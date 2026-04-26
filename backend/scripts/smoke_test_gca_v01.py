#!/usr/bin/env python3
"""
Script de Smoke Test para GCA v0.1

Testa o pipeline completo sem fazer requests a API real:
  1. Cria documento simulado
  2. Chama M01Service (gera questionnaire)
  3. Simula respostas do user
  4. Chama PersonasConsolidator (5 personas validam)
  5. Verifica integridade do output

Tempo: ~2s
Dependências: M01Service, PersonasConsolidator (já implementados)
"""

import sys
import json
import time
from pathlib import Path
from unittest.mock import Mock

# Adicionar backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.m01_service import M01Service, GeneratedQuestionnaire
from app.services.persona_validator import PersonasConsolidator


def generate_sample_document():
    """Gera documento simulado de teste"""
    return """
SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA (AJA) v3.0

Objetivo Principal:
Plataforma web para auxiliar advogados a gerar documentos jurídicos com IA.

Requisitos Funcionais:
1. Login seguro com 2FA
2. Geração automática de contratos
3. Integração com DataJud API
4. Versionamento de documentos
5. Auditoria completa

Requisitos Não-Funcionais:
- Performance: < 2 segundos (P99)
- Disponibilidade: 99.5% uptime
- Escalabilidade: 10.000 usuários simultâneos
- LGPD compliance obrigatório
- Assinatura digital ICP-Brasil

Stack:
- Backend: Python FastAPI
- Frontend: React 18
- Database: PostgreSQL
- Cache: Redis
- IA: Claude

Timeline: 6 meses MVP
"""


def mock_m01_response():
    """Gera resposta simulada do Anthropic API para M01"""
    return {
        "questions": [
            {
                "id": f"M01_Q{i}",
                "text": f"Pergunta {i}: " + (
                    "Qual é o objetivo principal?" if i == 1 else
                    "Quais tecnologias backend?" if i == 2 else
                    "Requisitos de compliance?" if i == 3 else
                    f"Requisito técnico {i}"
                ),
                "tipo": "aberta" if i % 3 != 0 else "escolha",
                "opcoes": ["Opção A", "Opção B"] if i % 3 == 0 else None,
                "obrigatoria": True,
                "dica": "Detalhe sua resposta" if i < 5 else None
            }
            for i in range(1, 36)  # 35 questões
        ],
        "extracted_concepts": [
            "automação",
            "documentos jurídicos",
            "compliance",
            "LGPD",
            "assinatura digital",
            "performance",
            "escalabilidade"
        ],
        "gaps_identified": [
            "Timeline parcialmente vaga",
            "Estratégia de backup não mencionada",
            "Plano de disaster recovery faltando"
        ],
        "total_questions": 35
    }


def mock_m01_service():
    """Cria M01Service com Anthropic mockado"""
    mock_client = Mock()

    response_data = mock_m01_response()
    mock_msg = Mock()
    mock_msg.content = [Mock(text=json.dumps(response_data))]
    mock_client.messages.create.return_value = mock_msg

    return M01Service(anthropic_client=mock_client)


def generate_sample_responses(question_count):
    """Gera respostas simuladas do user para as questões"""
    return {
        f"M01_Q{i}": f"Resposta #{i}: " + (
            "Automação jurídica para gerar contratos com IA" if i == 1 else
            "Python FastAPI + PostgreSQL + React 18 + Redis + Celery" if i == 2 else
            "LGPD compliance, assinatura digital ICP-Brasil, auditoria" if i == 3 else
            f"Detalhamento técnico para a questão {i}"
        )
        for i in range(1, question_count + 1)
    }


