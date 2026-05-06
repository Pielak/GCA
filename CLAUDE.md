# GCA_CLAUDE.md — Instruções Operacionais para Claude Code

**Objetivo:** Guia compacto de workflow, papéis, invariantes e portas de entrada para trabalhar no GCA.

---

## 1. Papéis RBAC — Conjunto A (5 papéis imutáveis)

| Papel | Escopo | Autoridades |
|-------|--------|-------------|
| **Admin** | Instância | Configura provedores, aprova projetos, operações globais |
| **GP** | Projeto | Soberano do projeto (emenda 2026-04-19); opera CodeGen, pipeline |
| **Dev** | Código | Implementa, ingestão, Arguidor; não aprova no Gatekeeper |
| **Tester** | Testes | Cria/executa testes, registra evidências |
| **QA** | Qualidade | Revisa/aprova resultados, valida maturity final |

**Porta de verificação:** `is_active_integrated_member()` — filtra `is_active AND joined_at IS NOT NULL`.

---

## 2. 12 Personas LLM — Conjunto B (agentes de IA, não humanos)

NÃO são papéis humanos. Validam documentos no pipeline n8n em paralelo (fan-out).

| Tag | Persona | Papel |
|-----|---------|-------|
| AUD | Auditor | Router — classifica doc, despacha para especialistas |
| GP | Gerente de Projetos | **Orquestrador** — supervisiona equipe, arbitragem final |
| ARQ | Arquiteto | Valida stack, padrões, NFRs |
| DBA | DBA | Valida schema, migrações, retenção |
| DEV | Dev Sênior | Valida implementabilidade, dependências |
| QA | QA | Valida testes, cobertura, BDD |
| UX | UX Designer | Jornada, acessibilidade, WCAG |
| UI | UI Designer | Design system, responsividade |
| SEG | Security | OWASP, AuthN/Z, superfície de ataque |
| **CONF** | **Conformidade** | **BLOQUEANTE** — score < 60 bloqueia ingestão |
| LGPD | Proteção de Dados | Dados pessoais, base legal, retenção |
| NEG | Negócio | Valor estratégico, ROI, risco |

**Porta única:** `prompts_registry.py` → `PERSONA_PROMPTS` dict com 12 system prompts + OCG addendum.

---

## 3. OCG — Invariantes Canônicas

### Regra 1: OCG Não Contrai
- ✅ OCG cresce com informação útil
- ❌ OCG não sobrescreve, não descarta
- Ingestão ruim → documento vai para **quarentena**, OCG intocado

### Regra 2: OCG Versionado
- Tabela `ocg_delta_log` — hash chain imutável
- Cada change → `change_type`, `trigger_source`, `ocg_delta_log` entry
- Auditável, reversível

### Regra 3: OCG Gate ≥95%
- **Limiar:** `SCORE_MATURIDADE = 95` em `backend/app/services/ocg_gate.py:64`
- **Decisão GP 2 (2026-05-04):** Todos 7 pilares (P1-P7) devem estar ≥95%
- Um pilar abaixo → **pillar_immature** → CodeGen bloqueado
- 5 níveis: `hard_block` | `insufficient` (<60) | `immature` (<95) | `pillar_immature` | `no_ocg`

**Porta:** `check_ocg_maturity_gate()` levanta HTTPException 409 em endpoints; `evaluate_ocg_maturity()` para workers.

---

## 4. Governança de IA — Provider Agnóstico

### Porta Única
`AIKeyResolver.resolve_project_provider_chain(db, project_id, include_api_key=False)` → lista de providers em ordem de preferência.

### Camadas
1. **GCA Admin** — chave global (settings)
2. **Projeto (GP)** — chaves via vault + `project_settings` (setting_type='llm')

### Criticidade (Contrato §6.2)
- **Baixa:** Classificação, extração, normalização → modelo local/Ollama ✅
- **Média:** Perguntas dirigidas, pré-análise → qualquer provider ✅
- **Alta:** OCG consolidação, Gatekeeper, CodeGen crítico → **modelo premium obrigatório** ❌ fallback automático proibido

### Providers Implementados
- ✅ Anthropic (AnthropicLLMClient)
- ✅ OpenAI (OpenAIClient)
- ✅ DeepSeek (DeepSeekClient)
- ❌ Gemini, Ollama (não implementados)

**DTs abertas:**
- **DT-079** — Hardcode Anthropic em `module_codegen_service.py:164-165` (investigação Gate 2 em aberto)

---

## 5. Processamento Binário — Sem Erro Silencioso

**Regra absoluta (CLAUDE.md §0):**

```python
try:
    # operação
except Exception as e:
    logger.error(...); raise  # NUNCA except: pass
```

Se operação não pode falhar → documentar por quê (garantia do framework, validação anterior).

---

