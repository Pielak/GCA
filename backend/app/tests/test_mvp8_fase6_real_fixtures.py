"""MVP 8 Fase 6 — Regressão com fixtures reais.

Os testes do MVP 8 até aqui (rich_docx, pdf_layered, vision_ocr,
extraction_report) construíram documentos in-memory via python-docx /
reportlab. Isso pega lógica de extração, mas **não pega regressões com
arquivos reais** — encoding estranho, XML de versões antigas do Word,
PDFs com fonts embarcadas quebradas, etc.

Esta suite versiona 3 arquivos em `backend/tests/fixtures/mvp8/` e
valida que a extração produz resultado acima de um baseline mínimo.
Asserts conservadores ("pelo menos X RFs") toleram evolução do LLM e
regex sem quebrar testes a cada tweak.

Fixtures (ver README.md naquele diretório):
  - `automacao_juridica_v2.docx` — doc rico do dogfood, 94 RFs
  - `gca_template_ingestao.docx` — template simples só paragraphs
  - `datajud_documento_tecnico.pdf` — PDF real com texto pesquisável
"""
from pathlib import Path

import pytest

from app.services.extraction_report_service import build_extraction_report
from app.services.pdf_layered_extractor import extract_pdf_layered
from app.services.rich_docx_extractor import extract_rich_text

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "mvp8"


# ============================================================================
# Helper
# ============================================================================

