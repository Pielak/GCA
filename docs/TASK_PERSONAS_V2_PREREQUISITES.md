# TASK_PERSONAS_V2 v1.3 — Pré-requisitos de Validação

Data: 2026-04-30  
Status: **Em validação** (3/5 bloqueadores + 2/2 recomendados)

---

## 📋 Checklist de Pré-requisitos

### BLOCKERS (Impedem Phase A)

#### ✅ [BLOCKER 1] DeepSeek v4-pro Prompt Caching Support
- **Status**: VALIDADO
- **Resultado**: DeepSeek v4-pro suporta prompt caching automaticamente (default, sem `cache_control` explícito necessário)
- **Custo**: Cache hits = 20% do input normal
- **Retorno API**: `prompt_cache_hit_tokens` + `prompt_cache_miss_tokens` em cada response
- **Implicação**: Personas paralelas reutilizarão contexto do questionário — 85%+ cache hit esperado
- **Documento**: `https://api-docs.deepseek.com/guides/kv_cache`
- **Validado por**: Web search + API docs fetch, 2026-04-30

---

#### ❓ [BLOCKER 2] Definir Critério de "Paridade v1"
- **Status**: PENDENTE DEFINIÇÃO
- **Questão**: Qual é exatamente o benchmark de sucesso para "v2 está tão bom quanto v1"?
- **Proposta**: ≥85% OCG recommendations aligned between v1 pipeline (current Arguidor-only) e v2 pipeline (Personas paralelos)
  - Métrica: Para mesmos 5 projetos piloto, extrair OCG recomendação v1 vs v2, comparar similarity
  - Limiar: Se <85% projects demonstram paridade, rollback flag `PERSONAS_V2_ENABLED` automaticamente
  - Coleta: Rodar pipeline dual (v1 e v2 em paralelo) por 1 semana, análise pós-teste
- **Responsabilidade**: Usuário define; Claude valida critério antes de Phase A
- **Crítico para**: Phase E (Validação com usuário), Phase G (GA + observabilidade)

---

#### ❓ [BLOCKER 3] Especificar Questionnaire Response Flow
- **Status**: PENDENTE DEFINIÇÃO
- **Questão**: Como humanos (GP ou Tech Lead) respondem os questions paravisores v2?
- **Opções**:
  1. **Webhook HTTP POST** — Sistema externo (Jira, Notion, etc) notifica GCA quando question respondida
  2. **Email link + callback** — GCA envia email com link magic, GP clica, UI form embutida, submete
  3. **UI panel inline** — Panel "Esperando decisão humana..." na IngestionPage com form + save
  4. **Hybrid** — Email por default, fallback a UI se fora de horário
- **Dependências**: Choice impacta:
  - Persona.wait_for_human_input() timeout (48h → 96h com escalation per current design)
  - Auditoria trail (qual GP respondeu, timestamp, mudanças de opinião)
  - Notificação (Slack/Teams/Email)
- **Crítico para**: Phase C (Timeout escalation logic), Phase D (Multi-round validation)
- **Responsabilidade**: Usuário escolhe + define UX; Claude implementa

---

#### ❓ [BLOCKER 4] Validar Fallback Mechanism do Auditor
- **Status**: PENDENTE DEFINIÇÃO (RECOMENDADO → BLOCKER se Auditor for single point of failure)
- **Questão**: Se Auditor persona falhar (timeout, modelo indisponível, hallucination detectada), qual é o fallback?
- **Risco**: Auditor é mandatory em Phase B2 (post-CodeGen conflict detection); se falhar, conflitos não são detectados
- **Propostas**:
  1. **Heuristic routing** — Fallback a regras determinísticas (score diffs > 15% = conflict)
  2. **Majority vote** — Se Auditor falha, usar votação simples dos 4 specialists (P1/P4/P5/P6)
  3. **Escalate to human** — Marcar projeto como "needs manual review", notificar Admin
  4. **Retry com Sonnet 4.6** — Se deepseek-v4-pro times out, retry com Claude Sonnet (cost+latency trade-off)
- **Crítico para**: Phase B2 (Conflict detection), Phase F (Escalation)
- **Responsabilidade**: Usuário escolhe estratégia; Claude valida trade-offs antes de code

---

### RECOMENDADOS (Melhoram robustez, não são blockers)

#### ❓ [RECOMMENDED 1] Refatorar conflict_rules/ para módulos isolados
- **Status**: PENDENTE DESIGN
- **Descrição**: Atualmente `conflict_detector.py` é arquivo único com todas as 47 regras de conflito
- **Proposta**: Split em módulos isolados:
  ```
  conflict_rules/
  ├── __init__.py (registry dispatcher)
  ├── category_a_functional.py (5 rules)
  ├── category_b_architecture.py (12 rules)
  ├── category_c_data.py (8 rules)
  ├── category_d_performance.py (11 rules)
  ├── category_e_security_compliance.py (6 rules)
  ├── category_f_cost_vendor.py (5 rules)
  ```
- **Benefício**: Easier testing, clearer ownership, allows external rule injection
- **Não é blocker**: v2 Phase A-D funcionam com structure atual; recomendado antes de Phase G (GA)

---

#### ❓ [RECOMMENDED 2] Implementar Auditor Heuristic Fallback
- **Status**: PENDENTE IMPLEMENTATION
- **Descrição**: Se Auditor persona times out ou falha, ativar regras determinísticas simples
- **Regras heurísticas**:
  - Score diff > 20% em mesmo pilar = conflict
  - Recomendações stack mutualmente excludentes = conflict (e.g., "use REST" vs "use gRPC")
  - Retenção de dados > 7 anos vs LGPD requirement = conflict
- **Não é blocker**: Retry automático + human escalation cobrem maioria dos casos

---

## 📊 Status Resumido

| # | Pré-requisito | Status | Responsável | ETA |
|---|---|---|---|---|
| 1 | DeepSeek caching ✅ | Validado | Claude | ✅ 2026-04-30 |
| 2 | Paridade v1 | Pendente user | Luiz + Claude | TBD |
| 3 | Questionnaire flow | Pendente user | Luiz + Claude | TBD |
| 4 | Auditor fallback | Pendente design | Claude (proposta) | Após #2/#3 |
| 5 | conflict_rules refactor | Recomendado | Claude | Após #2/#3 |

---

## 🚀 Próxima Ação

**Quando usuário define #2 (Paridade v1) e #3 (Questionnaire flow):**
1. Claude valida feasibilidade de cada escolha
2. Calcula impacto em timeline de Phase A-G
3. Propõe trade-offs de #4/#5
4. **Só então**: Recebe autorização explícita (§7.0 contrato) e inicia Phase A

**Critério de "Phase A ready"**: Todos 5 pré-requisitos ≥ "Pendente → Definido" (não necessariamente implementado)

---

## 📎 Referências

- TASK_PERSONAS_V2 v1.3: `/home/luiz/Downloads/TASK_PERSONAS_V2 (2).md`
- DeepSeek Caching Docs: https://api-docs.deepseek.com/guides/kv_cache
- GCA Canonical Contract §7.0: `/home/luiz/GCA/GCA_CANONICAL_CONTRACT.md`
- Previous audit feedback: Session 36 memory (personas paralelos + conflict detection)