## 6. Fluxo Gatekeeper — 5 Porteiros Sequenciais

Ordem fixa. **Não pular.**

```
1. Gerente de Projetos — escopo, viabilidade, negócio
   ↓ Aprovado
2. Arquiteto — stack, padrões, NFRs
   ↓ Aprovado
3. DBA — schema, migrations, retenção (PULE se não-DB)
   ↓ Aprovado/N/A
4. Dev Sênior — implementação
   ↓ Concluído
5. Tester/QA — testes, cobertura, regressão
   ↓ Aprovado
→ preparar-release (skill) — checklist final
```

Cada porteiro responde: **Veredito | Achados | Riscos | Correções obrigatórias | SHOULD | Arquivos | Aceite | Próxima ação**.

---

## 7. Entrada Padrão: Questionnaire → Ingestão → Pipeline n8n → Consolidação

### Path Canônico (MVP 35 + MVP 34)

1. **Questionário Técnico** — 2 camadas validação:
   - Camada 1 (RulesEvaluator) — 30 regras DSL determinísticas
   - Camada 2 (LLM sanity) — verificação semântica
2. **Ingestão** — upload documento + análise conformidade
3. **Pipeline n8n** — 12 personas em paralelo (135s com DeepSeek)
   - AUD classifica → fan-out aos 11 especialistas
   - Consolidador (Redis) agrega 12 respostas → update OCG único
4. **Soft-delete + revert** — GP pode deletar documento:
   - Soft-delete (`deleted_at IS NOT NULL`)
   - OCGUpdaterService recomputa ignorando doc deletado
   - `ocg_delta_log` entry → `REVERT_DOCUMENT_DELETE`
   - Módulos órfãos → `archived`

---

## 8. Vault — Secrets Criptografados

### Porta Única
```python
await VaultService.store_secret(
    db, project_id, secret_type, secret_key, secret_value, created_by
)
await VaultService.get_secret(db, project_id, secret_type, secret_key)
```

### Criptografia
- Cipher: pgcrypto (`pgp_sym_encrypt/decrypt`)
- Master key: `GCA_MASTER_KEY` (32+ chars em .env)
- PAT Git: prefixo obrigatório `fernet:v1:`

**Atenção:** `store_secret()` commita internamente → não chame dentro `session.begin()`.

---

## 9. Senhas Temporárias (Convites)

**Porta:** `generate_temporary_password()` em `backend/app/core/security.py:64`.

**Spec (RF-001):**
- Exatamente 10 caracteres
- ≥1 maiúscula, ≥1 dígito, ≥1 especial (!@#$%^&*)
- Gera via secrets.choice + shuffle

**Nunca usar:** `secrets.token_urlsafe(12)` ← não atende RF-001.

---

## 10. Histórico de MVPs e DTs

**MVPs recentes (2026-05-02/03):**
- MVP 35 — Validação Questionário (3 gates, 90/110 testes)
- MVP 34 — Revert Document Delete (3 gates, 15/15 testes)
- MVP 33 — Personas 12 LLM (10/10 testes)
- MVP 32 — OCG Updater (hot-fix quitado)
- MVP 31 — OCG Gate + CodeGen (35/35 testes)

**DTs abertas (8):**
- DT-079 (Major) — Hardcode Anthropic
- DT-080, 082, 083, 084 (Minor)
- DT-086 (Major, future) — Purge LGPD
- DT-087 (Minor) — FK `uploaded_by`

**Candidatos (não autorizados):**
- F4.2 — Chunker estrutural
- F4.3 — Accumulator + OCG único (aguarda endosso cliente)
- MVP 26 — AI Governance Moat

---

## 11. Plan Mode Obrigatório

Usar `EnterPlanMode` antes de:
- Mudanças em AIKeyResolver, RBAC, VaultService, migrações
- Mudanças em OCG, Gatekeeper, Personas
- Refactors multi-arquivo

---

## 12. Stack Detalhado

- **Backend:** FastAPI, SQLAlchemy 2.0+ async, PostgreSQL+asyncpg, Celery→Dramatiq, Redis
- **Frontend:** React/Next.js, Vite, Tailwind
- **IA:** Anthropic/OpenAI/DeepSeek SDK
- **Orquestração:** n8n (personas), Nginx (proxy)
- **Migrations:** 72 arquivos SQL (não Alembic) em `backend/migrations/`
- **Testes:** pytest, factory-boy, ~245+ passing (último reporte)

---

## 13. Regra Crítica: Erro Determinístico, Nunca Silencioso

- Falha autenticação → 401/403, mensagem clara
- Config ausente → rejeita (não fallback)
- Query pesada → log + executa (sem otimização oculta)
- Erro de parsing → bloqueia + relata (não assume default)

---

**Última atualização:** 2026-05-05 (Fase 2 reorganização)