def run_smoke_test():
    """Executa o teste completo"""

    print("\n" + "=" * 80)
    print("SMOKE TEST GCA v0.1 — Pipeline Completo")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 1: M01Service gera questionnaire
    # ──────────────────────────────────────────────────────────────────────────

    print("\n[1/4] M01Service gerando questionnaire...")
    start = time.time()

    m01 = mock_m01_service()
    doc = generate_sample_document()

    try:
        questionnaire = m01.generate_questionnaire(
            document_text=doc,
            domain="juridico",
            doc_type="requisitos"
        )
        elapsed = time.time() - start

        print(f"  ✅ Questionnaire gerado em {elapsed:.2f}s")
        print(f"  → {questionnaire.count} questões (esperado: 30-50)")
        print(f"  → {len(questionnaire.extracted_concepts)} conceitos extraídos")
        print(f"  → {len(questionnaire.gaps_identified)} gaps identificados")
        print(f"  → iteration_id: {questionnaire.iteration_id}")

        assert 30 <= questionnaire.count <= 50, f"❌ Count fora de range: {questionnaire.count}"
        assert len(questionnaire.extracted_concepts) > 0, "❌ Nenhum conceito extraído"
        assert len(questionnaire.gaps_identified) > 0, "❌ Nenhum gap identificado"
        print("  ✅ Validações passaram")

    except Exception as e:
        print(f"  ❌ Erro: {e}")
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 2: User responde
    # ──────────────────────────────────────────────────────────────────────────

    print("\n[2/4] Simulando respostas do user...")
    responses = generate_sample_responses(questionnaire.count)
    print(f"  ✅ {len(responses)} respostas geradas")

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 3: Personas validam
    # ──────────────────────────────────────────────────────────────────────────

    print("\n[3/4] Personas validando respostas...")
    start = time.time()

    try:
        consolidator = PersonasConsolidator()

        # Mock dos clientes Anthropic de cada Persona
        for persona in consolidator.personas:
            mock_client = Mock()
            approval_response = {
                "status": "approved",
                "decision": "Respostas adequadas para o domínio jurídico",
                "ocg_delta": {"secao": "validado"},
                "severity": "info"
            }
            mock_msg = Mock()
            mock_msg.content = [Mock(text=json.dumps(approval_response))]
            mock_client.messages.create.return_value = mock_msg
            persona.client = mock_client

        result = consolidator.validate_all(
            responses=responses,
            extracted_concepts=questionnaire.extracted_concepts,
            document_domain="juridico"
        )
        elapsed = time.time() - start

        print(f"  ✅ Validação concluída em {elapsed:.2f}s")
        print(f"  → {len(result.results)} personas responderam (esperado: 5)")

        approved_count = sum(1 for r in result.results if r.status == "approved")
        print(f"  → {approved_count}/5 personas aprovaram")

        for persona_result in result.results:
            status_icon = "✅" if persona_result.status == "approved" else "⚠️ "
            print(f"    {status_icon} {persona_result.persona}: {persona_result.status}")

        assert len(result.results) == 5, f"❌ Esperava 5 personas, got {len(result.results)}"
        print("  ✅ Validações passaram")

    except Exception as e:
        print(f"  ❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # FASE 4: Verificar output
    # ──────────────────────────────────────────────────────────────────────────

    print("\n[4/4] Validando integridade do output...")

    checks = [
        ("M01 count em range", 30 <= questionnaire.count <= 50),
        ("Conceitos extraídos", len(questionnaire.extracted_concepts) > 0),
        ("Gaps identificados", len(questionnaire.gaps_identified) > 0),
        ("Iteration ID gerado", questionnaire.iteration_id is not None),
        ("5 Personas responderam", len(result.results) == 5),
        ("5/5 aprovaram", approved_count == 5),
        ("next_action correto", result.next_action == "aggregate_to_ocg"),
    ]

    all_passed = True
    for check_name, check_result in checks:
        icon = "✅" if check_result else "❌"
        print(f"  {icon} {check_name}")
        if not check_result:
            all_passed = False

    # ──────────────────────────────────────────────────────────────────────────
    # RESULTADO
    # ──────────────────────────────────────────────────────────────────────────

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ SMOKE TEST PASSOU — GCA v0.1 pronto para teste com usuário")
    else:
        print("❌ SMOKE TEST FALHOU — Verifique os erros acima")
    print("=" * 80 + "\n")

    return all_passed


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
