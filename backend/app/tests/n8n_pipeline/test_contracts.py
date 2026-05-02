"""
Testes de contrato do pipeline n8n.

Cada teste valida o output esperado de um nó específico, dada uma entrada conhecida.
Usa a API do n8n para disparar nós isoladamente (via webhooks de teste) e a API
de execuções para inspecionar inputs/outputs reais.

Pré-requisitos:
- n8n rodando em http://localhost:5678
- Backend rodando em http://localhost:8000
- N8N_API_KEY válida (pega de env)
- Workflows GCA importados e ativos
"""
import os
import json
import time
import hmac
import hashlib
import pytest
import requests


# ─── Configuração ──────────────────────────────────────────────────────────

N8N_BASE = os.getenv("N8N_BASE_URL", "http://localhost:5678")
BACKEND_BASE = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
GCA_WEBHOOK_SECRET = "45b64e16b5653718023408419aade9a9a35ab244d1897bccebf51270f3b1cb6b"
NORMALIZER_SECRET = "d74ac09664abc7957cfc16ba3efbc068a08fcb3af9b84d055ca940a6afb377b0"

PROJECT_ID = "24bf72c3-2ee8-45fd-b879-d3a00b347c39"

VALID_PAYLOAD = {
    "ingestion_id": "00000000-0000-4000-8000-000000000001",
    "project_id": PROJECT_ID,
    "document_bytes_base64": "VGVzdGUgZG9jdW1lbnRvIHBhcmEgcGlwZWxpbmU=",  # base64
    "document_metadata": {
        "filename": "teste.txt",
        "mime_type": "text/plain",
        "size_bytes": 30,
    },
    "normalized_text": "Documento de teste para validar contratos do pipeline",
    "provider_chain": [
        {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "api_key": "sk-test-key",
        }
    ],
}


# ─── Helpers ───────────────────────────────────────────────────────────────


