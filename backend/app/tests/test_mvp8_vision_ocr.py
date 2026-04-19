"""MVP 8 Fase 3B — OCR via LLM Vision (camada 3 do PDF pipeline).

Testes com mocks do SDK Anthropic/OpenAI (não queima tokens reais) +
validação do fluxo de seleção de provider via AIKeyResolver.

Cobre:
  - Fluxo completo: PDF escaneado → render com pypdfium2 → mock vision
    retorna texto → resultado final inclui camada "ocr".
  - Sem provider com visão configurado: texto vazio + warning claro.
  - Só OpenAI configurado: cai pra OpenAI (Anthropic preferido mas opcional).
  - PDF já tem texto nas camadas 1+2: OCR não é disparado (economia).
  - OCR falha em uma página: continua processando as outras.
  - Limite de páginas respeitado.
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.pdf_layered_extractor import extract_pdf_layered_with_ocr


def _build_scanned_pdf(num_pages: int = 1) -> bytes:
    """PDF sem texto pesquisável — só retângulos/imagens (simula
    escaneado). pypdfium2 consegue renderizar as páginas."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for _ in range(num_pages):
        c.setFillGray(0.3)
        c.rect(100, 400, 400, 100, fill=1)
        c.showPage()
    c.save()
    return buf.getvalue()


