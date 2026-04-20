"""DT-4 dogfood — `_detect_pii` usa extrator real do formato antes de regex.

Cobre:
  - Texto simples com CPF válido → detectado.
  - PDF binário (sem texto humano) → NÃO detecta PII falso de xref numérico.
  - DOCX com texto humano contendo CPF → detectado.
  - file_type 'image'/'spreadsheet' → não escaneia.
  - Falha do extractor não derruba ingestão (retorna 'sem PII').
  - DOCX vazio (`[Erro ...]`) → não escaneia.
"""
from __future__ import annotations

import io

import pytest

from app.services.ingestion_service import IngestionService


def _make_real_docx_with_text(content: str) -> bytes:
    """Gera um .docx mínimo via python-docx contendo `content`."""
    from docx import Document
    doc = Document()
    doc.add_paragraph(content)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_real_pdf_with_text(content: str) -> bytes:
    """Gera um PDF real com texto extraível via reportlab."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, content)
    c.showPage()
    c.save()
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────────
# Caminho positivo: PII real é detectado
# ────────────────────────────────────────────────────────────────────────

def test_text_simples_com_cpf_detecta():
    """Texto simples segue funcionando — fluxo legado."""
    # 111.444.777-35 é CPF mod-11 válido
    text = b"Contato: meu CPF eh 11144477735 e moro em SP."
    detected, fields = IngestionService._detect_pii(text, "text")
    assert detected is True
    assert "cpf" in fields


def test_pdf_real_com_cpf_detecta():
    """PDF gerado via reportlab com CPF visível — extractor pega."""
    pdf = _make_real_pdf_with_text("CPF do titular: 11144477735")
    detected, fields = IngestionService._detect_pii(pdf, "pdf")
    assert detected is True
    assert "cpf" in fields


def test_docx_real_com_cpf_detecta():
    docx = _make_real_docx_with_text("Documento do titular CPF 11144477735")
    detected, fields = IngestionService._detect_pii(docx, "docx")
    assert detected is True
    assert "cpf" in fields


# ────────────────────────────────────────────────────────────────────────
# Caminho do bug: PDF/DOCX sem PII real, com runs numéricos
# ────────────────────────────────────────────────────────────────────────

def test_pdf_real_sem_pii_nao_dispara_falso_positivo():
    """PDF com texto técnico cheio de números (IDs, métricas) — sem PII real.

    Antes: decode("utf-8") bruto sobre bytes do PDF capturava sequências
    numéricas em xref tables, gerando falso-positivo. Após DT-4: extrator
    real só vê texto humano-legível, regex só roda nesse texto.
    """
    pdf = _make_real_pdf_with_text(
        "Métricas de execução: latency_ms=12345 size=98765432 "
        "request_id=11122233344 score=87654321 "
        "obs: nenhuma informação pessoal."
    )
    detected, fields = IngestionService._detect_pii(pdf, "pdf")
    # Os valores acima NÃO são CPFs/CNPJs/cartões válidos — devem passar.
    assert detected is False, f"falso-positivo: {fields}"


def test_docx_real_sem_pii():
    docx = _make_real_docx_with_text(
        "Estatísticas: req=123456789 build=987654321 latency=11122233344"
    )
    detected, fields = IngestionService._detect_pii(docx, "docx")
    assert detected is False, f"falso-positivo: {fields}"


# ────────────────────────────────────────────────────────────────────────
# Tipos não escaneados
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ft", ["image", "spreadsheet"])
def test_image_e_spreadsheet_nao_escaneados(ft):
    """Tipos binários sem extrator dedicado → pula scan."""
    payload = b"\x89PNG\r\n\x1a\n" + b"qualquer coisa 11144477735"
    detected, fields = IngestionService._detect_pii(payload, ft)
    assert detected is False
    assert fields == []


# ────────────────────────────────────────────────────────────────────────
# Falha do extractor é silenciosa
# ────────────────────────────────────────────────────────────────────────

def test_pdf_corrompido_retorna_sem_pii():
    """PDF inválido não derruba a ingestão — extractor falha, scan retorna ()."""
    bogus = b"isto nao eh um pdf de verdade"
    detected, fields = IngestionService._detect_pii(bogus, "pdf")
    assert detected is False
    assert fields == []


def test_docx_corrompido_retorna_sem_pii():
    bogus = b"isto nao eh um docx"
    detected, fields = IngestionService._detect_pii(bogus, "docx")
    assert detected is False
    assert fields == []


# ────────────────────────────────────────────────────────────────────────
# Helper público
# ────────────────────────────────────────────────────────────────────────

def test_extract_text_for_pii_scan_trunca_em_100kb():
    """Saída do helper nunca passa de 100 KB."""
    big = ("texto longo " * 20_000).encode("utf-8")
    text = IngestionService._extract_text_for_pii_scan(big, "text")
    assert len(text) <= 100_000


def test_extract_text_for_pii_scan_image_retorna_vazio():
    text = IngestionService._extract_text_for_pii_scan(b"binario", "image")
    assert text == ""