def sign_hmac(body_str: str, secret: str) -> str:
    """Gera signature HMAC-SHA256."""
    sig = hmac.new(secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def trigger_webhook(path: str, payload: dict, signature_header: str = None) -> requests.Response:
    """Dispara webhook do n8n e retorna a resposta."""
    body_str = json.dumps(payload, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    if signature_header:
        sig = sign_hmac(body_str, GCA_WEBHOOK_SECRET)
        headers[signature_header] = sig
    return requests.post(f"{N8N_BASE}/webhook/{path}", data=body_str, headers=headers, timeout=30)


def get_last_execution_for_workflow(workflow_id: str, max_age_sec: int = 30) -> dict:
    """Pega a última execução de um workflow específico (com data completa)."""
    if not N8N_API_KEY:
        pytest.skip("N8N_API_KEY não configurada — skip teste de integração")

    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    resp = requests.get(
        f"{N8N_BASE}/api/v1/executions?limit=10&workflowId={workflow_id}",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    executions = resp.json().get("data", [])
    if not executions:
        return None

    last = executions[0]
    # Pegar dados completos
    detail = requests.get(
        f"{N8N_BASE}/api/v1/executions/{last['id']}?includeData=true",
        headers=headers,
        timeout=10,
    )
    detail.raise_for_status()
    return detail.json()


def get_node_output(execution: dict, node_name: str) -> dict | None:
    """Extrai output de um nó específico de uma execução."""
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    runs = run_data.get(node_name, [])
    if not runs:
        return None
    main = runs[0].get("data", {}).get("main", [[]])
    if not main or not main[0]:
        return None
    return main[0][0].get("json", {})


def get_node_error(execution: dict, node_name: str) -> dict | None:
    """Extrai erro de um nó (None se nó não falhou)."""
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    runs = run_data.get(node_name, [])
    if not runs:
        return None
    return runs[0].get("error")


# ─── Testes do Workflow 01 (Normalizer) ────────────────────────────────────


class TestNormalizerWebhookTrigger:
    """Valida que o webhook do Normalizer aceita payload correto."""

    def test_aceita_payload_valido(self):
        """Webhook responde 200/202 com payload bem-formado."""
        resp = trigger_webhook(
            "gca-normalizer",
            VALID_PAYLOAD,
            signature_header="X-GCA-Signature",
        )
        assert resp.status_code in (200, 202), f"Esperado 200/202, recebido {resp.status_code}: {resp.text[:200]}"


class TestNormalizerG0Validar:
    """Valida o nó 'G0 - Validar entrada'."""

    def test_payload_valido_retorna_g0_status_ok(self):
        """G0 deve retornar _g0_status='ok' com todos os campos esperados."""
        trigger_webhook("gca-normalizer", VALID_PAYLOAD, "X-GCA-Signature")
        time.sleep(3)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        assert execution, "Execução não encontrada"

        g0_output = get_node_output(execution, "G0 - Validar entrada")
        assert g0_output, "Nó G0 não produziu output"

        # Contrato: deve ter todos esses campos quando _g0_status='ok'
        assert g0_output.get("_g0_status") == "ok", f"G0 retornou status errado: {g0_output}"
        assert g0_output.get("ingestion_id") == VALID_PAYLOAD["ingestion_id"]
        assert g0_output.get("project_id") == VALID_PAYLOAD["project_id"]
        assert g0_output.get("provider_chain") == VALID_PAYLOAD["provider_chain"]
        assert g0_output.get("document_bytes_base64") == VALID_PAYLOAD["document_bytes_base64"]

    def test_mime_invalido_retorna_g0_failed_com_project_id(self):
        """G0 com mime_type inválido deve retornar failed COM project_id (regressão)."""
        bad_payload = dict(VALID_PAYLOAD)
        bad_payload["ingestion_id"] = "00000000-0000-4000-8000-000000000002"
        bad_payload["document_metadata"] = dict(VALID_PAYLOAD["document_metadata"])
        bad_payload["document_metadata"]["mime_type"] = "application/invalid"

        trigger_webhook("gca-normalizer", bad_payload, "X-GCA-Signature")
        time.sleep(3)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        g0_output = get_node_output(execution, "G0 - Validar entrada")

        assert g0_output is not None
        assert g0_output.get("_g0_status") == "failed"
        assert g0_output.get("_g0_reason") == "g0_input_invalid"
        assert g0_output.get("_http_status") == 415
        assert g0_output.get("project_id") == bad_payload["project_id"], (
            "REGRESSÃO: G0 não retornou project_id em caso de erro"
        )

    def test_uuid_invalido_retorna_g0_failed_422(self):
        """G0 com ingestion_id não-UUID retorna failed/422."""
        bad_payload = dict(VALID_PAYLOAD)
        bad_payload["ingestion_id"] = "nao-eh-uuid"

        trigger_webhook("gca-normalizer", bad_payload, "X-GCA-Signature")
        time.sleep(3)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        g0_output = get_node_output(execution, "G0 - Validar entrada")

        assert g0_output.get("_g0_status") == "failed"
        assert g0_output.get("_http_status") == 422


class TestNormalizerCallbackErroG0:
    """Valida que o callback de erro G0 envia payload correto ao backend."""

    def test_callback_inclui_project_id(self):
        """Callback erro G0 deve enviar project_id no body (REGRESSÃO)."""
        bad_payload = dict(VALID_PAYLOAD)
        bad_payload["ingestion_id"] = "00000000-0000-4000-8000-000000000003"
        bad_payload["document_metadata"] = dict(VALID_PAYLOAD["document_metadata"])
        bad_payload["document_metadata"]["mime_type"] = "application/invalid"

        trigger_webhook("gca-normalizer", bad_payload, "X-GCA-Signature")
        time.sleep(4)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        callback_err = get_node_error(execution, "Callback erro G0")

        assert callback_err is None, (
            f"Callback erro G0 falhou (provavelmente schema inválido): "
            f"{str(callback_err)[:200]}"
        )

    def test_callback_payload_aceito_pelo_backend(self):
        """Callback envia payload conforme IngestionCompletePayload schema."""
        # Disparar e confirmar que callback chegou no backend sem erro 422
        bad_payload = dict(VALID_PAYLOAD)
        bad_payload["ingestion_id"] = "00000000-0000-4000-8000-000000000004"
        bad_payload["document_metadata"] = dict(VALID_PAYLOAD["document_metadata"])
        bad_payload["document_metadata"]["mime_type"] = "application/invalid"

        trigger_webhook("gca-normalizer", bad_payload, "X-GCA-Signature")
        time.sleep(4)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        callback_err = get_node_error(execution, "Callback erro G0")
        assert callback_err is None, f"Backend rejeitou callback: {str(callback_err)[:300]}"


class TestNormalizerDespacharConferente:
    """Valida o despacho para o Conferente."""

    def test_dispatch_chega_no_conferente(self):
        """Despacho deve disparar workflow do Conferente (sem 'could not start')."""
        trigger_webhook("gca-normalizer", VALID_PAYLOAD, "X-GCA-Signature")
        time.sleep(5)

        execution = get_last_execution_for_workflow("gca-normalizer-v3")
        despachar_err = get_node_error(execution, "Despachar para Conferente")

        assert despachar_err is None, (
            f"Despachar para Conferente falhou: {str(despachar_err.get('description', ''))[:300]}"
        )


# ─── Testes do Workflow 02 (Conferente) ────────────────────────────────────


class TestConferenteAtivo:
    """Valida que o Conferente está ativo e responde."""

    def test_conferente_workflow_ativo(self):
        """Workflow do Conferente deve estar ativo no n8n."""
        if not N8N_API_KEY:
            pytest.skip("N8N_API_KEY não configurada")
        headers = {"X-N8N-API-KEY": N8N_API_KEY}
        resp = requests.get(
            f"{N8N_BASE}/api/v1/workflows/gca-conferente-v3",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        workflow = resp.json()
        assert workflow.get("active") is True, (
            f"Workflow Conferente está inativo: {workflow.get('active')}"
        )

    def test_conferente_responde_webhook(self):
        """Webhook do Conferente deve aceitar POST."""
        envelope = {
            "ingestion_id": VALID_PAYLOAD["ingestion_id"],
            "project_id": VALID_PAYLOAD["project_id"],
            "normalized_text": "test",
            "provider_chain": VALID_PAYLOAD["provider_chain"],
        }
        body_str = json.dumps(envelope, separators=(",", ":"))
        sig = sign_hmac(body_str, NORMALIZER_SECRET)
        resp = requests.post(
            f"{N8N_BASE}/webhook/gca-conferente",
            data=body_str,
            headers={
                "Content-Type": "application/json",
                "X-Normalizer-Signature": sig,
            },
            timeout=10,
        )
        # Aceita 200 (sucesso) ou 4xx (erro de validação) — 404 não é OK
        assert resp.status_code != 404, "Webhook Conferente não existe"
        assert resp.status_code != 500, f"Webhook Conferente erro 500: {resp.text[:200]}"
