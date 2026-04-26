"""Testes de PersonaValidator — Análise de respostas por Personas

Alinhado a GCA_CANONICAL_CONTRACT.md e Task 2 do plano GCA v0.1:
- Cada Persona (GP, Arquiteto, DBA, Dev Sr, QA) valida respostas
- Saída: aprovação OU novas questões de clarificação
"""
import pytest
import json
from unittest.mock import Mock, patch
from app.services.persona_validator import (
    PersonaValidator,
    GPValidator,
    ArquitetoValidator,
    DBAValidator,
    DevSrValidator,
    QAValidator,
    PersonasConsolidator,
    ValidationResult,
    ConsolidatedValidation,
    create_personas_consolidator
)


class TestPersonaValidators:
    """Suite de testes para cada Persona"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Mock do cliente Anthropic com resposta de aprovação"""
        mock_client = Mock()

        # Resposta de aprovação
        approval_response = {
            "status": "approved",
            "decision": "Respostas claras e suficientes",
            "ocg_delta": {"secao_exemplo": "conteúdo"},
            "followup_questions": None,
            "severity": "info"
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=json.dumps(approval_response))]
        mock_client.messages.create.return_value = mock_message

        return mock_client

    @pytest.fixture
    def sample_responses(self):
        """Respostas de exemplo do questionário"""
        return {
            "M01_Q1": "Plataforma web para automação de documentos jurídicos",
            "M01_Q2": "Alta (produção, >1000 users, compliance crítico)",
            "M01_Q3": "Python FastAPI, PostgreSQL, React, AWS",
            "M01_Q4": "6 meses",
            "M01_Q5": "R$ 500k"
        }

    @pytest.fixture
    def sample_concepts(self):
        """Conceitos extraídos do documento"""
        return ["automação", "documentos", "jurídico", "compliance", "LGPD"]

    def test_gp_validator_approve(self, mock_anthropic_client, sample_responses, sample_concepts):
        """GP aprova respostas válidas de escopo/viabilidade"""
        validator = GPValidator(anthropic_client=mock_anthropic_client)
        result = validator.validate(sample_responses, sample_concepts, document_domain="juridico")

        assert isinstance(result, ValidationResult)
        assert result.persona == "GP (Gerente de Projetos)"
        assert result.status == "approved"
        assert result.decision != ""
        assert result.ocg_delta != {}
        assert result.severity == "info"

    def test_gp_validator_has_correct_prompt(self, mock_anthropic_client, sample_responses, sample_concepts):
        """GP validator deve ter prompts sobre escopo/viabilidade"""
        validator = GPValidator(anthropic_client=mock_anthropic_client)
        prompt = validator.get_validation_prompt()

        assert "ESCOPO" in prompt
        assert "VIABILIDADE" in prompt
        assert "STAKEHOLDERS" in prompt

    def test_arquiteto_validator_approve(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Arquiteto aprova respostas válidas de stack/arquitetura"""
        validator = ArquitetoValidator(anthropic_client=mock_anthropic_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.persona == "Arquiteto de Soluções"
        assert result.status == "approved"

    def test_arquiteto_validator_has_correct_prompt(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Arquiteto deve validar stack e padrões"""
        validator = ArquitetoValidator(anthropic_client=mock_anthropic_client)
        prompt = validator.get_validation_prompt()

        assert "STACK" in prompt
        assert "PADRÕES" in prompt

    def test_dba_validator_approve(self, mock_anthropic_client, sample_responses, sample_concepts):
        """DBA aprova respostas válidas de dados/persistência"""
        validator = DBAValidator(anthropic_client=mock_anthropic_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.persona == "DBA (Especialista em Dados)"
        assert result.status == "approved"

    def test_dba_validator_has_correct_prompt(self, mock_anthropic_client, sample_responses, sample_concepts):
        """DBA deve validar schema, retenção, performance"""
        validator = DBAValidator(anthropic_client=mock_anthropic_client)
        prompt = validator.get_validation_prompt()

        assert "DATABASE" in prompt
        assert "RETENÇÃO" in prompt
        assert "LGPD" in prompt or "COMPLIANCE" in prompt

    def test_dev_sr_validator_approve(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Dev Sr aprova respostas com implementabilidade realista"""
        validator = DevSrValidator(anthropic_client=mock_anthropic_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.persona == "Dev Senior"
        assert result.status == "approved"

    def test_dev_sr_validator_has_correct_prompt(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Dev Sr deve validar implementabilidade e timeline"""
        validator = DevSrValidator(anthropic_client=mock_anthropic_client)
        prompt = validator.get_validation_prompt()

        assert "FEATURES" in prompt
        assert "timeline" in prompt.lower()

    def test_qa_validator_approve(self, mock_anthropic_client, sample_responses, sample_concepts):
        """QA aprova respostas com testes viáveis"""
        validator = QAValidator(anthropic_client=mock_anthropic_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.persona == "QA (Qualidade)"
        assert result.status == "approved"

    def test_qa_validator_has_correct_prompt(self, mock_anthropic_client, sample_responses, sample_concepts):
        """QA deve validar testabilidade e critérios"""
        validator = QAValidator(anthropic_client=mock_anthropic_client)
        prompt = validator.get_validation_prompt()

        assert "TESTES" in prompt
        assert "COBERTURA" in prompt

    def test_validator_needs_clarification(self, sample_responses, sample_concepts):
        """Persona pode retornar needs_clarification com followup_questions"""
        mock_client = Mock()

        clarification_response = {
            "status": "needs_clarification",
            "decision": "Stack vago — precisa mais detalhes",
            "ocg_delta": {},
            "followup_questions": [
                {
                    "id": "M01_F1",
                    "text": "Qual versão do FastAPI?",
                    "tipo": "aberta",
                    "opcoes": None,
                    "dica": "ex: 0.104.1 ou latest"
                }
            ],
            "severity": "warning"
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=json.dumps(clarification_response))]
        mock_client.messages.create.return_value = mock_message

        validator = GPValidator(anthropic_client=mock_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.status == "needs_clarification"
        assert result.followup_questions is not None
        assert len(result.followup_questions) > 0
        assert result.severity == "warning"

    def test_validator_handles_json_with_markdown(self, sample_responses, sample_concepts):
        """Validator deve extrair JSON de resposta com markdown fence"""
        mock_client = Mock()

        response_data = {
            "status": "approved",
            "decision": "Ok",
            "ocg_delta": {},
            "severity": "info"
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=f"```json\n{json.dumps(response_data)}\n```")]
        mock_client.messages.create.return_value = mock_message

        validator = GPValidator(anthropic_client=mock_client)
        result = validator.validate(sample_responses, sample_concepts)

        assert result.status == "approved"

    def test_validator_handles_invalid_json(self, sample_responses, sample_concepts):
        """Validator deve degradar graciosamente se JSON inválido"""
        mock_client = Mock()

        mock_message = Mock()
        mock_message.content = [Mock(text="Resposta inválida {{{")]
        mock_client.messages.create.return_value = mock_message

        validator = GPValidator(anthropic_client=mock_client)
        result = validator.validate(sample_responses, sample_concepts)

        # Deve retornar needs_clarification, não falhar
        assert result.status == "needs_clarification"
        assert result.severity == "critical"

    def test_validator_uses_sonnet_4_6(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Validator deve usar claude-sonnet-4-6"""
        validator = GPValidator(anthropic_client=mock_anthropic_client)
        validator.validate(sample_responses, sample_concepts)

        call_args = mock_anthropic_client.messages.create.call_args
        assert call_args[1]["model"] == "claude-sonnet-4-6-20250514"

    def test_validator_uses_max_tokens_2048(self, mock_anthropic_client, sample_responses, sample_concepts):
        """Validator deve usar max_tokens=2048"""
        validator = GPValidator(anthropic_client=mock_anthropic_client)
        validator.validate(sample_responses, sample_concepts)

        call_args = mock_anthropic_client.messages.create.call_args
        assert call_args[1]["max_tokens"] == 2048


class TestPersonasConsolidator:
    """Suite de testes para consolidação de validações"""

    @pytest.fixture
    def mock_anthropic_clients(self):
        """5 mocks, um para cada Persona"""
        mocks = {}

        # Todas aprovam por padrão
        approval_response = {
            "status": "approved",
            "decision": "Respostas ok",
            "ocg_delta": {},
            "severity": "info"
        }

        for persona_name in ["GP", "Arquiteto", "DBA", "Dev", "QA"]:
            mock = Mock()
            mock_msg = Mock()
            mock_msg.content = [Mock(text=json.dumps(approval_response))]
            mock.messages.create.return_value = mock_msg
            mocks[persona_name] = mock

        return mocks

    @pytest.fixture
    def sample_responses(self):
        return {
            "M01_Q1": "Automação jurídica",
            "M01_Q2": "Alta criticidade",
            "M01_Q3": "Python + React",
            "M01_Q4": "6 meses",
            "M01_Q5": "R$ 500k"
        }

    @pytest.fixture
    def sample_concepts(self):
        return ["automação", "jurídico", "compliance"]

    def test_consolidator_all_approved(self, mock_anthropic_clients, sample_responses, sample_concepts):
        """Quando todas 5 Personas aprovam, ready_for_ocg_aggregation=True"""
        consolidator = PersonasConsolidator()

        # Monkey-patch os clientes
        consolidator.personas[0].client = mock_anthropic_clients["GP"]
        consolidator.personas[1].client = mock_anthropic_clients["Arquiteto"]
        consolidator.personas[2].client = mock_anthropic_clients["DBA"]
        consolidator.personas[3].client = mock_anthropic_clients["Dev"]
        consolidator.personas[4].client = mock_anthropic_clients["QA"]

        result = consolidator.validate_all(sample_responses, sample_concepts)

        assert isinstance(result, ConsolidatedValidation)
        assert result.all_approved is True
        assert result.ready_for_ocg_aggregation is True
        assert result.next_action == "aggregate_to_ocg"
        assert len(result.results) == 5

    def test_consolidator_one_needs_clarification(self, mock_anthropic_clients, sample_responses, sample_concepts):
        """Se 1 Persona precisa clarificação, gera followup_questionnaire"""
        clarification_response = {
            "status": "needs_clarification",
            "decision": "Vago",
            "ocg_delta": {},
            "followup_questions": [
                {"id": "M01_F1", "text": "Mais detalhe?", "tipo": "aberta", "opcoes": None, "dica": None}
            ],
            "severity": "warning"
        }

        mock_msg = Mock()
        mock_msg.content = [Mock(text=json.dumps(clarification_response))]
        mock_anthropic_clients["DBA"].messages.create.return_value = mock_msg

        consolidator = PersonasConsolidator()
        consolidator.personas[0].client = mock_anthropic_clients["GP"]
        consolidator.personas[1].client = mock_anthropic_clients["Arquiteto"]
        consolidator.personas[2].client = mock_anthropic_clients["DBA"]
        consolidator.personas[3].client = mock_anthropic_clients["Dev"]
        consolidator.personas[4].client = mock_anthropic_clients["QA"]

        result = consolidator.validate_all(sample_responses, sample_concepts)

        assert result.all_approved is False
        assert result.ready_for_ocg_aggregation is False
        assert result.next_action == "generate_followup_questionnaire"

    def test_consolidator_result_count(self, mock_anthropic_clients, sample_responses, sample_concepts):
        """Consolidador retorna exatamente 5 resultados (uma por Persona)"""
        consolidator = PersonasConsolidator()

        for i, persona in enumerate(consolidator.personas):
            personas_list = list(mock_anthropic_clients.keys())
            persona.client = mock_anthropic_clients[personas_list[i]]

        result = consolidator.validate_all(sample_responses, sample_concepts)

        assert len(result.results) == 5
        personas_names = [r.persona for r in result.results]
        assert "GP (Gerente de Projetos)" in personas_names
        assert "Arquiteto de Soluções" in personas_names
        assert "DBA (Especialista em Dados)" in personas_names
        assert "Dev Senior" in personas_names
        assert "QA (Qualidade)" in personas_names

    def test_consolidator_factory(self):
        """Factory deve criar um PersonasConsolidator válido"""
        with patch('app.services.persona_validator.Anthropic'):
            consolidator = create_personas_consolidator()
            assert isinstance(consolidator, PersonasConsolidator)
            assert len(consolidator.personas) == 5


class TestValidationResult:
    """Testes da dataclass ValidationResult"""

    def test_validation_result_defaults(self):
        """ValidationResult deve ter defaults sensatos"""
        result = ValidationResult(
            persona="gp",
            status="approved",
            decision="Test"
        )

        assert result.persona == "gp"
        assert result.status == "approved"
        assert result.decision == "Test"
        assert result.ocg_delta == {}
        assert result.followup_questions is None
        assert result.severity == "info"

    def test_validation_result_with_delta(self):
        """ValidationResult pode conter delta para OCG"""
        delta = {"stack": "Python + FastAPI"}
        result = ValidationResult(
            persona="arquiteto",
            status="approved",
            decision="Stack ok",
            ocg_delta=delta
        )

        assert result.ocg_delta == delta

    def test_validation_result_with_followups(self):
        """ValidationResult pode conter followup_questions"""
        followups = [
            {"id": "M01_F1", "text": "Pergunta?", "tipo": "aberta", "opcoes": None, "dica": None}
        ]
        result = ValidationResult(
            persona="dba",
            status="needs_clarification",
            decision="Precisa mais detalhe",
            followup_questions=followups
        )

        assert result.followup_questions == followups
