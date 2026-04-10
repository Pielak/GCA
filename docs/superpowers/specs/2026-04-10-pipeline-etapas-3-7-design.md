# Design: Pipeline Etapas 3-7 (TestGen → Security → Compliance → QA)

**Data:** 2026-04-10
**Status:** Aprovado

---

## 1. TestGen (Etapa 3)

Apos CodeGen, LLM gera testes (unitarios + integracao) no formato da stack.

**Endpoint:** `POST /projects/{id}/backlog/{item_id}/generate-tests`
- Chama LLM com codigo gerado + OCG testing requirements
- Cobertura minima projetada: 70%+
- Status do item: `tests_running`

## 2. Branch + Commit + GitHub Actions (Etapa 4)

**Endpoint:** `POST /projects/{id}/backlog/{item_id}/run-tests`
- Cria branch `feature/backlog-{item_id}` via GitHub API
- Commita codigo + testes
- Gera `.github/workflows/test.yml` se nao existir
- Status: `tests_running`

**Endpoint:** `GET /projects/{id}/backlog/{item_id}/test-status`
- Polling GitHub Actions API
- Completed + success → `security_review`
- Completed + failure → `blocked`

## 3. Security Review (Etapa 5)

**Endpoint:** `POST /projects/{id}/backlog/{item_id}/security-scan`
- LLM analisa contra OWASP Top 10
- Se Semgrep configurado, chama API tambem
- CRITICAL → blocked, MEDIUM → warning
- Pass → `compliance_review`

## 4. Compliance Check (Etapa 6)

**Endpoint:** `POST /projects/{id}/backlog/{item_id}/compliance-check`
- LLM valida contra ISO 27001 + LGPD do item
- Pass → `awaiting_qa`, Fail → blocked

## 5. QA Approval (Etapa 7)

**Endpoint:** `POST /projects/{id}/backlog/{item_id}/qa-approve`
- Requer `qa:approve`
- Aprovado → `ready_to_merge`, Rejeitado → `blocked`
- Audit log completo
