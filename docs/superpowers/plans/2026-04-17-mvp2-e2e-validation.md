# Roteiro de validação E2E — MVP 2 (smoke manual, ~25 min)

**Objetivo:** validar no dogfood que os 3 pontos de mudança de OCG disparam corretamente os hooks de consistência (propagate + gatekeeper reeval) e que as features do §10 do MVP 2 funcionam fim-a-fim.

**Saída esperada:** último item pendente do §10 ("validação ingestão end-to-end no dogfood") marcado como OK → gate do MVP 2 pode avançar para MVP 3.

**Pré-condições do código** (todas satisfeitas em 2026-04-17):
- Commits `3942f6a` (contração OCG + PII), `1a2e917` (Gatekeeper reeval), `96eb131` (hooks nos 3 pontos).
- Baseline 320/343 testes backend passando; 23 failures pré-existentes inalteradas.

---

## Pré-requisitos

```bash
docker ps --format '{{.Names}}\t{{.Status}}'   # gca-backend, gca-frontend, gca-postgres, gca-redis = Up
curl -sf http://localhost:8000/health && echo OK
curl -sf http://localhost:5173 | head -1
```

- Login admin: `pielak.ctba@gmail.com` / (senha local)
- Login GP: `pielakluiz@gmail.com` / (senha local)
- SQL: `docker exec -it gca-postgres psql -U gca -d gca`

Convenção nesta validação: `<PID>` = uuid do projeto de teste. Substitua a cada cenário.

---

## Cenário 1 — Projeto novo (seed inicial do backlog)

**Expectativa:** questionário aprovado → OCG criado → backlog populado automaticamente + evento `BACKLOG_REGENERATED` e `GATEKEEPER_REEVALUATED` com `trigger=questionnaire_approved`.

### Passos

1. Abrir `/solicitar-projeto` (público, sem login). Preencher nome, email, projeto. Submeter passo 1 + passo 2.
2. Logar como admin → Dashboard Admin → aprovar a solicitação. Isso dispara `_generate_ocg` em background (~30-60s).
3. Acompanhar logs:
   ```bash
   docker logs gca-backend -f | grep -E "ocg_generation|backlog_regen|gatekeeper_reeval"
   ```
4. Obter `<PID>`: `SELECT id, slug, name FROM projects ORDER BY created_at DESC LIMIT 1;`
5. Verificar audit:
   ```sql
   SELECT event_type, details->>'trigger' AS trigger, created_at
   FROM audit_log_global
   WHERE resource_id = '<PID>'
     AND event_type IN ('BACKLOG_REGENERATED','GATEKEEPER_REEVALUATED')
   ORDER BY created_at DESC LIMIT 5;
   ```
   **Esperado:** 2 linhas, ambas com `trigger=questionnaire_approved`.
6. Verificar count do backlog:
   ```sql
   SELECT COUNT(*) FROM backlog_items
   WHERE project_id='<PID>' AND source='ocg';
   ```
   **Esperado:** ≥ 1.
7. UI: logar como GP → abrir o projeto → aba **Backlog**. Items devem aparecer sem clicar "Regenerar".

### Critério de falha
- 0 eventos no audit,
- backlog vazio após OCG criado,
- erro no log de `_generate_ocg` ou `ocg_reactive`.

---

## Cenário 2 — Upload de documento (expansão)

**Pré:** projeto com setup completo (repo + PAT + chave IA configurada pelo GP em Settings > LLM). Usar projeto existente se já houver um em estado bom, ou completar o setup do projeto criado no Cenário 1.

### Passos

1. Aba **Ingestão** → upload de `.md` ou `.txt` com conteúdo técnico real (5-10 parágrafos sobre arquitetura/stack do sistema).
2. Acompanhar o status na UI: `pending → processing → completed` (~30-90s). Log:
   ```bash
   docker logs gca-backend -f | grep -E "analysis_complete|ocg_reactive|propagate|gatekeeper_reeval"
   ```
3. Verificar audit:
   ```sql
   SELECT event_type, details->>'trigger' AS trigger, created_at
   FROM audit_log_global
   WHERE resource_id = '<PID>' AND created_at > NOW() - INTERVAL '5 minutes'
   ORDER BY created_at DESC;
   ```
   **Esperado:** `DOCUMENT_INGESTED` + `BACKLOG_REGENERATED` + `GATEKEEPER_REEVALUATED`, todos com `trigger=document_ingestion`.
4. Verificar incremento do OCG:
   ```sql
   SELECT version, updated_at FROM ocg WHERE project_id='<PID>'
   ORDER BY version DESC LIMIT 2;
   ```
   **Esperado:** versão nova > versão anterior.
5. UI: aba **Gatekeeper** com scores atualizados; aba **Backlog** com items novos ou modificados.

### Critério de falha
- Status trava em `processing`,
- `arguider_status=error` (ver detalhes em `arguider_analyses`),
- eventos `BACKLOG_REGENERATED`/`GATEKEEPER_REEVALUATED` ausentes,
- OCG sem incremento.

