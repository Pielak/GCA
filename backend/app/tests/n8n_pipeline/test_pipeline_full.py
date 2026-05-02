"""
Testes do pipeline completo n8n: Conferente → Especialistas → Consolidador → Backend.

Estratégia:
- Validações estáticas (estrutura dos workflows): rápido, sem consumir LLM
- Conectividade de webhooks: cada path responde (não 404)
- Smoke test E2E: 1 execução real, validar até onde chegou (sem assert rígido em LLM)
"""
import os
import json
import time
import hmac
import hashlib
import sqlite3
import pytest
import requests


N8N_BASE = os.getenv("N8N_BASE_URL", "http://localhost:5678")
BACKEND_BASE = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_DB = "/home/luiz/.n8n/database.sqlite"

GCA_WEBHOOK_SECRET = "45b64e16b5653718023408419aade9a9a35ab244d1897bccebf51270f3b1cb6b"
NORMALIZER_SECRET = "d74ac09664abc7957cfc16ba3efbc068a08fcb3af9b84d055ca940a6afb377b0"
CONFERENTE_SECRET = "a1a181c0d85c328777be4eb42e1c60c1b2584913645199b0453d58961a5a3456"
SPECIALIST_SECRET = "413a72e9401f1977c4e6ec16dabf9ea6e36862f391d274c681e9e650bb367649"

PROJECT_ID = "24bf72c3-2ee8-45fd-b879-d3a00b347c39"

# Lista canônica de workflows GCA (conjunto B do CLAUDE.md §0.5)
GCA_WORKFLOWS = [
    "gca-normalizer-v3",
    "gca-conferente-v3",
    "gca-orchestrator-gp",
    "gca-specialist-aud",
    "gca-specialist-arq",
    "gca-specialist-dba",
    "gca-specialist-dev",
    "gca-specialist-qa",
    "gca-specialist-ux",
    "gca-specialist-ui",
    "gca-specialist-seg",
    "gca-specialist-conf",
    "gca-specialist-lgpd",
    "gca-specialist-neg",
    "gca-consolidador-v3",
    "gca-pipeline-logger",
]

SPECIALIST_WEBHOOKS = [
    "gca-specialist-arq",
    "gca-specialist-dba",
    "gca-specialist-dev",
    "gca-specialist-qa",
    "gca-specialist-ux",
    "gca-specialist-ui",
    "gca-specialist-seg",
    "gca-specialist-conf",
    "gca-specialist-lgpd",
    "gca-specialist-neg",
]


# ─── Helpers ───────────────────────────────────────────────────────────────


