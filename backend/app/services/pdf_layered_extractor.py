"""MVP 8 Fase 3 (Commit A) — pipeline de camadas para PDF.

O extractor antigo em `arguider_service._extract_pdf` chama direto
`pdfplumber.page.extract_text()` e retorna só isso. Não funciona para:
  - PDFs que são formulários preenchidos (AcroForm) onde o texto "visível"
    está em campos, não no conteúdo;
  - PDFs escaneados (imagem pura) — retornam string vazia, o pipeline
    recebe nada e o OCG não evolui, repetindo o mesmo bug do docx-em-tabela.

Pipeline definido no contrato §7 MVP 8 Fase 3:

  Camada 1 — AcroForm: se o PDF é um formulário, ler cada campo e
             emitir como `[Campo: valor]`, igual ao formato das tabelas
             de docx (Fase 2).
  Camada 2 — texto pesquisável: `pdfplumber.extract_text()` por página.
  Camada 3 — OCR via LLM Vision (implementação no Commit B) — render
             cada página com pypdfium2 e enviar pra provider multimodal.

Este módulo implementa as camadas 1 e 2 + deduplicação. A camada 3
entra em seguida sem mudar o contrato público deste módulo (o chamador
chama `extract_pdf_layered(bytes)` e recebe `PdfExtractionResult`).

Deduplicação: se o texto da camada 2 já contém todo o conteúdo da
camada 1 (por substring), não duplica. Caso contrário, emite ambos —
o Arguidor se beneficia de ver o texto corrente E os campos de
formulário estruturados.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PdfExtractionResult:
    """Resultado da extração em camadas.

    text: string final pronta pra passar pro Arguidor.
    layers_used: lista ordenada de nomes das camadas que contribuíram
                 ("acroform", "text", "ocr").
    acroform_fields: nome→valor dos campos de formulário encontrados.
    pages_text: texto extraído por página (índice 0-based).
    warnings: mensagens de aviso (não impedem uso do resultado).
    """
    text: str = ""
    layers_used: list[str] = field(default_factory=list)
    acroform_fields: dict[str, str] = field(default_factory=dict)
    pages_text: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_pdf_layered(file_bytes: bytes) -> PdfExtractionResult:
    """Extrai PDF em camadas. Retorna resultado mesmo quando falha
    parcial — o `text` pode estar vazio e `warnings` explica por quê.

    Contrato pro chamador antigo (arguider_service): chame
    `extract_pdf_layered(b).text` pra obter string compatível com o
    extractor antigo.
    """
    result = PdfExtractionResult()
    if not file_bytes:
        result.warnings.append("PDF vazio — 0 bytes recebidos.")
        return result

    # Camada 1 — AcroForm
    try:
        fields = _extract_acroform_fields(file_bytes)
        if fields:
            result.acroform_fields = fields
            result.layers_used.append("acroform")
    except Exception as exc:
        result.warnings.append(f"Camada AcroForm falhou: {exc}")
        logger.warning("pdf_layered.acroform_failed", error=str(exc))

    # Camada 2 — texto pesquisável
    try:
        pages = _extract_searchable_text(file_bytes)
        if any(p.strip() for p in pages):
            result.pages_text = pages
            result.layers_used.append("text")
    except Exception as exc:
        result.warnings.append(f"Camada de texto pesquisável falhou: {exc}")
        logger.warning("pdf_layered.text_failed", error=str(exc))

    result.text = _merge_layers(result)

    if not result.text:
        result.warnings.append(
            "Nenhuma camada produziu texto. PDF provavelmente é escaneado/imagem — "
            "OCR via LLM Vision será necessário."
        )

    return result


async def extract_pdf_layered_with_ocr(
    file_bytes: bytes,
    ocr_callback: Callable[[bytes], Awaitable[tuple[str, list[str]]]] | None = None,
) -> PdfExtractionResult:
    """Pipeline completo em camadas 1+2+3. Camada 3 (OCR) só é
    disparada quando 1+2 não produziram texto E `ocr_callback` foi
    passado. O callback recebe os bytes do PDF e deve retornar
    `(texto_ocr, warnings)`.

    Separado da `extract_pdf_layered` pra manter sync puro quando OCR
    não é necessário (testes isolados, caminho crítico de PDF textual).
    """
    result = extract_pdf_layered(file_bytes)
    if result.text or ocr_callback is None:
        return result

    try:
        ocr_text, ocr_warnings = await ocr_callback(file_bytes)
    except Exception as exc:
        result.warnings.append(f"OCR falhou: {exc}")
        logger.warning("pdf_layered.ocr_failed", error=str(exc))
        return result

    if ocr_warnings:
        result.warnings.extend(ocr_warnings)

    if ocr_text.strip():
        result.layers_used.append("ocr")
        result.text = ocr_text
        # Tira o warning "nenhuma camada produziu texto" já que agora OCR cobriu
        result.warnings = [w for w in result.warnings if "Nenhuma camada produziu texto" not in w]

    return result


def _extract_acroform_fields(file_bytes: bytes) -> dict[str, str]:
    """Lê AcroForm fields via pypdf. Retorna dict nome→valor só com
    campos que tenham valor preenchido (ignorar campos vazios)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return {}

    reader = PdfReader(io.BytesIO(file_bytes))
    try:
        fields = reader.get_form_text_fields() or {}
    except Exception:
        fields = {}

    try:
        all_fields = reader.get_fields() or {}
    except Exception:
        all_fields = {}

    merged: dict[str, str] = {}
    for name, value in fields.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            merged[str(name)] = text

    for name, field_obj in all_fields.items():
        if name in merged:
            continue
        try:
            value = field_obj.get("/V")
        except Exception:
            value = None
        if value is None:
            continue
        if isinstance(value, list):
            text = ", ".join(str(v) for v in value).strip()
        else:
            text = str(value).strip()
        if text and text not in ("/Off",):
            merged[str(name)] = text

    return merged


def _extract_searchable_text(file_bytes: bytes) -> list[str]:
    """Extrai texto por página com pdfplumber — fallback pra pypdf se
    pdfplumber falhar pontualmente em alguma página."""
    try:
        import pdfplumber
    except ImportError:
        return _extract_with_pypdf(file_bytes)

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("pdf_layered.pdfplumber_page_failed", error=str(exc))
                text = ""
            pages.append(text)
    return pages


def _extract_with_pypdf(file_bytes: bytes) -> list[str]:
    """Fallback quando pdfplumber não está disponível."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    return [page.extract_text() or "" for page in reader.pages]


def _merge_layers(result: PdfExtractionResult) -> str:
    """Concatena AcroForm + texto pesquisável com deduplicação.

    Regra: se o texto pesquisável já contém cada valor do AcroForm
    literalmente, não emite bloco separado pra formulário (evita
    duplicação). Se nem todos os valores estão no texto, emite os
    campos como parágrafos estruturados no topo.
    """
    parts: list[str] = []

    text_joined = "\n\n".join(p for p in result.pages_text if p and p.strip()).strip()

    if result.acroform_fields:
        missing_in_text = [
            (name, value) for name, value in result.acroform_fields.items()
            if value not in text_joined
        ]
        if missing_in_text:
            parts.append("[FORMULÁRIO]")
            for name, value in missing_in_text:
                parts.append(f"[{name}: {value}]")
            parts.append("[/FORMULÁRIO]")

    if text_joined:
        parts.append(text_joined)

    return "\n\n".join(parts)
