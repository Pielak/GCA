"""Testes de M01Service — Questionnaire Generator from Requirements Document

Alinhado a GCA_CANONICAL_CONTRACT.md e Task 1 do plano GCA v0.1:
- Lê documento de requisitos
- Extrai contexto e gaps
- Gera 30-50 perguntas dinâmicas
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from app.services.m01_service import M01Service, Question, GeneratedQuestionnaire


class TestM01ServiceGenerateQuestionnaire:
    """Suite de testes para M01Service.generate_questionnaire()"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Mock do cliente Anthropic com resposta estruturada"""
        mock_client = Mock()

        # Resposta válida com 40 questões
        valid_response = {
            "questions": [
                {
                    "id": "M01_Q1",
                    "text": "Qual é o objetivo principal do projeto?",
                    "tipo": "aberta",
                    "opcoes": None,
                    "obrigatoria": True,
                    "dica": "Descreva em 1-2 frases"
                },
                {
                    "id": "M01_Q2",
                    "text": "Qual é a criticidade?",
                    "tipo": "escolha",
                    "opcoes": ["Baixa", "Média", "Alta"],
                    "obrigatoria": True,
                    "dica": None
                }
            ] + [
                {
                    "id": f"M01_Q{i}",
                    "text": f"Pergunta técnica {i}",
                    "tipo": "aberta",
                    "opcoes": None,
                    "obrigatoria": True,
                    "dica": None
                }
                for i in range(3, 41)
            ],
            "extracted_concepts": ["software", "API", "escalabilidade"],
            "gaps_identified": ["falta clareza em NFRs", "timeline vago"],
            "total_questions": 40
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=json.dumps(valid_response))]
        mock_client.messages.create.return_value = mock_message

        return mock_client

    @pytest.fixture
    def sample_document(self):
        """Documento de requisitos de exemplo (AJA-like)"""
        return """
        SISTEMA DE AUTOMAÇÃO JURÍDICA ASSISTIDA (AJA)

        Objetivo: Plataforma web para gerar documentos jurídicos automaticamente.

        Requisitos Funcionais:
        - Login seguro com 2FA
        - Geração de contratos civis
        - Integração com DataJud
        - Auditoria de mudanças

        Requisitos Não-Funcionais:
        - Performance: < 2s resposta
        - Disponibilidade: 99.9%
        - Escala: até 10k usuários
        - Compliance: LGPD, ISO 27001

        Stack Indicado: Python FastAPI, PostgreSQL, React, AWS
        Timeline: 6 meses MVP
        Orçamento: R$ 500k
        """

    def test_generate_questionnaire_success(self, mock_anthropic_client, sample_document):
        """Teste principal: gera questionnaire com 30-50 questões"""
        service = M01Service(anthropic_client=mock_anthropic_client)

        result = service.generate_questionnaire(
            document_text=sample_document,
            domain="juridico",
            doc_type="requisitos",
            iteration_id="test_iter_001"
        )

        # Validações
        assert isinstance(result, GeneratedQuestionnaire)
        assert result.count == 40
        assert len(result.questions) == 40
        assert 30 <= result.count <= 50
        assert result.iteration_id == "test_iter_001"
        assert result.document_domain == "juridico"
        assert len(result.extracted_concepts) > 0
        assert len(result.gaps_identified) > 0

    def test_question_structure(self, mock_anthropic_client, sample_document):
        """Valida estrutura de cada Question"""
        service = M01Service(anthropic_client=mock_anthropic_client)
        result = service.generate_questionnaire(sample_document)

        first_question = result.questions[0]
        assert isinstance(first_question, Question)
        assert first_question.id == "M01_Q1"
        assert first_question.text != ""
        assert first_question.tipo in ["aberta", "escolha", "multipla"]
        assert first_question.obrigatoria is True

        # Questão com escolhas
        second_question = result.questions[1]
        if second_question.tipo == "escolha":
            assert isinstance(second_question.opcoes, list)
            assert len(second_question.opcoes) > 0

    def test_too_short_document_raises_error(self, mock_anthropic_client):
        """Documento muito curto deve rejeitar"""
        service = M01Service(anthropic_client=mock_anthropic_client)

        with pytest.raises(ValueError, match="Document must be at least 200 characters"):
            service.generate_questionnaire("Muito curto")

    def test_too_few_questions_raises_error(self, mock_anthropic_client, sample_document):
        """Se Claude retorna < 30 questões, deve rejeitar"""
        mock_client = Mock()

        # Resposta com apenas 20 questões
        invalid_response = {
            "questions": [
                {"id": f"M01_Q{i}", "text": f"Q{i}", "tipo": "aberta", "opcoes": None, "obrigatoria": True, "dica": None}
                for i in range(1, 21)
            ],
            "extracted_concepts": ["test"],
            "gaps_identified": ["gap1"],
            "total_questions": 20
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=json.dumps(invalid_response))]
        mock_client.messages.create.return_value = mock_message

        service = M01Service(anthropic_client=mock_client)

        with pytest.raises(ValueError, match="Generated only 20 questions, need >= 30"):
            service.generate_questionnaire(sample_document)

    def test_too_many_questions_trimmed(self, mock_anthropic_client, sample_document):
        """Se Claude retorna > 50 questões, deve trimmar para 50"""
        mock_client = Mock()

        # Resposta com 60 questões
        long_response = {
            "questions": [
                {"id": f"M01_Q{i}", "text": f"Q{i}", "tipo": "aberta", "opcoes": None, "obrigatoria": True, "dica": None}
                for i in range(1, 61)
            ],
            "extracted_concepts": ["test"],
            "gaps_identified": ["gap1"],
            "total_questions": 60
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=json.dumps(long_response))]
        mock_client.messages.create.return_value = mock_message

        service = M01Service(anthropic_client=mock_client)
        result = service.generate_questionnaire(sample_document)

        assert result.count == 50
        assert len(result.questions) == 50

    def test_json_parsing_with_markdown_fence(self, sample_document):
        """Claude pode retornar JSON dentro de ```json ... ```"""
        mock_client = Mock()

        response_with_fence = {
            "questions": [
                {"id": f"M01_Q{i}", "text": f"Q{i}", "tipo": "aberta", "opcoes": None, "obrigatoria": True, "dica": None}
                for i in range(1, 41)
            ],
            "extracted_concepts": ["test"],
            "gaps_identified": ["gap1"],
            "total_questions": 40
        }

        mock_message = Mock()
        mock_message.content = [Mock(text=f"```json\n{json.dumps(response_with_fence)}\n```")]
        mock_client.messages.create.return_value = mock_message

        service = M01Service(anthropic_client=mock_client)
        result = service.generate_questionnaire(sample_document)

        assert result.count == 40

    def test_invalid_json_response_raises_error(self, sample_document):
        """Resposta que não é JSON válido deve falhar"""
        mock_client = Mock()
        mock_message = Mock()
        mock_message.content = [Mock(text="Isto não é JSON válido {{{")]
        mock_client.messages.create.return_value = mock_message

        service = M01Service(anthropic_client=mock_client)

        with pytest.raises(ValueError, match="Failed to parse Claude response as JSON"):
            service.generate_questionnaire(sample_document)

    def test_document_truncation_at_10k_chars(self, mock_anthropic_client):
        """Documento > 10k chars deve ser truncado"""
        long_doc = "A" * 15000

        service = M01Service(anthropic_client=mock_anthropic_client)
        result = service.generate_questionnaire(long_doc)

        # Verificar que o cliente foi chamado
        call_args = mock_anthropic_client.messages.create.call_args
        user_prompt = call_args[1]["messages"][0]["content"]

        # Deve conter a marca de truncação
        assert "[... documento truncado ...]" in user_prompt

    def test_iteration_id_generated_if_not_provided(self, mock_anthropic_client, sample_document):
        """Se iteration_id não for fornecido, deve gerar um"""
        service = M01Service(anthropic_client=mock_anthropic_client)
        result = service.generate_questionnaire(sample_document)

        assert result.iteration_id is not None
        assert result.iteration_id.startswith("m01_")
        assert len(result.iteration_id) > 4

    def test_iteration_id_preserved_if_provided(self, mock_anthropic_client, sample_document):
        """Se iteration_id for fornecido, deve usar o mesmo"""
        custom_id = "custom_iteration_abc123"
        service = M01Service(anthropic_client=mock_anthropic_client)
        result = service.generate_questionnaire(
            sample_document,
            iteration_id=custom_id
        )

        assert result.iteration_id == custom_id

    def test_domain_parameter_propagates(self, mock_anthropic_client, sample_document):
        """Domain parameter deve aparecer no resultado e na prompt"""
        service = M01Service(anthropic_client=mock_anthropic_client)
        result = service.generate_questionnaire(
            sample_document,
            domain="financeiro"
        )

        assert result.document_domain == "financeiro"

        # Verificar que aparece na prompt
        call_args = mock_anthropic_client.messages.create.call_args
        user_prompt = call_args[1]["messages"][0]["content"]
        assert "financeiro" in user_prompt

    def test_model_is_sonnet_4_6(self, mock_anthropic_client, sample_document):
        """Service deve usar claude-sonnet-4-6"""
        service = M01Service(anthropic_client=mock_anthropic_client)
        service.generate_questionnaire(sample_document)

        call_args = mock_anthropic_client.messages.create.call_args
        assert call_args[1]["model"] == "claude-sonnet-4-6-20250514"

    def test_max_tokens_is_4096(self, mock_anthropic_client, sample_document):
        """Service deve usar max_tokens=4096"""
        service = M01Service(anthropic_client=mock_anthropic_client)
        service.generate_questionnaire(sample_document)

        call_args = mock_anthropic_client.messages.create.call_args
        assert call_args[1]["max_tokens"] == 4096

    def test_anthropic_client_created_if_not_provided(self):
        """Se client não for fornecido, M01Service cria um novo"""
        with patch('app.services.m01_service.Anthropic') as mock_anthropic_class:
            service = M01Service()

            # Deve ter chamado Anthropic() para criar um client
            mock_anthropic_class.assert_called_once()
            assert service.client is not None


class TestCreateM01ServiceFactory:
    """Testes para a factory function create_m01_service()"""

    def test_factory_creates_service(self):
        """Factory deve criar um M01Service válido"""
        from app.services.m01_service import create_m01_service

        with patch('app.services.m01_service.Anthropic'):
            service = create_m01_service()
            assert isinstance(service, M01Service)

    def test_factory_initializes_client(self):
        """Factory deve inicializar Anthropic client"""
        from app.services.m01_service import create_m01_service

        with patch('app.services.m01_service.Anthropic') as mock_anthropic_class:
            service = create_m01_service()
            mock_anthropic_class.assert_called_once()
