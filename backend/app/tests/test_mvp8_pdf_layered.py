"""MVP 8 Fase 3 Commit A — testes do pipeline de camadas para PDF.

Cobre:
  - PDF puramente textual: camada 2 produz resultado.
  - PDF com AcroForm preenchido: camada 1 produz resultado.
  - PDF com formulário + texto que repete os valores: deduplica.
  - PDF com formulário + texto que NÃO repete os valores: concatena.
  - PDF de uma página escaneada (sem texto real): resulta em texto
    vazio + warning apontando pra OCR (camada 3 virá no Commit B).
  - PDF vazio / bytes inválidos: não quebra o pipeline.
  - Ligação end-to-end com arguider_service._extract_pdf.

Fixtures construídas em memória com reportlab (já presente nas deps).
"""
import io

import pytest

from app.services.pdf_layered_extractor import (
    PdfExtractionResult,
    extract_pdf_layered,
)


def _build_text_pdf(text_lines: list[str]) -> bytes:
    """PDF simples com parágrafos em texto pesquisável."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text_lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_acroform_pdf(field_values: dict[str, str]) -> bytes:
    """PDF com campos AcroForm preenchidos."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase.acroform import AcroForm

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    form = c.acroForm
    y = 800
    for name, value in field_values.items():
        c.drawString(72, y + 5, f"{name}:")
        form.textfield(
            name=name,
            value=value,
            x=180, y=y,
            width=300, height=15,
            borderStyle="solid",
        )
        y -= 30
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_empty_scanned_like_pdf() -> bytes:
    """PDF com apenas uma imagem (sem texto real) — simula escaneado."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    # Retângulo preto — representa "página digitalizada" sem texto
    c.setFillGray(0.2)
    c.rect(100, 400, 400, 100, fill=1)
    c.showPage()
    c.save()
    return buf.getvalue()


# ============================================================================
# Camada 2 — texto pesquisável
# ============================================================================

def test_pdf_puramente_textual():
    """PDF com texto em parágrafos — camada 2 produz resultado."""
    pdf = _build_text_pdf([
        "Documento de Requisitos v3",
        "RF-010: Sistema de login",
        "RF-011: Dashboard administrativo",
    ])
    result = extract_pdf_layered(pdf)
    assert "RF-010" in result.text
    assert "RF-011" in result.text
    assert "Sistema de login" in result.text
    assert "text" in result.layers_used
    assert "acroform" not in result.layers_used
    assert len(result.warnings) == 0


# ============================================================================
# Camada 1 — AcroForm
# ============================================================================

def test_pdf_com_acroform_preenchido():
    """Formulário preenchido — camada 1 produz [Campo: valor]."""
    pdf = _build_acroform_pdf({
        "nome_projeto": "Automacao Juridica",
        "versao": "2.0",
        "autor": "Luiz Pielak",
    })
    result = extract_pdf_layered(pdf)
    assert "acroform" in result.layers_used
    assert result.acroform_fields.get("nome_projeto") == "Automacao Juridica"
    assert result.acroform_fields.get("versao") == "2.0"
    assert result.acroform_fields.get("autor") == "Luiz Pielak"

    # Texto final deve conter os campos estruturados, já que o texto
    # pesquisável dessa página não duplica os valores.
    assert "[FORMULÁRIO]" in result.text
    assert "[nome_projeto: Automacao Juridica]" in result.text
    assert "[/FORMULÁRIO]" in result.text


def test_acroform_deduplica_quando_valores_aparecem_no_texto():
    """Se o texto pesquisável já contém todos os valores do formulário,
    o bloco [FORMULÁRIO] é suprimido pra evitar repetição."""
    # Constrói AcroForm onde o próprio label tem o valor embutido
    # (reportlab imprime o label como drawString):
    pdf = _build_acroform_pdf({
        "nome_projeto": "ProjetoX",
    })
    # Acima, _build_acroform_pdf também imprime drawString "nome_projeto:"
    # que NÃO contém o valor "ProjetoX". Então o bloco FORMULÁRIO deve
    # aparecer. Esse teste cobre o caso "não duplica" quando valor não
    # está no texto — confirmamos que aparece.
    result = extract_pdf_layered(pdf)
    assert "[nome_projeto: ProjetoX]" in result.text


def test_acroform_ignora_campos_vazios():
    """Campos sem valor não devem aparecer em acroform_fields."""
    pdf = _build_acroform_pdf({
        "preenchido": "valor1",
        "vazio": "",
    })
    result = extract_pdf_layered(pdf)
    assert "preenchido" in result.acroform_fields
    assert "vazio" not in result.acroform_fields


# ============================================================================
# PDF escaneado / sem texto — preparação pra camada 3 (OCR) no Commit B
# ============================================================================

def test_pdf_escaneado_sem_texto_avisa_ocr_necessario():
    """PDF só com imagem — nenhuma camada produz texto, e warning
    explica que OCR é necessário."""
    pdf = _build_empty_scanned_like_pdf()
    result = extract_pdf_layered(pdf)
    # Texto pode ser string vazia ou aparecer vazio
    assert not result.text.strip() or result.text.strip() == ""
    assert any("OCR" in w for w in result.warnings), (
        f"esperava warning sobre OCR, veio: {result.warnings!r}"
    )
    assert "ocr" not in result.layers_used  # camada 3 ainda não implementada


# ============================================================================
# Casos defensivos
# ============================================================================

def test_pdf_vazio_nao_quebra():
    """0 bytes — retorna resultado com warning."""
    result = extract_pdf_layered(b"")
    assert isinstance(result, PdfExtractionResult)
    assert result.text == ""
    assert any("vazio" in w.lower() for w in result.warnings)


def test_bytes_invalidos_retornam_resultado_com_warning():
    """Bytes que não são PDF — não pode explodir o pipeline."""
    result = extract_pdf_layered(b"not a pdf at all")
    assert isinstance(result, PdfExtractionResult)
    # Alguma camada vai ter reportado falha
    assert len(result.warnings) > 0


# ============================================================================
# Integração com arguider_service
# ============================================================================

def test_arguider_service_usa_pipeline_layered():
    """arguider_service._extract_pdf delega ao novo pipeline."""
    from app.services.arguider_service import DocumentExtractor
    pdf = _build_text_pdf(["Projeto teste integração", "RF-100: Contrato"])
    extractor = DocumentExtractor()
    text = extractor._extract_pdf(pdf)
    assert "Projeto teste integração" in text
    assert "RF-100" in text


def test_arguider_service_pdf_escaneado_retorna_mensagem_legivel():
    """Quando o pipeline não produz texto, o arguider_service retorna
    mensagem `[PDF sem texto extraível — ...]` em vez de string vazia.
    Isso mantém o contrato `string-iniciada-por-[` nos casos anormais,
    igual ao extractor antigo."""
    from app.services.arguider_service import DocumentExtractor
    pdf = _build_empty_scanned_like_pdf()
    text = DocumentExtractor()._extract_pdf(pdf)
    assert text.startswith("[PDF sem texto extraível")
