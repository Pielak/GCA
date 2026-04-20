"""MVP 8 Fase 4 — Normalização heurística de seções implícitas.

A Fase 5 já detecta por regex `RF-\\d+`, `RNF-\\d+` e "Módulo X" quando
o autor usa prefixos explícitos. Fase 4 amplia pra captar seções sem
prefixo:

  - **implicit_requirements**: frases normativas "o sistema deve X",
    "o usuário pode Y" — sem rótulo RF.
  - **deliverables_hints**: frases de produção "será entregue X",
    "entregável: Y".
  - **phases_hints**: cronograma "Fase 1", "Sprint 3", "Etapa N".

Heurística pura (regex), sem LLM — determinístico e sem custo.

Shape do `extraction_report` é backward-compat: só adiciona chaves.
Testes existentes (Fase 5 + Fase 6) continuam passando.
"""
import pytest

from app.services.extraction_report_service import (
    DELIVERABLE_PATTERNS, IMPLICIT_REQ_PATTERN, PHASE_PATTERNS,
    _normalize_match, build_extraction_report,
)


# ============================================================================
# Requisitos implícitos — frases normativas
# ============================================================================

def test_implicit_req_frase_basica():
    """'O sistema deve validar entrada do usuário' → detectado."""
    text = "Relatório.\nO sistema deve validar todas as entradas do usuário antes de processar."
    matches = IMPLICIT_REQ_PATTERN.findall(text)
    assert len(matches) == 1
    assert "deve validar" in matches[0].lower()


def test_implicit_req_multiplas_variacoes():
    """Aceita deve, pode, poderá, precisa, é obrigatório."""
    text = """
O usuário deve poder fazer login com email e senha.
O sistema poderá bloquear usuários após 5 tentativas.
A aplicação precisa suportar autenticação multifator.
O administrador tem que aprovar novos cadastros.
É obrigatório registrar timestamp em toda operação.
"""
    matches = IMPLICIT_REQ_PATTERN.findall(text)
    assert len(matches) >= 4  # "É obrigatório" não começa com O/A/Os/As


def test_implicit_req_ignora_frase_muito_curta():
    """Frase com pouco contexto (< 10 chars após verbo) não conta."""
    text = "O sistema deve X."
    matches = IMPLICIT_REQ_PATTERN.findall(text)
    # Padrão exige {10,200} de contexto — X é curto
    assert len(matches) == 0


def test_implicit_req_nao_detecta_pergunta_ou_exclamacao():
    """Padrão começa no início da linha ou após ponto — filtros naturais."""
    text = "isso é uma frase? o sistema deve algo que não importa"
    # Match só quando começa após \n ou ponto — "o sistema deve" no meio não dispara
    # (regex tem `(?:^|(?<=[\.\n]))\s*(?:O|A|...)` — precisa do O maiúsculo)
    matches = IMPLICIT_REQ_PATTERN.findall(text)
    assert len(matches) == 0


def test_report_implicit_requirements_no_dogfood():
    """Doc v2.0 tem tanto RFs explícitos quanto afirmações normativas."""
    text = """
Especificação do sistema.

RF-001: Login com email.

O sistema deve armazenar tokens por no máximo 30 minutos.
O usuário pode recuperar senha por email de confirmação.
A aplicação precisa criptografar senhas com bcrypt rounds >= 12.
"""
    report = build_extraction_report(text.encode("utf-8"), "txt")
    # RFs explícitos continuam detectados
    assert "RF-001" in report["requirements_functional"]
    # Implicit agora também
    assert len(report["implicit_requirements"]) >= 3


# ============================================================================
# Entregáveis
# ============================================================================

def test_deliverable_pattern_verbos_producao():
    """'Será entregue...', 'Será produzido...', 'Entregável: ...'"""
    text = """
Ao final do projeto:
Será entregue o código fonte completo.
Será produzido documentação técnica em português.
Entregável: relatório de testes com 80% de cobertura.
Deliverable: pipeline CI/CD configurado.
"""
    matches: list[str] = []
    for pat in DELIVERABLE_PATTERNS:
        matches.extend(pat.findall(text))
    assert len(matches) >= 3


def test_report_deliverables_hints_populado():
    text = (
        "Será entregue o código fonte em GitHub.\n"
        "Entregável: documentação em markdown.\n"
        "Serão produzidas evidências de teste UAT."
    )
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert len(report["deliverables_hints"]) >= 2