def sign_hmac(body_str: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def get_workflow_active_data(workflow_id: str) -> tuple[dict, dict] | tuple[None, None]:
    """Lê nodes/connections da versão ATIVA do workflow."""
    conn = sqlite3.connect(N8N_DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT wh.nodes, wh.connections FROM workflow_history wh
        JOIN workflow_entity we ON we.activeVersionId = wh.versionId
        WHERE we.id = ?
    """, (workflow_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None, None
    return json.loads(row[0]), json.loads(row[1])


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 1 — Validações estáticas (estrutura dos workflows)
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowsEstrutura:
    """Verifica estrutura básica de cada workflow GCA."""

    @pytest.mark.parametrize("wf_id", GCA_WORKFLOWS)
    def test_workflow_existe_e_ativo(self, wf_id):
        """Cada workflow GCA deve existir e estar ativo."""
        conn = sqlite3.connect(N8N_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT active, activeVersionId FROM workflow_entity WHERE id = ?", (wf_id,))
        row = cursor.fetchone()
        conn.close()

        assert row, f"Workflow {wf_id} não existe"
        # gca-pipeline-logger pode estar inativo (é error workflow)
        if wf_id != "gca-pipeline-logger":
            assert row[0] == 1, f"Workflow {wf_id} não está ativo"
        assert row[1], f"Workflow {wf_id} sem activeVersionId"

    @pytest.mark.parametrize("wf_id", GCA_WORKFLOWS)
    def test_conexoes_nao_orfas(self, wf_id):
        """Nenhuma conexão deve apontar para nó inexistente (regressão)."""
        nodes, connections = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        node_names = {n["name"] for n in nodes}
        orphans = []

        for src, conn_data in connections.items():
            if src not in node_names:
                orphans.append(f"source '{src}' inexistente")
            if isinstance(conn_data.get("main"), list):
                for branch in conn_data["main"]:
                    for c in branch:
                        tgt = c.get("node")
                        if tgt and tgt not in node_names:
                            orphans.append(f"{src} → '{tgt}' (target inexistente)")

        assert not orphans, f"Conexões órfãs em {wf_id}: {orphans}"

    @pytest.mark.parametrize("wf_id", GCA_WORKFLOWS)
    def test_tem_webhook_trigger(self, wf_id):
        """Cada workflow do GCA deve ter um webhook trigger ou error trigger."""
        nodes, _ = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        triggers = [
            n for n in nodes
            if n["type"] in ("n8n-nodes-base.webhook", "n8n-nodes-base.errorTrigger")
        ]
        assert triggers, f"{wf_id} sem trigger (webhook/errorTrigger)"


class TestProviderAgnostico:
    """Verifica que nenhum workflow tem provider hardcoded (Anthropic/OpenAI/etc)."""

    @pytest.mark.parametrize("wf_id", [
        w for w in GCA_WORKFLOWS
        if w not in ("gca-normalizer-v3", "gca-consolidador-v3", "gca-pipeline-logger")
    ])
    def test_sem_hardcode_provider(self, wf_id):
        """Workflows com LLM call não devem ter URL/header anthropic/claude hardcoded."""
        nodes, _ = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        # Procurar URLs hardcoded de providers
        hardcoded_urls = ["api.anthropic.com", "api.openai.com", "claude-"]
        violations = []

        for node in nodes:
            params_str = json.dumps(node.get("parameters", {}))
            # Permitir em código JS (que faz lookup dinâmico) — verificar só URLs
            url = node.get("parameters", {}).get("url", "")
            if isinstance(url, str):
                for bad in hardcoded_urls:
                    if bad in url and "$json" not in url and "{{" not in url:
                        violations.append(f"{node['name']}: URL hardcoded '{bad}'")

        assert not violations, f"Hardcoded em {wf_id}: {violations}"


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 2 — Conectividade de webhooks
# ═══════════════════════════════════════════════════════════════════════════


class TestWebhooksConectividade:
    """Cada webhook do pipeline deve responder (não 404)."""

    @pytest.mark.parametrize("path", [
        "gca-normalizer",
        "gca-conferente",
        "gca-orchestrator-gp",
        "gca-consolidador-accumulate",
    ] + SPECIALIST_WEBHOOKS)
    def test_webhook_existe(self, path):
        """Webhook não deve retornar 404 (caso n8n não tenha registrado)."""
        # POST com body vazio — pode dar 4xx mas não deve ser 404
        resp = requests.post(
            f"{N8N_BASE}/webhook/{path}",
            json={},
            timeout=10,
        )
        assert resp.status_code != 404, f"Webhook /{path} não registrado (404)"
        # 500 com 'Workflow could not be started' = workflow tem bug interno
        if resp.status_code == 500 and "could not be started" in resp.text:
            pytest.fail(f"Webhook /{path} existe mas workflow não inicia: {resp.text[:200]}")


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 3 — Conferente: dispatch para especialistas
# ═══════════════════════════════════════════════════════════════════════════


class TestConferenteDispatch:
    """Valida que o Conferente despacha para especialistas + GP."""

    def test_conferente_tem_no_dispatch_especialistas(self):
        """Conferente deve ter um nó que despacha para múltiplos especialistas."""
        nodes, _ = get_workflow_active_data("gca-conferente-v3")
        assert nodes
        despatch_nodes = [n for n in nodes if "specialista" in n["name"].lower() or "dispatch" in n["name"].lower()]
        assert len(despatch_nodes) >= 2, f"Esperado nós de dispatch para especialistas, achei: {[n['name'] for n in despatch_nodes]}"

    def test_conferente_tem_dispatch_gp(self):
        """Conferente deve ter dispatch separado para GP (orquestrador)."""
        nodes, _ = get_workflow_active_data("gca-conferente-v3")
        assert nodes
        gp_nodes = [n for n in nodes if "GP" in n["name"] or "orchestrator" in n["name"].lower()]
        assert gp_nodes, "Conferente sem nó de dispatch para GP"


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 4 — Especialistas: estrutura padronizada
# ═══════════════════════════════════════════════════════════════════════════


SPECIALIST_WORKFLOWS = [
    "gca-specialist-arq",
    "gca-specialist-dba",
    "gca-specialist-dev",
    "gca-specialist-qa",
    "gca-specialist-ux",
    "gca-specialist-ui",
    "gca-specialist-seg",
    "gca-specialist-conf",
    "gca-specialist-lgpd",
    "gca-specialist-neg",
    "gca-orchestrator-gp",
]


class TestEspecialistasEstrutura:
    """Cada especialista deve seguir padrão: webhook → HMAC → LLM → callback."""

    @pytest.mark.parametrize("wf_id", SPECIALIST_WORKFLOWS)
    def test_especialista_tem_llm_call(self, wf_id):
        """Cada especialista deve ter um nó de chamada LLM."""
        nodes, _ = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        llm_nodes = [n for n in nodes if "LLM" in n["name"] or "Chamar" in n["name"]]
        assert llm_nodes, f"{wf_id} sem nó LLM. Nós: {[n['name'] for n in nodes]}"

    @pytest.mark.parametrize("wf_id", SPECIALIST_WORKFLOWS)
    def test_especialista_callback_consolidador(self, wf_id):
        """Cada especialista deve fazer callback ao Consolidador."""
        nodes, _ = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        callback_node = None
        for n in nodes:
            url = n.get("parameters", {}).get("url", "")
            if "consolidador" in str(url).lower():
                callback_node = n
                break

        assert callback_node, f"{wf_id} sem callback ao Consolidador"

    @pytest.mark.parametrize("wf_id", SPECIALIST_WORKFLOWS)
    def test_especialista_usa_provider_chain_dinamico(self, wf_id):
        """Cada especialista deve montar request LLM dinamicamente baseado em provider_chain."""
        nodes, _ = get_workflow_active_data(wf_id)
        if nodes is None:
            pytest.skip(f"{wf_id} sem dados")

        # Procurar nó que monta a request
        for n in nodes:
            if n["type"] == "n8n-nodes-base.code" and ("Montar" in n["name"] or "LLM Request" in n["name"]):
                code = n["parameters"].get("jsCode", "")
                # Deve referenciar provider_chain, não hardcoded
                assert "provider_chain" in code, f"{wf_id}/{n['name']}: não usa provider_chain"
                # Deve ter pelo menos suporte a deepseek (que é o configurado)
                assert "deepseek" in code.lower() or "providerName" in code, (
                    f"{wf_id}: não suporta DeepSeek dinamicamente"
                )
                return

        pytest.fail(f"{wf_id} sem nó de montagem de LLM Request")


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 5 — Consolidador: acumulação e callback final
# ═══════════════════════════════════════════════════════════════════════════


class TestConsolidador:
    """Valida o Consolidador: acumulação em Redis e callback final ao Backend."""

    def test_consolidador_tem_endpoint_accumulate(self):
        """Consolidador deve ter webhook /gca-consolidador-accumulate."""
        nodes, _ = get_workflow_active_data("gca-consolidador-v3")
        assert nodes

        webhook_node = next(
            (n for n in nodes if n["type"] == "n8n-nodes-base.webhook"),
            None,
        )
        assert webhook_node, "Consolidador sem webhook"
        path = webhook_node["parameters"].get("path", "")
        assert path == "gca-consolidador-accumulate", f"Path errado: {path}"

    def test_consolidador_callback_final_ao_backend(self):
        """Consolidador deve fazer callback final a /api/v1/webhooks/ingestion-complete."""
        nodes, _ = get_workflow_active_data("gca-consolidador-v3")
        assert nodes

        callback_node = None
        for n in nodes:
            url = n.get("parameters", {}).get("url", "")
            if "ingestion-complete" in str(url):
                callback_node = n
                break

        assert callback_node, "Consolidador sem callback final ao Backend"


# ═══════════════════════════════════════════════════════════════════════════
# CLASSE 6 — Backend: endpoints de pipeline
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendEndpoints:
    """Backend tem todos os endpoints internos que o pipeline usa."""

    def test_endpoint_hmac_sign_existe(self):
        """POST /api/v1/webhooks/internal/hmac/sign deve existir."""
        resp = requests.post(
            f"{BACKEND_BASE}/api/v1/webhooks/internal/hmac/sign",
            json={"body_raw": "test", "secret_name": "GCA_WEBHOOK_SECRET"},
            timeout=10,
        )
        assert resp.status_code in (200, 400, 422), f"Esperado 200/400/422, recebeu {resp.status_code}"

    def test_endpoint_hmac_verify_existe(self):
        """POST /api/v1/webhooks/internal/hmac/verify deve existir."""
        resp = requests.post(
            f"{BACKEND_BASE}/api/v1/webhooks/internal/hmac/verify",
            json={"body_raw": "test", "signature": "x", "secret_name": "GCA_WEBHOOK_SECRET"},
            timeout=10,
        )
        assert resp.status_code in (200, 400, 422)

    def test_endpoint_pipeline_log_existe(self):
        """POST /api/v1/webhooks/internal/pipeline-log deve existir."""
        resp = requests.post(
            f"{BACKEND_BASE}/api/v1/webhooks/internal/pipeline-log",
            json={
                "ts": "2026-05-02T00:00:00Z",
                "ingestion_id": "test",
                "workflow": "test",
                "node": "test",
                "event": "test",
            },
            timeout=10,
        )
        assert resp.status_code in (200, 201, 400, 422)

    def test_endpoint_ingestion_complete_existe(self):
        """POST /api/v1/webhooks/ingestion-complete deve existir."""
        resp = requests.post(
            f"{BACKEND_BASE}/api/v1/webhooks/ingestion-complete",
            json={},  # body vazio — vai dar 422 mas não 404
            timeout=10,
        )
        assert resp.status_code != 404, "Endpoint ingestion-complete não existe"
