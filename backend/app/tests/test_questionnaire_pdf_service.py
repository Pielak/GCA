"""Testes de regressão do serviço de PDF editável do questionário técnico.

Cobre `generate_pdf`, `extract_answers_from_pdf` e `extract_answers_from_text`.
Gate para impedir:
  - regressão do import (reportlab/pypdf ausentes no container) — testes falham no collect se a lib sumir;
  - regressão do AcroForm (nomes dos campos, formato dos checkboxes, `/Yes` etc.);
  - regressão do fluxo de leitura (ID → resposta).
"""
import io

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.questionnaire_pdf_service import (
    BLOCKS,
    extract_answers_from_pdf,
    extract_answers_from_text,
    generate_pdf,
)

pytestmark = pytest.mark.unit


# ─── Dados de apoio ──────────────────────────────────────────────────

Q_META = {q["id"]: q for b in BLOCKS for q in b["questions"]}


def _fill_pdf(pdf_bytes: bytes, values: dict) -> bytes:
    """Aplica AcroForm values em todas as páginas e devolve novo PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _multi_to_fields(q_id: str, labels: list[str]) -> dict:
    """Converte lista de rótulos de uma pergunta multi em campos q{id}_cb_{idx}."""
    options = Q_META[q_id]["options"]
    return {f"q{q_id}_cb_{options.index(l)}": "/Yes" for l in labels}


# ─── generate_pdf ────────────────────────────────────────────────────

def test_generate_pdf_returns_valid_pdf_bytes():
    pdf_bytes = generate_pdf(
        project_name="Projeto X",
        deliverable_type="new_system",
        project_slug="projeto-x",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 50_000  # sanidade de tamanho
    assert pdf_bytes.startswith(b"%PDF-")  # assinatura PDF


def test_generate_pdf_contains_all_49_acroform_fields():
    """Cada uma das 49 perguntas tem ao menos um campo no AcroForm."""
    pdf_bytes = generate_pdf(project_name="X", deliverable_type="new_system", project_slug="x")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    fields = reader.get_fields() or {}
    field_names = set(fields.keys())

    for q_id, meta in Q_META.items():
        if meta["type"] in ("text", "single"):
            assert f"q{q_id}" in field_names, f"Q{q_id} ({meta['type']}) sem campo q{q_id}"
        elif meta["type"] == "multi":
            # Pelo menos o primeiro checkbox existe
            assert f"q{q_id}_cb_0" in field_names, f"Q{q_id} sem q{q_id}_cb_0"
            # E o campo de "Outros"
            assert f"q{q_id}_outros" in field_names, f"Q{q_id} sem q{q_id}_outros"


def test_generate_pdf_prefills_project_name_and_slug():
    """Q1 e Q2 vêm pré-preenchidos."""
    pdf_bytes = generate_pdf(
        project_name="Meu Projeto",
        deliverable_type="new_system",
        project_slug="meu-projeto",
    )
    answers = extract_answers_from_pdf(pdf_bytes)
    assert answers.get("Q1") == "Meu Projeto"
    assert answers.get("Q2") == "meu-projeto"


# ─── extract_answers_from_pdf ────────────────────────────────────────

def test_extract_returns_empty_when_form_not_filled():
    """Q1/Q2 vêm pré-preenchidos via generate_pdf; sem pré-preenchimento
    (project_name=''), extração deve devolver dict vazio."""
    pdf_bytes = generate_pdf(project_name="", deliverable_type="", project_slug="")
    answers = extract_answers_from_pdf(pdf_bytes)
    assert answers == {}


def test_extract_reads_text_and_single_fields():
    pdf_bytes = generate_pdf(project_name="", deliverable_type="", project_slug="")
    filled = _fill_pdf(
        pdf_bytes,
        {
            "q1": "Nome do Projeto Preenchido",
            "q5": "Alta",
            "q6": "Confidencial",
        },
    )
    answers = extract_answers_from_pdf(filled)
    assert answers["Q1"] == "Nome do Projeto Preenchido"
    assert answers["Q5"] == "Alta"
    assert answers["Q6"] == "Confidencial"


def test_extract_reads_multi_checkboxes():
    pdf_bytes = generate_pdf(project_name="", deliverable_type="", project_slug="")
    values = {}
    values.update(_multi_to_fields("15", ["Aplicação web", "API"]))
    values.update(_multi_to_fields("16", ["Monólito modular", "Clean Architecture"]))
    filled = _fill_pdf(pdf_bytes, values)

    answers = extract_answers_from_pdf(filled)
    assert set(answers["Q15"]) == {"Aplicação web", "API"}
    assert set(answers["Q16"]) == {"Monólito modular", "Clean Architecture"}


def test_extract_ignores_unselected_single_placeholder():
    """`single` não preenchido vem como 'Selecione...' — não deve virar resposta."""
    pdf_bytes = generate_pdf(project_name="", deliverable_type="", project_slug="")
    # Sem fill, q5 mantém "Selecione..." default
    answers = extract_answers_from_pdf(pdf_bytes)
    assert "Q5" not in answers


def test_extract_full_cycle_preserves_all_answer_types():
    """Sanity end-to-end: preenche ~10 perguntas cobrindo text/single/multi
    e confere que cada uma chegou com o tipo certo."""
    pdf_bytes = generate_pdf(project_name="P", deliverable_type="new_system", project_slug="p")
    values = {
        "q1": "Projeto Final",         # text
        "q3": "Não",                   # single
        "q5": "Alta",                  # single
        "q24": "TypeScript",           # single
    }
    values.update(_multi_to_fields("4", ["Novo sistema"]))
    values.update(_multi_to_fields("22", ["Web SPA", "Portal autenticado"]))
    filled = _fill_pdf(pdf_bytes, values)

    answers = extract_answers_from_pdf(filled)
    assert answers["Q1"] == "Projeto Final"
    assert answers["Q3"] == "Não"
    assert answers["Q5"] == "Alta"
    assert answers["Q24"] == "TypeScript"
    assert answers["Q4"] == ["Novo sistema"]
    assert set(answers["Q22"]) == {"Web SPA", "Portal autenticado"}


# ─── extract_answers_from_text (fallback) ────────────────────────────

def test_extract_from_text_reads_simple_qn_format():
    text = "Q1. Nome do projeto: Foo\nQ3. Altera existente: Não\nQ15. Entregável: API, Microserviço"
    answers = extract_answers_from_text(text)
    assert answers["Q1"].startswith("Nome do projeto:")  # regex greedy — ok por ser fallback
    assert "Não" in answers["Q3"]


def test_extract_from_text_splits_multi_on_commas():
    """Quando o tipo da pergunta é `multi` e há vírgulas, divide em lista."""
    text = "Q15. API, Microserviço"
    answers = extract_answers_from_text(text)
    assert isinstance(answers["Q15"], list)
    assert "API" in answers["Q15"]
    assert "Microserviço" in answers["Q15"]


def test_extract_from_text_returns_empty_on_no_matches():
    assert extract_answers_from_text("sem perguntas aqui") == {}
