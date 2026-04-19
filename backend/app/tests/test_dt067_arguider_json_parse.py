"""DT-067 — Parse robusto do JSON retornado pelo LLM no Arguidor.

Bug dogfood 2026-04-19: Claude Haiku respondeu JSON envolto em code
fences (```json ... ```). O `_extract_json` antigo tentava json.loads
do texto cru, falhava; o regex fallback `\\{.*\\}` em DOTALL pegava
até o último `}` do documento inteiro (incluindo blocos após o JSON
válido) e também falhava no json.loads. Resultado: retornava `{}`
silenciosamente, análise persistida com gaps=[], show_stoppers=[],
module_candidates=[] → Arguidor UI vazio, Roadmap vazio, pipeline
inteiro invisível ao user.

Este teste valida que o parser agora:
  - Aceita JSON puro.
  - Aceita JSON dentro de ```json ... ``` (formato padrão do Claude).
  - Aceita JSON dentro de ``` ... ``` (sem linguagem).
  - Aceita JSON precedido por preâmbulo em linguagem natural.
  - Usa contagem de chaves balanceadas em vez de regex gananciosa.
  - Lida com strings contendo `{` e `}` sem contar como nesting.
  - Retorna {} e loga texto completo quando realmente não há JSON válido.
"""
import pytest

from app.services.arguider_service import DocumentExtractor

# _extract_json é staticmethod no ArguiderService, não no DocumentExtractor.
# Vou importar a classe certa:
from app.services.arguider_service import ArguiderService


def _parse(text: str) -> dict:
    return ArguiderService._extract_json(text)


def test_json_puro():
    """Caso feliz: LLM retornou JSON sem adornos."""
    result = _parse('{"gaps": [{"id": "G1"}], "show_stoppers": []}')
    assert result["gaps"][0]["id"] == "G1"
    assert result["show_stoppers"] == []


def test_json_dentro_de_code_fence_json():
    """Formato padrão do Claude: ```json ... ```"""
    text = '```json\n{"module_candidates": [{"name": "Autenticação"}]}\n```'
    result = _parse(text)
    assert result["module_candidates"][0]["name"] == "Autenticação"


def test_json_dentro_de_code_fence_sem_linguagem():
    """Alguns providers fecham com ``` sem especificar linguagem."""
    text = '```\n{"key": "value"}\n```'
    result = _parse(text)
    assert result["key"] == "value"


def test_json_com_preambulo_natural():
    """LLM escreveu 'Aqui está a análise:' antes do JSON."""
    text = 'Aqui está a análise do documento:\n\n{"gaps": ["g1"]}\n\nFim.'
    result = _parse(text)
    assert result["gaps"] == ["g1"]


def test_strings_com_chaves_literais_nao_confundem_parser():
    """Se o valor de um campo tem '{' ou '}' dentro de string, o
    parser deve contar corretamente e retornar o objeto inteiro."""
    text = '{"template": "function f() { return {}; }", "gaps": []}'
    result = _parse(text)
    assert result["template"] == "function f() { return {}; }"
    assert result["gaps"] == []


def test_string_com_aspas_escapadas_nao_confunde():
    """Aspas escapadas dentro de strings devem ser respeitadas."""
    text = '{"msg": "aspas \\"internas\\" ok", "ok": true}'
    result = _parse(text)
    assert result["msg"] == 'aspas "internas" ok'
    assert result["ok"] is True


def test_json_aninhado_profundo():
    """Estrutura profunda não pode quebrar o parser."""
    text = '{"a": {"b": {"c": {"d": {"e": "deep"}}}}}'
    result = _parse(text)
    assert result["a"]["b"]["c"]["d"]["e"] == "deep"


def test_json_seguido_de_lixo_so_extrai_o_objeto():
    """Se o LLM escreveu JSON + texto depois, extrai só o objeto bem
    formado."""
    text = '{"gaps": [{"id": "G1"}]}\n\nObservação: ignore o campo X.'
    result = _parse(text)
    assert result["gaps"][0]["id"] == "G1"


def test_code_fence_com_trailing_whitespace():
    """Variação real vista no dogfood: whitespace antes/depois do fence."""
    text = '   \n\n```json\n{"ok": 1}\n```   \n'
    result = _parse(text)
    assert result["ok"] == 1


def test_texto_sem_json_retorna_dict_vazio():
    """LLM falou só bobagem em linguagem natural — sem JSON extraível."""
    text = "Desculpe, não consegui analisar este documento."
    result = _parse(text)
    assert result == {}


def test_texto_vazio_retorna_dict_vazio():
    """Resposta vazia do LLM — contrato antigo preservado."""
    assert _parse("") == {}
    assert _parse("   ") == {}


def test_json_invalido_mas_fence_valido_loga_e_retorna_vazio():
    """Fence está lá mas o conteúdo tem sintaxe quebrada. O parser
    não pode retornar algo plausível — retorna {} e o caller vê
    análise vazia (não é o que queremos, mas é o contrato honesto)."""
    text = '```json\n{"gaps": [invalid syntax}\n```'
    result = _parse(text)
    assert result == {}


def test_reproducao_do_bug_dogfood_haiku_multi_campos():
    """Caso concreto do dogfood: Haiku retornou todos os campos do
    schema do Arguidor dentro de ```json...```. Antes da correção,
    isso resultava em {} e persistência com arrays vazios."""
    text = '''```json
{
  "document_classification": {"type": "requirements", "maturity": "medium"},
  "gaps": [
    {"id": "G1", "text": "Stakeholders não identificados", "severity": "high"}
  ],
  "show_stoppers": [
    {"text": "Sem ROI definido", "severity": "critical"}
  ],
  "poor_definitions": [],
  "improvement_suggestions": ["Adicionar métricas de sucesso"],
  "module_candidates": [
    {"name": "Módulo de Peças", "priority": "high"},
    {"name": "Módulo de Dossiê", "priority": "medium"}
  ],
  "ocg_fields_to_update": []
}
```'''
    result = _parse(text)
    assert result["document_classification"]["type"] == "requirements"
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["id"] == "G1"
    assert result["show_stoppers"][0]["severity"] == "critical"
    assert len(result["module_candidates"]) == 2
    assert result["module_candidates"][0]["name"] == "Módulo de Peças"