---

## Cenário 3 — Delete de documento (contração)

### Passos

1. Aba **Ingestão** → ícone lixeira no doc do Cenário 2. Confirmar.
2. Verificar delta de contração:
   ```sql
   SELECT trigger_source, fields_changed, ocg_version_from, ocg_version_to, change_summary
   FROM ocg_delta_log
   WHERE project_id='<PID>' AND trigger_source='document_removal'
   ORDER BY created_at DESC LIMIT 1;
   ```
   **Esperado:** 1 linha com `trigger_source=document_removal` e `fields_changed` populado.
3. Verificar audit do delete:
   ```sql
   SELECT event_type, details->>'trigger' AS trigger, created_at
   FROM audit_log_global
   WHERE resource_id = '<PID>'
     AND created_at > NOW() - INTERVAL '2 minutes'
   ORDER BY created_at DESC;
   ```
   **Esperado:** `BACKLOG_REGENERATED` + `GATEKEEPER_REEVALUATED` com `trigger=document_removal`.
4. UI: aba **Backlog** — items gerados exclusivamente por esse doc não existem mais.

### Nota importante
Se a contração só teve `fields_skipped` (tocados por deltas posteriores) e nenhum revertido, os hooks **não disparam** (por design — nada a propagar). Nesse caso, a resposta do DELETE traz `fields_reverted: []` e `fields_skipped: [...]`. Isso é comportamento correto, não regressão.

### Critério de falha
- Delta `document_removal` ausente,
- hooks não disparados mesmo com `fields_reverted` não-vazio,
- backlog ainda tem items obsoletos da versão anterior.

---

## Cenário 4 — PII quarantine (regressão do bug de 2026-04-17)

**Contexto:** antes do commit `3942f6a`, o detector de PII dava falso-positivo em PDFs do questionário (runs de 14 dígitos em xref tables viravam "CNPJ"). Esse cenário garante que o bug não volta.

### Passos

1. Upload de um **PDF do questionário técnico preenchido** (ou qualquer PDF sem CPF/CNPJ/email reais).
   **Esperado:** `arguider_status=completed` (NÃO `quarantined`).
2. Criar arquivo com CPF válido por mod-11:
   ```bash
   echo "Contato: João Silva, CPF 12345678909, email joao@teste.com" > /tmp/pii.txt
   ```
3. Upload do `.txt`. **Esperado:** `arguider_status=quarantined`, ícone 🛡️ laranja na UI, card laranja "Quarentena" no grid.
4. Verificar SQL:
   ```sql
   SELECT original_filename, arguider_status, quarantine_status
   FROM ingested_documents
   WHERE project_id='<PID>' ORDER BY created_at DESC LIMIT 3;
   ```
   **Esperado:** PDF do questionário = `completed`; txt com CPF = `quarantined`.

### Critério de falha
- PDF do questionário marcado como `quarantined` (regressão do bug),
- CPF real passando como `completed`.

---

## Critério de abertura do gate do MVP 2

Após rodar os 4 cenários, o item `[⏸] Validação ingestão end-to-end no dogfood` do §10 do `GCA_MVP_PROGRESS.md` pode ser marcado `[x]` e o gate pode mudar para **PODE AVANÇAR** se:

| Cenário | Check |
|---|---|
| 1 | 2 eventos no audit com `trigger=questionnaire_approved`, backlog não vazio |
| 2 | 3 eventos com `trigger=document_ingestion`, OCG versão +1 |
| 3 | delta `document_removal`, 2 eventos com esse trigger (se houve `fields_reverted`) |
| 4 | PDF do questionário não quarentenado; CPF real quarentenado |

**NÃO AVANÇAR** se qualquer cenário falhar — registrar a falha, abrir DT no §3 do progresso, corrigir, revalidar.

---

## Procedimento após smoke

1. Atualizar `GCA_MVP_PROGRESS.md`:
   - §6 "Situação do gate": mudar para **PODE AVANÇAR**.
   - §10: marcar o último item `[x]` com data e referência a esta validação.
   - §9 (emendas): registrar "Smoke manual MVP 2 executado em 2026-MM-DD, todos os 4 cenários OK".
2. Considerar abrir MVP 3 no progresso (novo cabeçalho, escopo canônico do contrato §7).
3. Commitar a atualização do progresso como `docs(progress): MVP 2 gate aberto após smoke E2E`.

## Contraindicações

- Este roteiro **não** substitui testes automatizados — ele valida integração viva (LLM real, filas, sessions). Os unit tests das frentes A-D (commits `3942f6a`, `1a2e917`, `96eb131`) continuam sendo o gate automatizável.
- Se o LLM do GP estiver com quota/rate-limit, o Cenário 2 pode falhar por motivo externo ao GCA. Nesse caso, registrar como "ambiente" e não como "regressão de código".
- Este é um dogfood real. **Não inserir dados de teste no DB via SQL/script** — use a UI. Isso respeita a regra canônica `feedback_no_unauthorized_data`.
