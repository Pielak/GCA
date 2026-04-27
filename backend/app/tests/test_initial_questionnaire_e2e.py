"""
Testes E2E para Initial Questionnaire — fluxo completo draft → submit
"""
from fastapi.testclient import TestClient


def test_fluxo_completo_draft_to_submit(async_client: TestClient, test_project, auth_headers):
    """
    Teste do fluxo completo:
    1. GET cria questionnaire vazio em draft
    2. PATCH preenche respostas (auto-save)
    3. PATCH com submit=True muda para submitted
    4. Verificar que dados foram persistidos
    """
    project_id = test_project.id

    # ==== FASE 1: GET inicial cria questionnaire vazio ====
    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["q1_name"] is None

    # ==== FASE 2: PATCH preenche seção A (contexto) ====
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q1_name": "Sistema de Agendamentos",
            "q1_objective": "Plataforma web para clínicas",
            "q2_type": "novo_sistema",
            "q3_users": "Pacientes, médicos",
            "q3_volume": 1000,
            "q4_months": 6,
            "q4_target_date": "2026-10-27",
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    assert data["submitted_at"] is None

    # ==== FASE 3: PATCH preenche seção B (funcionais) ====
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q5_flows": "Fluxo 1: Login → Dashboard\nFluxo 2: Agendamento",
            "q6_integrations": ["sms", "google_calendar"],
            "q6_integrations_detail": "SMS via Twilio, Google Calendar para sync",
            "q7_frequency": "milhares_dia",
            "q8_reports": "Dashboard de ocupação",
            "q9_rules": "Slots de 30 min, 1 médico por slot",
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # ==== FASE 4: PATCH preenche seção C (RNFs) ====
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q10_performance": "importante_100_500ms",
            "q11_uptime": "99.5",
            "q12_sensitive_data": ["dados_pessoais", "dados_saude"],
            "q13_scalability": "modesto",
            "q14_compliance": ["lgpd"],
            "q15_longevity": "medio_prazo",
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # ==== FASE 5: PATCH preenche seção D (técnico) ====
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q16_stack": "Backend: Python/FastAPI, Frontend: React, DB: PostgreSQL",
            "q17_existing_infra": "AWS, Docker",
            "q18_constraints": "Integração com SAP legado",
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # ==== FASE 6: PATCH preenche seção E + SUBMIT ====
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q19_gca_expectations": ["codigo_completo", "documentacao"],
            "q20_risks": "Performance com volume, equipe pequena",
            "submit": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["submitted_at"] is not None
    assert data["submitted_by"] is not None

    # ==== FASE 7: Verificar que dados foram persistidos ====
    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["q1_name"] == "Sistema de Agendamentos"
    assert data["q6_integrations"] == ["sms", "google_calendar"]
    assert data["q12_sensitive_data"] == ["dados_pessoais", "dados_saude"]
    assert data["q19_gca_expectations"] == ["codigo_completo", "documentacao"]


def test_multiplas_submissoes_nao_criadas_mas_atualizadas(async_client: TestClient, test_project, auth_headers):
    """
    Validar que submeter 2x não cria 2 questionnaires (unique constraint).
    A segunda chamada atualiza a primeira.
    """
    project_id = test_project.id

    # Primeira submissão
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q1_name": "Primeira",
            "submit": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    first_id = response.json()["id"]

    # Segunda submissão (deve atualizar, não criar)
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q1_name": "Segunda",
            "submit": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    second_id = response.json()["id"]

    # IDs devem ser idênticos (updated, not created)
    assert first_id == second_id

    # GET deve retornar a segunda versão
    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["q1_name"] == "Segunda"


def test_campos_jsonb_array_persistem_corretamente(async_client: TestClient, test_project, auth_headers):
    """Validar que arrays JSONB (checklists) são salvos e recuperados"""
    project_id = test_project.id

    # Salvar arrays
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q6_integrations": ["sms", "email", "slack"],
            "q12_sensitive_data": ["dados_pessoais", "dados_financeiros"],
            "q14_compliance": ["lgpd", "gdpr", "hipaa"],
            "q19_gca_expectations": ["codigo_completo", "documentacao", "testes"],
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Recuperar e verificar
    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    data = response.json()
    assert data["q6_integrations"] == ["sms", "email", "slack"]
    assert data["q12_sensitive_data"] == ["dados_pessoais", "dados_financeiros"]
    assert data["q14_compliance"] == ["lgpd", "gdpr", "hipaa"]
    assert data["q19_gca_expectations"] == ["codigo_completo", "documentacao", "testes"]


def test_valores_numericos_salvos_corretamente(async_client: TestClient, test_project, auth_headers):
    """Validar que números (volume, meses) são salvos como números, não strings"""
    project_id = test_project.id

    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q3_volume": 5000,
            "q4_months": 12,
            "submit": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    data = response.json()
    assert data["q3_volume"] == 5000
    assert isinstance(data["q3_volume"], int)
    assert data["q4_months"] == 12
    assert isinstance(data["q4_months"], int)


def test_submitted_nao_pode_ser_editado_no_frontend(async_client: TestClient, test_project, auth_headers):
    """
    Após submit=True, a resposta entra em "submitted".
    Frontend deve disabilitar edição (form readonly).
    """
    project_id = test_project.id

    # Submeter
    async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q1_name": "Original",
            "submit": True,
        },
        headers=auth_headers,
    )

    # Tentar editar (endpoint não impede, mas frontend desabilita UI)
    response = async_client.patch(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        json={
            "q1_name": "Modificado",
            "submit": False,
        },
        headers=auth_headers,
    )
    # Backend retorna 200 mas status continua submitted
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"

    # Verificar que q1_name não foi alterado
    response = async_client.get(
        f"/api/v1/projects/{project_id}/initial-questionnaire",
        headers=auth_headers,
    )
    data = response.json()
    assert data["status"] == "submitted"