def test_report_deliverables_vazio_quando_doc_nao_tem():
    """Doc sem frases de produção → lista vazia, sem warning."""
    text = "Apenas texto descritivo do projeto, sem promessas."
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert report["deliverables_hints"] == []


# ============================================================================
# Fases / cronograma
# ============================================================================

def test_phase_pattern_fase_numerica():
    """'Fase 1', 'Sprint 3', 'Etapa 2' detectados."""
    text = """
Planejamento:
Fase 1: Setup do ambiente.
Sprint 2: Implementação core.
Etapa 3 - Testes integrados.
Marco 4: go-live.
"""
    matches: list[str] = []
    for pat in PHASE_PATTERNS:
        matches.extend(pat.findall(text))
    assert len(matches) >= 3


def test_phase_pattern_ordinal():
    """'1ª fase', '2º sprint' também detectados."""
    text = "A 1ª fase inicia setup. A 2ª fase cobre features."
    found = []
    for pat in PHASE_PATTERNS:
        found.extend(pat.findall(text))
    assert len(found) >= 2


def test_report_phases_hints_dogfood_style():
    text = """
Cronograma:
Fase 1: Fundação (2 meses).
Fase 2: Features principais (4 meses).
Fase 3: Go-live (1 mês).
"""
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert len(report["phases_hints"]) >= 3


def test_report_phases_vazio_quando_sem_cronograma():
    text = "Descrição do projeto sem datas ou fases explícitas."
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert report["phases_hints"] == []


# ============================================================================
# Shape estável + backward compat
# ============================================================================

def test_report_shape_inclui_novas_chaves():
    """Frontend da Fase 5 depende de shape estável. Chaves novas são
    aditivas — as antigas continuam presentes."""
    report = build_extraction_report(b"", "pdf")
    must_have = {
        "ok", "file_type", "chars", "paragraphs", "tables_detected",
        "text_boxes", "headers_footers", "pdf_layers",
        "pdf_pages_with_text", "acroform_fields",
        "requirements_functional", "requirements_non_functional",
        "module_hints", "warnings", "text_sample",
        # Fase 4
        "implicit_requirements", "deliverables_hints", "phases_hints",
    }
    assert set(report.keys()) >= must_have


def test_report_shape_novas_chaves_sempre_listas():
    """Mesmo doc vazio: chaves novas são [] (não None)."""
    report = build_extraction_report(b"", "pdf")
    assert isinstance(report["implicit_requirements"], list)
    assert isinstance(report["deliverables_hints"], list)
    assert isinstance(report["phases_hints"], list)


# ============================================================================
# Dedup e limites
# ============================================================================

def test_implicit_requirements_nao_duplica():
    """Mesma frase repetida 3x vira 1 item."""
    text = "\n".join(["O sistema deve validar entrada antes de persistir."] * 3)
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert len(report["implicit_requirements"]) == 1


def test_implicit_requirements_respeita_limit_10():
    """20 requisitos implícitos distintos → só 10 no preview."""
    sentences = [
        f"O sistema deve executar operação número {i} com validação completa de entrada do usuário."
        for i in range(20)
    ]
    text = "\n".join(sentences)
    report = build_extraction_report(text.encode("utf-8"), "txt", max_preview_items=10)
    assert len(report["implicit_requirements"]) == 10


# ============================================================================
# _normalize_match helper
# ============================================================================

def test_normalize_match_compacta_whitespace():
    assert _normalize_match("  a   b\t\tc  ") == "a b c"


def test_normalize_match_trima_pontuacao_solta():
    assert _normalize_match(";a b.") == "a b"
    assert _normalize_match("—texto—") == "texto"


def test_normalize_match_vazio():
    assert _normalize_match("") == ""
    assert _normalize_match(None or "") == ""


# ============================================================================
# Retrocompat com Fase 5/6 (não quebra existentes)
# ============================================================================

def test_fase5_rfs_ainda_funcionam():
    """Heurística de RF- / RNF- / Módulo continua intacta."""
    text = "RF-001: Login.\nRNF-005: Performance < 2s.\nMódulo autenticação central."
    report = build_extraction_report(text.encode("utf-8"), "txt")
    assert "RF-001" in report["requirements_functional"]
    assert "RNF-005" in report["requirements_non_functional"]
    assert any("autenticação" in m.lower() for m in report["module_hints"])
