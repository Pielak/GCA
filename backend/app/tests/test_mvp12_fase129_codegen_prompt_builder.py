"""MVP 12 Fase 12.9 — Builder canônico de prompts CodeGen.

Contrato §7 MVP 12 Fase 12.9:
- `/scaffold` e `/regenerate-file` antes duplicavam montagem de prompt
  (header + REGRA docstrings + stack + arquitetura + formato de resposta).
- `services/codegen_prompt_builder.py` centraliza via
  `build_scaffold_prompt` e `build_regenerate_file_prompt`.
- Esta suite valida estrutura e campos essenciais de cada prompt.
"""
import pytest

from app.services.codegen_prompt_builder import (
    build_scaffold_prompt,
    build_regenerate_file_prompt,
)


# ─── Scaffold ──────────────────────────────────────────────────────────


def test_scaffold_prompt_contem_header_e_regra_docstring():
    p = build_scaffold_prompt(
        project_name="Foo",
        project_slug="foo",
        project_description=None,
        stack=None,
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    assert "engenheiro de software sênior" in p
    assert "scaffold completo" in p
    assert "REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS" in p
    assert "PEP 257" in p
    assert "JSDoc" in p


def test_scaffold_prompt_rende_project_metadata():
    p = build_scaffold_prompt(
        project_name="GCA Dogfood",
        project_slug="gca-dogfood",
        project_description="Descrição do projeto dogfood.",
        stack={"backend": "FastAPI", "frontend": "React"},
        architecture={"style": "Clean"},
        testing={"coverage": 80},
        modules=[{"name": "auth"}, {"name": "users"}],
        arguider_modules=None,
        business_rules=["Regra 1"],
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    assert "Nome: GCA Dogfood" in p
    assert "Slug: gca-dogfood" in p
    assert "Descrição: Descrição do projeto dogfood." in p
    assert '"backend": "FastAPI"' in p
    assert '"style": "Clean"' in p
    assert '"coverage": 80' in p
    assert "auth" in p
    assert "Regra 1" in p


def test_scaffold_prompt_fallbacks_para_valores_vazios():
    p = build_scaffold_prompt(
        project_name="Foo",
        project_slug="foo",
        project_description=None,
        stack=None,
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    assert "Sem descrição" in p
    assert "Python + FastAPI como padrão" in p
    assert "Clean Architecture com camadas service/repository" in p
    assert "Testes unitários e de integração obrigatórios" in p
    assert "Nenhum módulo identificado no OCG" in p
    assert "Sem regras de negócio explícitas" in p
    assert "Nenhum gap identificado" in p
    assert "Nenhum documento ingerido" in p


def test_scaffold_prompt_inclui_formato_multi_arquivo():
    p = build_scaffold_prompt(
        project_name="Foo",
        project_slug="foo",
        project_description=None,
        stack=None,
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=None,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    assert '"files": [' in p
    assert "MÁXIMO 25 arquivos" in p
    assert "Status possíveis" in p
    assert '"complete"' in p


def test_scaffold_prompt_limita_arguider_modules_a_10():
    many = [{"name": f"m{i}"} for i in range(20)]
    p = build_scaffold_prompt(
        project_name="Foo",
        project_slug="foo",
        project_description=None,
        stack=None,
        architecture=None,
        testing=None,
        modules=None,
        arguider_modules=many,
        business_rules=None,
        arguider_gaps=None,
        critical_findings=None,
        compliance=None,
        ingested_docs_context="",
    )
    assert "m0" in p
    assert "m9" in p
    assert "m10" not in p  # parou no índice 9


# ─── Regenerate file ──────────────────────────────────────────────────


def test_regenerate_prompt_contem_header_e_regra_compacta():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/main.py",
        instruction=None,
        current_content=None,
    )
    assert "CONTEÚDO COMPLETO de um único arquivo" in p
    assert "REGRA INEGOCIÁVEL — DOCSTRINGS OBRIGATÓRIAS" in p
    # versão compacta — sem a lista completa de linguagens do scaffold
    assert "- **Python (.py)**" not in p


def test_regenerate_prompt_inclui_path_e_instrucao_default():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/services/payments.py",
        instruction=None,
        current_content=None,
    )
    assert "src/services/payments.py" in p
    assert "Reescreva completamente" in p


def test_regenerate_prompt_inclui_instrucao_custom():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/x.py",
        instruction="Adicionar suporte a Stripe",
        current_content=None,
    )
    assert "Adicionar suporte a Stripe" in p
    assert "Reescreva completamente" not in p


def test_regenerate_prompt_inclui_current_content_quando_presente():
    content = "def foo():\n    pass\n"
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/x.py",
        instruction=None,
        current_content=content,
    )
    assert "Conteúdo Atual" in p
    assert content.strip() in p


def test_regenerate_prompt_omite_current_quando_vazio():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/x.py",
        instruction=None,
        current_content=None,
    )
    assert "Conteúdo Atual" not in p


def test_regenerate_prompt_inclui_formato_single_arquivo():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/x.py",
        instruction=None,
        current_content=None,
    )
    assert '"content"' in p
    assert '"status"' in p
    # Sem "files" (que é do scaffold multi)
    assert '"files":' not in p


def test_regenerate_prompt_fallbacks_compactos():
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/x.py",
        instruction=None,
        current_content=None,
    )
    # Stack compacta é "Não definida", não "Não definida — use Python + FastAPI como padrão"
    assert "Não definida" in p
    assert "Python + FastAPI como padrão" not in p
    # Arquitetura compacta é "Padrão: Clean Architecture" sem sufixo
    assert "Clean Architecture com camadas" not in p


def test_regenerate_prompt_trunca_current_content_longo():
    """current_content > 6000 chars é truncado para caber no prompt."""
    long = "Z" * 10000
    p = build_regenerate_file_prompt(
        project_name="Foo",
        project_description=None,
        stack=None,
        architecture=None,
        path="src/arquivo.py",
        instruction=None,
        current_content=long,
    )
    # O conteúdo tem 10000 Z's, mas prompt só leva 6000 (slice [:6000])
    assert p.count("Z") == 6000
