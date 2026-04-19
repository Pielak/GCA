"""MVP 8 Fase 3B — OCR via LLM multimodal (camada 3 do PDF pipeline).

Quando as camadas 1 (AcroForm) e 2 (texto pesquisável) não produzem
conteúdo, o PDF provavelmente é escaneado (imagem pura). Este módulo
renderiza cada página com pypdfium2 e envia pra um provider com
capacidade de visão pra ler o texto.

Política de escolha de provider (CLAUDE.md §6 + contrato §6.2):
  - Usa o provider configurado pelo GP no projeto via AIKeyResolver.
  - Extração de texto é **baixa criticidade** — não consolida OCG, não
    decide arquitetura. Pode usar modelo barato.
  - Só providers com suporte nativo a vision são candidatos. Se o GP
    só configurou providers sem vision (ex: Ollama sem modelo vision),
    retorna string vazia + warning — não há fallback silencioso.

Providers suportados nesta fase:
  - Anthropic: todos os modelos claude-3+ têm vision.
  - OpenAI: gpt-4o, gpt-4o-mini, gpt-4.1 (*-vision legados também).

Fora de escopo (futuro):
  - Gemini Vision (API ligeiramente diferente).
  - Ollama Vision (llava, llama3.2-vision) — exige probe do modelo
    instalado.
  - Batching de múltiplas páginas em uma chamada (pra reduzir custo).
"""
from __future__ import annotations

import base64
import io
from uuid import UUID
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# Providers que têm vision API nativa. Ordem = preferência quando o
# projeto tem múltiplos configurados.
PROVIDERS_WITH_VISION = ("anthropic", "openai")

# Default model por provider — barato e com vision. GP pode sobrescrever
# via project_settings, mas no MVP usamos o default quando ele não
# especifica um modelo multimodal explicitamente.
DEFAULT_VISION_MODEL = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}

# Limite de páginas por chamada — OCR de PDFs de centenas de páginas
# via LLM seria caro e lento. Se o doc é maior, o texto é truncado com
# aviso; GP pode refazer upload de um recorte.
DEFAULT_MAX_PAGES = 10

# Prompt de extração — instruções claras pra não perder dados tabulares
# (conforme o formato que o Arguidor já espera da Fase 2 do .docx).
VISION_PROMPT = (
    "Extraia todo o texto legível desta página de documento em português ou inglês. "
    "Preserve a ordem de leitura natural. "
    "Se houver tabela, formate cada linha como "
    "[Coluna1: valor] [Coluna2: valor]. "
    "Se houver formulário preenchido, formate como "
    "[NomeDoCampo: valor]. "
    "NÃO adicione preâmbulos, explicações nem comentários — retorne APENAS "
    "o texto extraído."
)


async def ocr_pdf_via_project_vision(
    pdf_bytes: bytes,
    db: AsyncSession,
    project_id: UUID,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[str, list[str]]:
    """Rende cada página do PDF e pede pro LLM extrair o texto.

    Retorna `(texto, warnings)`. Texto vazio + warning listando o motivo
    quando nenhum provider com visão está configurado ou todos falham.
    """
    warnings: list[str] = []

    chosen = await _pick_vision_provider(db, project_id)
    if not chosen:
        warnings.append(
            "Nenhum provider com suporte a visão (Anthropic/OpenAI) está "
            "configurado no projeto. OCR de PDF escaneado ficou indisponível."
        )
        return "", warnings

    provider, model, api_key = chosen

    page_images = _render_pdf_pages(pdf_bytes, max_pages=max_pages)
    if not page_images:
        warnings.append("Não foi possível renderizar páginas do PDF com pypdfium2.")
        return "", warnings

    if len(page_images) == max_pages:
        warnings.append(
            f"PDF excedeu o limite de {max_pages} páginas para OCR via Vision; "
            "apenas as primeiras foram processadas."
        )

    parts: list[str] = []
    for idx, png_bytes in enumerate(page_images):
        try:
            text = await _call_vision(provider, model, api_key, png_bytes)
        except Exception as exc:
            warnings.append(f"Página {idx+1}: OCR falhou ({exc}).")
            logger.warning(
                "vision.page_failed",
                provider=provider,
                page=idx + 1,
                error=str(exc),
            )
            continue
        if text.strip():
            parts.append(f"[PÁGINA {idx+1}]\n{text.strip()}")

    if not parts:
        warnings.append("OCR rodou mas todas as páginas retornaram vazio.")
        return "", warnings

    final = "\n\n".join(parts)
    logger.info(
        "vision.ocr_completed",
        provider=provider,
        model=model,
        pages=len(page_images),
        pages_with_text=len(parts),
        chars=len(final),
    )
    return final, warnings


async def _pick_vision_provider(
    db: AsyncSession,
    project_id: UUID,
) -> Optional[tuple[str, str, str]]:
    """Resolve (provider, model, api_key) pro primeiro provider da
    cadeia do projeto que tenha suporte a visão e chave válida."""
    from app.services.ai_key_resolver import AIKeyResolver

    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
    for entry in chain:
        provider = entry.get("provider")
        if provider not in PROVIDERS_WITH_VISION:
            continue
        api_key = await AIKeyResolver.get_project_key(db, project_id, provider)
        if not api_key:
            continue
        model = entry.get("model") or DEFAULT_VISION_MODEL[provider]
        return provider, model, api_key

    return None


def _render_pdf_pages(pdf_bytes: bytes, *, max_pages: int) -> list[bytes]:
    """Renderiza cada página do PDF como PNG via pypdfium2 a 150 DPI —
    resolução suficiente pra OCR mantendo payload razoável.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("vision.pypdfium2_missing")
        return []

    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except Exception as exc:
        logger.warning("vision.pdf_open_failed", error=str(exc))
        return []

    pages: list[bytes] = []
    # 150 DPI / 72 DPI base = scale 2.08 — bom equilíbrio nitidez/tamanho
    scale = 150 / 72
    try:
        total = len(pdf)
        for i in range(min(total, max_pages)):
            try:
                page = pdf[i]
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG", optimize=True)
                pages.append(buf.getvalue())
            except Exception as exc:
                logger.warning("vision.page_render_failed", page=i + 1, error=str(exc))
                continue
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return pages


async def _call_vision(provider: str, model: str, api_key: str, png_bytes: bytes) -> str:
    """Dispara a chamada multimodal. Thin wrapper — não tenta retry ou
    fallback (o chamador decide o que fazer com as exceções)."""
    if provider == "anthropic":
        return await _call_anthropic_vision(api_key, model, png_bytes)
    if provider == "openai":
        return await _call_openai_vision(api_key, model, png_bytes)
    raise ValueError(f"Provider sem handler de vision: {provider}")


async def _call_anthropic_vision(api_key: str, model: str, png_bytes: bytes) -> str:
    from anthropic import AsyncAnthropic

    b64 = base64.b64encode(png_bytes).decode("ascii")
    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )
    blocks = getattr(response, "content", []) or []
    parts: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


async def _call_openai_vision(api_key: str, model: str, png_bytes: bytes) -> str:
    from openai import AsyncOpenAI

    b64 = base64.b64encode(png_bytes).decode("ascii")
    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                        },
                    },
                ],
            }
        ],
    )
    choices = getattr(response, "choices", []) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message else ""
    return (content or "").strip()
