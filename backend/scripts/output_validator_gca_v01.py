#!/usr/bin/env python3
"""
Validador de Output para GCA v0.1 Endpoints

Verifica que os outputs dos endpoints estão no formato esperado:
  - M01 endpoint: retorna 30-50 questões com estrutura correta
  - Validator endpoint: retorna 5 personas com decisões válidas

Uso:
  python output_validator_gca_v01.py --test-m01
  python output_validator_gca_v01.py --test-validator
  python output_validator_gca_v01.py --all
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any

# Adicionar backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.m01_service import M01Service, GeneratedQuestionnaire, Question
from app.services.persona_validator import PersonasConsolidator, ValidationResult
from unittest.mock import Mock


# ─────────────────────────────────────────────────────────────────────────────
# VALIDADORES M01
# ─────────────────────────────────────────────────────────────────────────────

class M01OutputValidator:
    """Validador para outputs do M01Service"""

    @staticmethod
    def validate_question(q: Any, idx: int) -> List[str]:
        """Valida estrutura de uma questão individual (dict ou dataclass)"""
        errors = []

        # Converter dataclass para dict se necessário
        if hasattr(q, '__dataclass_fields__'):
            q_dict = {k: getattr(q, k) for k in q.__dataclass_fields__}
        else:
            q_dict = q

        # Campos obrigatórios
        required_fields = ["id", "text", "tipo", "obrigatoria"]
        for field in required_fields:
            if field not in q_dict:
                errors.append(f"Q[{idx}] campo obrigatório faltando: {field}")

        # Validar tipos
        if "id" in q_dict and not isinstance(q_dict["id"], str):
            errors.append(f"Q[{idx}] 'id' deve ser string, got {type(q_dict['id'])}")

        if "text" in q_dict and not isinstance(q_dict["text"], str):
            errors.append(f"Q[{idx}] 'text' deve ser string, got {type(q_dict['text'])}")

        if "tipo" in q_dict:
            tipos_validos = ["aberta", "escolha", "múltipla"]
            if q_dict["tipo"] not in tipos_validos:
                errors.append(f"Q[{idx}] 'tipo' inválido: {q_dict['tipo']}. Esperado: {tipos_validos}")

        if "obrigatoria" in q_dict and not isinstance(q_dict["obrigatoria"], bool):
            errors.append(f"Q[{idx}] 'obrigatoria' deve ser boolean, got {type(q_dict['obrigatoria'])}")

        # Validar opcoes (só obrigatório se tipo='escolha')
        if "tipo" in q_dict:
            if q_dict["tipo"] in ["escolha", "múltipla"]:
                if "opcoes" not in q_dict or q_dict["opcoes"] is None:
                    errors.append(f"Q[{idx}] 'opcoes' obrigatória para tipo={q_dict['tipo']}")
                elif not isinstance(q_dict["opcoes"], list):
                    errors.append(f"Q[{idx}] 'opcoes' deve ser list, got {type(q_dict['opcoes'])}")

        return errors

    @staticmethod
    def validate_questionnaire(questionnaire: GeneratedQuestionnaire) -> List[str]:
        """Valida GeneratedQuestionnaire completo"""
        errors = []

        # Validar count
        if not (30 <= questionnaire.count <= 50):
            errors.append(f"count fora de range: {questionnaire.count} (esperado: 30-50)")

        # Validar questões
        if len(questionnaire.questions) != questionnaire.count:
            errors.append(f"count={questionnaire.count} mas len(questions)={len(questionnaire.questions)}")

        # Validar cada questão
        for idx, q in enumerate(questionnaire.questions):
            q_errors = M01OutputValidator.validate_question(q, idx)
            errors.extend(q_errors)

        # Validar conceitos
        if not isinstance(questionnaire.extracted_concepts, list):
            errors.append(f"extracted_concepts deve ser list, got {type(questionnaire.extracted_concepts)}")
        elif len(questionnaire.extracted_concepts) == 0:
            errors.append("extracted_concepts vazio (esperado: ≥ 1)")

        # Validar gaps
        if not isinstance(questionnaire.gaps_identified, list):
            errors.append(f"gaps_identified deve ser list, got {type(questionnaire.gaps_identified)}")

        # Validar iteration_id
        if questionnaire.iteration_id is None:
            errors.append("iteration_id é None (obrigatório)")

        return errors


# ─────────────────────────────────────────────────────────────────────────────
# VALIDADORES PERSONA
# ─────────────────────────────────────────────────────────────────────────────

class PersonaOutputValidator:
    """Validador para outputs do PersonasConsolidator"""

    VALID_PERSONAS = [
        "GP (Gerente de Projetos)",
        "Arquiteto de Soluções",
        "DBA (Especialista em Dados)",
        "Dev Senior",
        "QA (Qualidade)"
    ]

    VALID_STATUSES = ["approved", "needs_clarification", "rejected"]
    VALID_SEVERITIES = ["info", "warning", "error"]

    @staticmethod
    def validate_single_result(result: ValidationResult, idx: int) -> List[str]:
        """Valida um ValidationResult individual"""
        errors = []

        # Validar persona
        if result.persona not in PersonaOutputValidator.VALID_PERSONAS:
            errors.append(f"Result[{idx}] persona inválida: {result.persona}")

        # Validar status
        if result.status not in PersonaOutputValidator.VALID_STATUSES:
            errors.append(f"Result[{idx}] status inválido: {result.status}")

        # Validar decision
        if not isinstance(result.decision, str) or len(result.decision) == 0:
            errors.append(f"Result[{idx}] decision vazio ou inválido")

        # Validar severity
        if result.severity not in PersonaOutputValidator.VALID_SEVERITIES:
            errors.append(f"Result[{idx}] severity inválida: {result.severity}")

        return errors

    @staticmethod
    def validate_consolidated(consolidated) -> List[str]:
        """Valida ConsolidatedValidation completo"""
        errors = []

        # Validar count de personas
        if len(consolidated.results) != 5:
            errors.append(f"Esperava 5 personas, got {len(consolidated.results)}")

        # Validar cada resultado
        for idx, result in enumerate(consolidated.results):
            r_errors = PersonaOutputValidator.validate_single_result(result, idx)
            errors.extend(r_errors)

        # Validar next_action
        valid_next_actions = ["aggregate_to_ocg", "generate_followup_questionnaire", "manual_review"]
        if consolidated.next_action not in valid_next_actions:
            errors.append(f"next_action inválida: {consolidated.next_action}")

        # Validar all_approved consistency
        approved_count = sum(1 for r in consolidated.results if r.status == "approved")
        if consolidated.all_approved != (approved_count == 5):
            errors.append(f"all_approved={consolidated.all_approved} mas apenas {approved_count}/5 aprovaram")

        return errors


# ─────────────────────────────────────────────────────────────────────────────
# TESTES
# ─────────────────────────────────────────────────────────────────────────────

def test_m01_output():
    """Testa output do M01Service"""
    print("\n" + "=" * 80)
    print("VALIDANDO OUTPUT: M01Service")
    print("=" * 80)

    # Mock Anthropic
    mock_client = Mock()
    response_data = {
        "questions": [
            {
                "id": f"M01_Q{i}",
                "text": f"Pergunta {i}",
                "tipo": "aberta" if i % 2 == 0 else "escolha",
                "opcoes": None if i % 2 == 0 else ["A", "B"],
                "obrigatoria": True,
                "dica": None
            }
            for i in range(1, 36)
        ],
        "extracted_concepts": ["conceito1", "conceito2", "conceito3"],
        "gaps_identified": ["gap1", "gap2"],
        "total_questions": 35
    }
    mock_msg = Mock()
    mock_msg.content = [Mock(text=json.dumps(response_data))]
    mock_client.messages.create.return_value = mock_msg

    m01 = M01Service(anthropic_client=mock_client)
    questionnaire = m01.generate_questionnaire(
        document_text="Doc de teste" * 100,
        domain="juridico",
        doc_type="requisitos"
    )

    # Validar
    errors = M01OutputValidator.validate_questionnaire(questionnaire)

    if errors:
        print("❌ ERROS ENCONTRADOS:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("✅ M01 output válido:")
        print(f"  - count: {questionnaire.count}")
        print(f"  - questões: {len(questionnaire.questions)}")
        print(f"  - conceitos: {len(questionnaire.extracted_concepts)}")
        print(f"  - gaps: {len(questionnaire.gaps_identified)}")
        return True


def test_validator_output():
    """Testa output do PersonasConsolidator"""
    print("\n" + "=" * 80)
    print("VALIDANDO OUTPUT: PersonasConsolidator")
    print("=" * 80)

    consolidator = PersonasConsolidator()

    # Mock Anthropic para cada persona
    for persona in consolidator.personas:
        mock_client = Mock()
        approval_response = {
            "status": "approved",
            "decision": "Validação OK",
            "ocg_delta": {"test": "data"},
            "severity": "info"
        }
        mock_msg = Mock()
        mock_msg.content = [Mock(text=json.dumps(approval_response))]
        mock_client.messages.create.return_value = mock_msg
        persona.client = mock_client

    result = consolidator.validate_all(
        responses={f"Q{i}": f"Resposta {i}" for i in range(1, 36)},
        extracted_concepts=["conceito1", "conceito2"],
        document_domain="juridico"
    )

    # Validar
    errors = PersonaOutputValidator.validate_consolidated(result)

    if errors:
        print("❌ ERROS ENCONTRADOS:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("✅ PersonasConsolidator output válido:")
        print(f"  - personas: {len(result.results)}")
        print(f"  - aprovadas: {sum(1 for r in result.results if r.status == 'approved')}")
        print(f"  - next_action: {result.next_action}")
        return True


def main():
    parser = argparse.ArgumentParser(description="Validador de Output GCA v0.1")
    parser.add_argument("--test-m01", action="store_true", help="Testar M01 output")
    parser.add_argument("--test-validator", action="store_true", help="Testar Validator output")
    parser.add_argument("--all", action="store_true", help="Testar tudo (default)")

    args = parser.parse_args()

    if not any([args.test_m01, args.test_validator, args.all]):
        args.all = True

    results = []

    if args.test_m01 or args.all:
        results.append(("M01 Output", test_m01_output()))

    if args.test_validator or args.all:
        results.append(("Validator Output", test_validator_output()))

    # Sumário
    print("\n" + "=" * 80)
    print("SUMÁRIO")
    print("=" * 80)
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"{icon} {name}")

    print("=" * 80 + "\n")

    all_passed = all(passed for _, passed in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