def _build_textual_pdf() -> bytes:
    """PDF com texto real — camada 2 deve cobrir sem acionar OCR."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "RF-200: Documento textual — não precisa de OCR")
    c.showPage()
    c.save()
    return buf.getvalue()


# ============================================================================
# Fluxo positivo — camada 3 aciona e retorna texto
# ============================================================================

@pytest.mark.asyncio
async def test_escaneado_aciona_ocr_e_retorna_texto():
    """PDF sem texto → OCR mockado retorna string → pipeline reporta
    camada 'ocr' e texto OCR vira o resultado final."""
    pdf = _build_scanned_pdf()

    async def fake_ocr(pdf_bytes):
        return "RF-300 Extraído via OCR", []

    result = await extract_pdf_layered_with_ocr(pdf, ocr_callback=fake_ocr)
    assert "RF-300 Extraído via OCR" in result.text
    assert "ocr" in result.layers_used
    # Warning original "nenhuma camada produziu texto" deve ter sido removido
    assert not any("Nenhuma camada produziu texto" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_textual_nao_aciona_ocr():
    """PDF com texto pesquisável — camada 2 cobre, OCR não é chamado
    (economia de tokens)."""
    pdf = _build_textual_pdf()
    ocr_called = {"count": 0}

    async def fake_ocr(pdf_bytes):
        ocr_called["count"] += 1
        return "não deveria ser chamado", []

    result = await extract_pdf_layered_with_ocr(pdf, ocr_callback=fake_ocr)
    assert "RF-200" in result.text
    assert "ocr" not in result.layers_used
    assert ocr_called["count"] == 0


@pytest.mark.asyncio
async def test_ocr_callback_none_nao_quebra():
    """Backward compat: sem callback, pipeline retorna como Commit A."""
    pdf = _build_scanned_pdf()
    result = await extract_pdf_layered_with_ocr(pdf, ocr_callback=None)
    assert not result.text.strip()
    assert "ocr" not in result.layers_used
    # Warning original permanece
    assert any("OCR" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_ocr_callback_que_falha_preserva_warning():
    """Se o callback explode, o pipeline não quebra — retorna texto
    vazio e adiciona warning com o motivo."""
    pdf = _build_scanned_pdf()

    async def broken_ocr(pdf_bytes):
        raise RuntimeError("simulação de falha de rede")

    result = await extract_pdf_layered_with_ocr(pdf, ocr_callback=broken_ocr)
    assert not result.text.strip()
    assert any("OCR falhou" in w and "simulação" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_ocr_warnings_sao_propagados():
    """Warnings vindos do callback (ex: 'página 3 falhou') chegam ao
    resultado final pro GP ver."""
    pdf = _build_scanned_pdf()

    async def partial_ocr(pdf_bytes):
        return "texto da pagina 1", ["Página 2: falhou (timeout)"]

    result = await extract_pdf_layered_with_ocr(pdf, ocr_callback=partial_ocr)
    assert "texto da pagina 1" in result.text
    assert any("timeout" in w for w in result.warnings)


# ============================================================================
# vision_service — seleção de provider
# ============================================================================

@pytest.mark.asyncio
async def test_sem_provider_com_visao_avisa_indisponivel():
    """Projeto sem Anthropic/OpenAI configurado — OCR retorna vazio +
    warning explícito."""
    from app.services.vision_service import ocr_pdf_via_project_vision

    fake_chain = [
        {"provider": "ollama", "model": "llama3.1:8b", "base_url": None},
        {"provider": "deepseek", "model": "deepseek-chat", "base_url": None},
    ]

    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=fake_chain),
    ):
        text, warnings = await ocr_pdf_via_project_vision(
            b"fake", db=MagicMock(), project_id=uuid4(),
        )
    assert text == ""
    assert any("suporte a visão" in w for w in warnings)


@pytest.mark.asyncio
async def test_anthropic_e_openai_ambos_disponiveis_prefere_anthropic():
    """Ordem de preferência: Anthropic > OpenAI (alinhado ao contrato
    §6.2 — Claude tende a ter melhor raciocínio geral)."""
    from app.services.vision_service import _pick_vision_provider

    chain = [
        {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "base_url": None},
        {"provider": "openai", "model": "gpt-4o-mini", "base_url": None},
    ]
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-fake"),
    ):
        chosen = await _pick_vision_provider(db=MagicMock(), project_id=uuid4())

    assert chosen is not None
    provider, model, key = chosen
    assert provider == "anthropic"


@pytest.mark.asyncio
async def test_so_openai_configurado_cai_pra_openai():
    """Se o GP só tem OpenAI, usa OpenAI mesmo sendo segunda preferência."""
    from app.services.vision_service import _pick_vision_provider

    chain = [
        {"provider": "openai", "model": "gpt-4o-mini", "base_url": None},
    ]
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-openai"),
    ):
        chosen = await _pick_vision_provider(db=MagicMock(), project_id=uuid4())

    assert chosen is not None
    assert chosen[0] == "openai"


@pytest.mark.asyncio
async def test_provider_com_visao_mas_sem_chave_pula():
    """Se Anthropic está na chain mas vault não tem a chave (caso
    raro, config corrompida), skipa pra próxima opção."""
    from app.services.vision_service import _pick_vision_provider

    chain = [
        {"provider": "anthropic", "model": "claude-haiku", "base_url": None},
        {"provider": "openai", "model": "gpt-4o-mini", "base_url": None},
    ]

    async def key_getter(db, project_id, provider):
        return None if provider == "anthropic" else "sk-openai"

    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(side_effect=key_getter),
    ):
        chosen = await _pick_vision_provider(db=MagicMock(), project_id=uuid4())

    assert chosen is not None
    assert chosen[0] == "openai"


# ============================================================================
# Renderização de páginas
# ============================================================================

def test_render_pdf_pages_respeita_max_pages():
    """PDF com 5 páginas, max_pages=2 → retorna 2 PNGs."""
    from app.services.vision_service import _render_pdf_pages

    pdf = _build_scanned_pdf(num_pages=5)
    pages = _render_pdf_pages(pdf, max_pages=2)
    assert len(pages) == 2
    # Todos são PNG válidos (começam com magic bytes)
    for png in pages:
        assert png.startswith(b"\x89PNG")


def test_render_pdf_bytes_invalidos_retorna_lista_vazia():
    """Bytes que não são PDF — não explode."""
    from app.services.vision_service import _render_pdf_pages
    pages = _render_pdf_pages(b"not a pdf", max_pages=5)
    assert pages == []


# ============================================================================
# Integração ponta-a-ponta via vision_service + mock do SDK
# ============================================================================

@pytest.mark.asyncio
async def test_ocr_end_to_end_com_anthropic_mockado():
    """Fluxo completo: vision_service seleciona Anthropic, renderiza
    página, chama SDK mockado, retorna texto concatenado."""
    from app.services.vision_service import ocr_pdf_via_project_vision

    pdf = _build_scanned_pdf(num_pages=2)
    chain = [{"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "base_url": None}]

    # Mock do SDK Anthropic — retorna um texto por página
    fake_response = MagicMock()
    block = MagicMock()
    block.text = "Texto extraído da página via Claude"
    fake_response.content = [block]

    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_response)

    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-ant-fake"),
    ), patch(
        "app.services.vision_service.AsyncAnthropic",
        return_value=fake_client,
        create=True,
    ):
        # Patch AsyncAnthropic no namespace do anthropic — vision_service
        # importa dentro da função, então precisamos patchar lá.
        import anthropic
        with patch.object(anthropic, "AsyncAnthropic", return_value=fake_client):
            text, warnings = await ocr_pdf_via_project_vision(
                pdf, db=MagicMock(), project_id=uuid4(), max_pages=2,
            )

    assert "Texto extraído da página via Claude" in text
    # 2 páginas × mesma resposta mockada → duas marcações de página
    assert text.count("[PÁGINA") == 2
    # SDK chamado duas vezes (1 por página)
    assert fake_client.messages.create.await_count == 2


@pytest.mark.asyncio
async def test_ocr_excede_limite_paginas_emite_warning():
    """Doc com 15 páginas, limit=3 — só processa 3 e avisa."""
    from app.services.vision_service import ocr_pdf_via_project_vision

    pdf = _build_scanned_pdf(num_pages=15)
    chain = [{"provider": "anthropic", "model": "claude-haiku", "base_url": None}]

    fake_response = MagicMock()
    block = MagicMock()
    block.text = "ok"
    fake_response.content = [block]
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_response)

    import anthropic
    with patch(
        "app.services.ai_key_resolver.AIKeyResolver.resolve_project_provider_chain",
        new=AsyncMock(return_value=chain),
    ), patch(
        "app.services.ai_key_resolver.AIKeyResolver.get_project_key",
        new=AsyncMock(return_value="sk-ant-fake"),
    ), patch.object(anthropic, "AsyncAnthropic", return_value=fake_client):
        text, warnings = await ocr_pdf_via_project_vision(
            pdf, db=MagicMock(), project_id=uuid4(), max_pages=3,
        )

    assert any("excedeu" in w.lower() and "3 páginas" in w for w in warnings)
    assert fake_client.messages.create.await_count == 3