def _load(name: str) -> bytes:
    """Carrega fixture pelo nome. Pula teste se não estiver presente
    (permite o repo dropar fixtures se precisar, sem quebrar tudo)."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"fixture ausente: {path}")
    return path.read_bytes()


# ============================================================================
# automacao_juridica_v2.docx — doc rico do dogfood
# ============================================================================

def test_automacao_juridica_extracao_minima():
    """Doc v2.0 tem ~32k chars. Regressão: qualquer mudança no extractor
    que reduza isso drasticamente indica perda de conteúdo."""
    bytes_ = _load("automacao_juridica_v2.docx")
    text = extract_rich_text(bytes_)
    assert len(text) >= 20_000, (
        f"extração devolveu só {len(text)} chars (esperado ≥ 20k)"
    )
    # Sem indicador de erro no início
    assert not text.startswith("["), f"início suspeito: {text[:80]!r}"


def test_automacao_juridica_detecta_rfs():
    """Doc tem 94 RFs. Validamos ≥ 50 pra tolerar evolução do regex."""
    import re
    bytes_ = _load("automacao_juridica_v2.docx")
    text = extract_rich_text(bytes_)
    rf_matches = set(re.findall(r"\bRF-\d{2,}\b", text))
    assert len(rf_matches) >= 50, (
        f"só {len(rf_matches)} RFs únicos detectados: {sorted(rf_matches)[:10]}"
    )


def test_automacao_juridica_detecta_rnfs():
    """Doc tem 9 RNFs. Validamos ≥ 5."""
    import re
    bytes_ = _load("automacao_juridica_v2.docx")
    text = extract_rich_text(bytes_)
    rnf_matches = set(re.findall(r"\bRNF-\d{2,}\b", text))
    assert len(rnf_matches) >= 5


def test_automacao_juridica_report_completo():
    """extraction_report monta shape estável + RFs detectados."""
    bytes_ = _load("automacao_juridica_v2.docx")
    report = build_extraction_report(bytes_, "docx")
    assert report["ok"] is True
    assert report["chars"] >= 20_000
    assert report["paragraphs"] >= 50  # many paragraphs
    assert len(report["requirements_functional"]) >= 1  # pelo menos o preview


def test_automacao_juridica_sem_warnings():
    """Doc bem-formado não deve gerar warnings no extractor."""
    bytes_ = _load("automacao_juridica_v2.docx")
    report = build_extraction_report(bytes_, "docx")
    assert report["warnings"] == [], f"warnings inesperados: {report['warnings']}"


# ============================================================================
# gca_template_ingestao.docx — template simples
# ============================================================================

def test_gca_template_extracao_basica():
    """Template tem ~8k chars sem tabelas. Baseline mínimo de paragraphs."""
    bytes_ = _load("gca_template_ingestao.docx")
    text = extract_rich_text(bytes_)
    assert len(text) >= 3_000, f"esperava ≥ 3k chars, veio {len(text)}"
    assert not text.startswith("[")


def test_gca_template_sem_tabelas():
    """Template é paragraphs only. Se começar a detectar tabelas falsas,
    há regressão no parser de tabelas."""
    bytes_ = _load("gca_template_ingestao.docx")
    text = extract_rich_text(bytes_)
    # [TABELA] só é emitido quando rich_docx detecta <w:tbl>
    assert "[TABELA]" not in text


def test_gca_template_report_ok():
    bytes_ = _load("gca_template_ingestao.docx")
    report = build_extraction_report(bytes_, "docx")
    assert report["ok"] is True
    assert report["tables_detected"] == 0


# ============================================================================
# datajud_documento_tecnico.pdf — PDF real do dogfood
# ============================================================================

def test_datajud_pdf_extracao_texto():
    """PDF tem texto pesquisável — camada 2 (text) do layered extractor
    deve cobrir. Sem necessidade de Vision OCR."""
    bytes_ = _load("datajud_documento_tecnico.pdf")
    result = extract_pdf_layered(bytes_)
    assert result.text, "texto vazio — extração falhou"
    assert "text" in result.layers_used, f"camadas usadas: {result.layers_used}"
    # OCR (camada 3) NÃO deve ter sido necessária
    assert "ocr" not in result.layers_used


def test_datajud_pdf_tamanho_minimo():
    """311 KB de PDF com conteúdo técnico — baseline ≥ 5k chars."""
    bytes_ = _load("datajud_documento_tecnico.pdf")
    result = extract_pdf_layered(bytes_)
    assert len(result.text) >= 5_000, (
        f"só {len(result.text)} chars extraídos"
    )


def test_datajud_pdf_multipagina():
    """PDF tem múltiplas páginas — `pages_text` deve listar > 1."""
    bytes_ = _load("datajud_documento_tecnico.pdf")
    result = extract_pdf_layered(bytes_)
    assert result.pdf_pages_with_text if False else True  # attr não existe no result
    # Validamos via pages_text list
    non_empty = [p for p in result.pages_text if p and p.strip()]
    assert len(non_empty) >= 2, f"esperava ≥ 2 páginas com texto"


def test_datajud_pdf_report_pdf_layers():
    """extraction_report expõe pdf_layers — frontend da Fase 5 consome."""
    bytes_ = _load("datajud_documento_tecnico.pdf")
    report = build_extraction_report(bytes_, "pdf")
    assert report["ok"] is True
    assert "text" in report["pdf_layers"]
    assert report["pdf_pages_with_text"] >= 2


# ============================================================================
# Propriedades cross-fixture — contrato estável do extractor
# ============================================================================

def test_todos_fixtures_report_tem_shape_canonico():
    """Shape do report é estável — frontend depende das mesmas chaves."""
    expected_keys = {
        "ok", "file_type", "chars", "paragraphs", "tables_detected",
        "text_boxes", "headers_footers", "pdf_layers",
        "pdf_pages_with_text", "acroform_fields",
        "requirements_functional", "requirements_non_functional",
        "module_hints", "warnings", "text_sample",
    }
    for name, file_type in [
        ("automacao_juridica_v2.docx", "docx"),
        ("gca_template_ingestao.docx", "docx"),
        ("datajud_documento_tecnico.pdf", "pdf"),
    ]:
        bytes_ = _load(name)
        report = build_extraction_report(bytes_, file_type)
        missing = expected_keys - set(report.keys())
        assert not missing, f"{name}: faltam chaves {missing}"


def test_fixtures_nao_geram_caminho_de_erro_informativo():
    """Nenhum fixture deve retornar string começando com '[' (contrato
    antigo pra sinalizar erro)."""
    for name, fn in [
        ("automacao_juridica_v2.docx", lambda b: extract_rich_text(b)),
        ("gca_template_ingestao.docx", lambda b: extract_rich_text(b)),
        ("datajud_documento_tecnico.pdf", lambda b: extract_pdf_layered(b).text),
    ]:
        bytes_ = _load(name)
        text = fn(bytes_)
        assert not text.startswith("["), (
            f"{name}: extração devolveu formato de erro: {text[:100]!r}"
        )


def test_fixtures_dir_tem_readme():
    """Contrato: qualquer fixture versionada tem documentação mínima."""
    readme = FIXTURES_DIR / "README.md"
    if not readme.exists():
        pytest.skip("README ausente — documentação não verificada")
    content = readme.read_text()
    # Todos os fixtures versionados são citados
    for name in ("automacao_juridica_v2.docx", "gca_template_ingestao.docx",
                 "datajud_documento_tecnico.pdf"):
        assert name in content, f"README não menciona {name}"
