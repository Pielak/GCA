"""Hot-fix MVP 32 — DT-081 fechamento real.

Bug 3 descoberto após merge do PR #4: quando _load_persona_scores produz
fallback (LLM falhou), o fallback antigo montava llm_result sem 'raw_text'
mas com 'changes' (formato simples) — _parse_llm_response tentava
json.loads('') e levantava ValueError. Resultado: ocg_pending mesmo com
fallback funcional.

Fix: fallback agora produz deltas canônicos + marcador _from_fallback=True;
_parse_llm_response detecta o marcador e retorna direto.

Como rodar:
    docker compose exec backend bash -c "cd /app && \\
      TEST_DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      DATABASE_URL=postgresql+asyncpg://gca:gca_secret@postgres:5432/gca_test \\
      pytest app/tests/test_mvp32_fix_parse_fallback.py -v"
"""
import pytest
from unittest.mock import MagicMock

from app.services.ocg_updater_service import OCGUpdaterService


def _make_updater():
    """Constrói updater com db mock — só usamos métodos sync que não tocam DB."""
    return OCGUpdaterService(db=MagicMock())


def test_parse_llm_response_aceita_fallback_sem_raw_text():
    """DT-081 fix: fallback monta llm_result sem raw_text — parser deve aceitar."""
    updater = _make_updater()

    llm_result_fallback = {
        "_from_fallback": True,
        "updated_ocg": {"some": "data"},
        "deltas": [
            {"op": "replace", "path": "PILLAR_SCORES.P1.score", "new_value": 70.5},
            {"op": "replace", "path": "PILLAR_SCORES.P2.score", "new_value": 65.0},
        ],
        "change_type": "EXPAND",
        "context_health": {"depth": 0.5, "confidence": 0.4, "quality": 0.5},
    }

    deltas, change_type, context_health = updater._parse_llm_response(llm_result_fallback)

    assert len(deltas) == 2, f"Esperava 2 deltas, recebeu {len(deltas)}"
    assert deltas[0]["op"] == "replace"
    assert deltas[0]["path"] == "PILLAR_SCORES.P1.score"
    assert deltas[0]["new_value"] == 70.5
    assert change_type == "EXPAND"
    assert context_health == {"depth": 0.5, "confidence": 0.4, "quality": 0.5}


def test_parse_llm_response_caminho_real_llm_continua_funcionando():
    """Não-regressão: llm_result REAL (com raw_text) continua passando pelo JSON parser."""
    updater = _make_updater()

    llm_result_real = {
        "raw_text": (
            '{"deltas": [{"op": "replace", "path": "PILLAR_SCORES.P3.score", '
            '"new_value": 80}], "change_type": "EXPAND", "context_health": '
            '{"depth": 0.7, "confidence": 0.8, "quality": 0.7}}'
        ),
    }

    deltas, change_type, context_health = updater._parse_llm_response(llm_result_real)

    assert len(deltas) == 1
    assert deltas[0]["path"] == "PILLAR_SCORES.P3.score"
    assert deltas[0]["new_value"] == 80
    assert change_type == "EXPAND"
    assert context_health["confidence"] == 0.8


def test_parse_llm_response_fallback_change_type_default_expand():
    """OCG só cresce — fallback sem change_type explícito → EXPAND."""
    updater = _make_updater()

    llm_result_fallback = {
        "_from_fallback": True,
        "updated_ocg": {},
        "deltas": [],
        # change_type ausente
        "context_health": {},
    }

    deltas, change_type, context_health = updater._parse_llm_response(llm_result_fallback)

    assert deltas == []
    assert change_type == "EXPAND", "Fallback sem change_type deve cair em EXPAND (OCG só cresce)"


def test_parse_llm_response_fallback_context_health_default():
    """Fallback sem context_health → defaults canônicos (0.5/0.5/0.5)."""
    updater = _make_updater()

    llm_result_fallback = {
        "_from_fallback": True,
        "deltas": [],
        # context_health ausente
    }

    deltas, change_type, context_health = updater._parse_llm_response(llm_result_fallback)

    assert context_health == {"depth": 0.5, "confidence": 0.5, "quality": 0.5}


def test_parse_llm_response_real_llm_sem_raw_text_levanta_value_error():
    """Não-regressão: llm_result do LLM real SEM raw_text válido continua falhando (ocg_pending)."""
    updater = _make_updater()

    llm_result_invalido = {
        "raw_text": "",  # vazio — sem _from_fallback marker
    }

    with pytest.raises(ValueError, match="JSON"):
        updater._parse_llm_response(llm_result_invalido)


def test_apply_deltas_fallback_aceita_pillar_scores_inicializado():
    """DT-081 fix continuação: deltas do fallback aplicam em ocg_data legado.

    Regressão: ocg_data pré-MVP 31 não tem 'PILLAR_SCORES'. apply_deltas com
    op='replace' falhava com 'segmento não encontrado'. Fix: fallback agora
    inicializa PILLAR_SCORES no current_ocg_data antes de gerar deltas.
    """
    from app.services.ocg_delta_applier import apply_deltas

    # Simula ocg_data legado SEM PILLAR_SCORES
    current_ocg_legacy = {
        "overall_score": 0,
        "blocked": False,
        # NOTA: sem PILLAR_SCORES — situação real do projeto 24bf72c3 pré-fix
    }

    # Fallback inicializa PILLAR_SCORES manualmente (mesma lógica do código)
    current_ocg_legacy["PILLAR_SCORES"] = {
        "P1": {"score": 50},
        "P2": {"score": 50},
        "P3": {"score": 50},
    }

    # Deltas canônicos — chave "new_value" (não "value", que era bug do hot-fix inicial)
    deltas = [
        {"op": "replace", "path": "PILLAR_SCORES.P1.score", "new_value": 70.5},
        {"op": "replace", "path": "PILLAR_SCORES.P2.score", "new_value": 65.0},
        {"op": "replace", "path": "PILLAR_SCORES.P3.score", "new_value": 80.0},
    ]

    result, applied, rejected = apply_deltas(current_ocg_legacy, deltas)

    assert len(applied) == 3, f"Esperava 3 deltas aplicados, recebeu {len(applied)}"
    assert len(rejected) == 0, f"Esperava 0 rejeitados, recebeu {rejected}"
    assert result["PILLAR_SCORES"]["P1"]["score"] == 70.5
    assert result["PILLAR_SCORES"]["P2"]["score"] == 65.0
    assert result["PILLAR_SCORES"]["P3"]["score"] == 80.0
