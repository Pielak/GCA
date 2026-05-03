"""Testes de blindagem do ParallelEvaluator — resiliência contra crash de personas."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.parallel_evaluator import ParallelEvaluator
from app.services.personas.base import PersonaOutput, PersonaScore


class TestFallbackPersonaOutput:
    def test_creates_degraded_output(self):
        output = ParallelEvaluator._make_fallback_persona_output(
            "gp", passada=1, error="timeout",
        )
        assert output.persona_tag == "gp"
        assert output.passada == 1
        assert output.fallback_used is True
        assert output.error_code == "PAR-EVAL-001"
        assert output.error_message == "timeout"
        assert output.approved is False
        assert output.tentative is True
        assert output.scores.escopo == 50
        assert output.scores.stack == 50

    def test_passada_2_tentative_false(self):
        output = ParallelEvaluator._make_fallback_persona_output(
            "qa", passada=2, error="crash",
        )
        assert output.tentative is False


class TestSafeGatherResults:
    def test_all_success(self):
        outputs = [
            PersonaOutput(
                persona_tag="gp", passada=1,
                scores=PersonaScore(escopo=80),
                approved=True, tentative=True,
            ),
            PersonaOutput(
                persona_tag="arq", passada=1,
                scores=PersonaScore(stack=75),
                approved=True, tentative=True,
            ),
        ]
        results = ParallelEvaluator._safe_gather_results(
            outputs, ["gp", "arq"], passada=1,
        )
        assert len(results) == 2
        assert results["gp"].approved is True
        assert results["arq"].approved is True

    def test_one_crash_produces_fallback(self):
        outputs = [
            PersonaOutput(
                persona_tag="gp", passada=1,
                scores=PersonaScore(escopo=80),
                approved=True, tentative=True,
            ),
            RuntimeError("LLM timeout"),
        ]
        results = ParallelEvaluator._safe_gather_results(
            outputs, ["gp", "arq"], passada=1,
        )
        assert len(results) == 2
        assert results["gp"].approved is True
        assert results["arq"].fallback_used is True
        assert results["arq"].error_code == "PAR-EVAL-001"
        assert "LLM timeout" in results["arq"].error_message

    def test_all_crash_all_fallbacks(self):
        outputs = [
            RuntimeError("crash gp"),
            RuntimeError("crash arq"),
            RuntimeError("crash dev"),
        ]
        results = ParallelEvaluator._safe_gather_results(
            outputs, ["gp", "arq", "dev"], passada=1,
        )
        assert len(results) == 3
        for tag in ["gp", "arq", "dev"]:
            assert results[tag].fallback_used is True
            assert results[tag].scores.escopo == 50

    def test_mixed_success_and_exceptions(self):
        outputs = [
            PersonaOutput(
                persona_tag="dev", passada=1,
                scores=PersonaScore(implementacao=90),
                approved=True, tentative=True,
            ),
            ValueError("invalid state"),
            PersonaOutput(
                persona_tag="ux", passada=1,
                scores=PersonaScore(ux=70),
                approved=False, tentative=True,
            ),
        ]
        results = ParallelEvaluator._safe_gather_results(
            outputs, ["dev", "qa", "ux"], passada=1,
        )
        assert results["dev"].approved is True
        assert results["qa"].fallback_used is True
        assert results["ux"].approved is False  # normal, not a crash
