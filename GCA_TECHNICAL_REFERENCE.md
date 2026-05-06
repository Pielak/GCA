# GCA_TECHNICAL_REFERENCE.md — Esquema, Modelos, Endpoints

**Versão:** 2.0  
**Data:** 2026-05-05  
**Status:** Canônico / referência para desenvolvimento

> **Workflow:** `GCA_CLAUDE.md`  
> **Produto:** `GCA_SPECIFICATION.md`  
> **MVPs:** `GCA_MVP_ROADMAP.md`

---

## §1. Schema de Database

### Tabelas Críticas (18+ detectadas)

| Tabela | Propósito | Referências |
|---|---|---|
| `ocg` | OCG canônico por projeto (master table) | 1→N com ingested_documents |
| `ocg_individual` | OCG por documento/persona (MVP 31) | Raw SQL via `text()` |
| `ocg_global` | Consolidação final OCG (MVP 31) | Raw SQL via `text()` |
| `ocg_delta_log` | Auditoria de mudanças OCG (hash chain) | Imutável, versionado |
| `users` | Usuários da instância | FK project_members |
| `projects` | Projetos isolados | 1→N project_members, project_settings |
| `project_members` | Membros do projeto (RBAC) | FK users, projects |
| `project_settings` | Configuração por projeto (LLM, features) | `setting_type='llm'` para provider |
| `project_secrets` | Secrets criptografados com pgcrypto | Vault criptografado |
| `ingested_documents` | Documentos ingeridos | Nova col `parent_document_id` em MVP 34 candidate |
| `module_candidates` | Candidatos de módulo (backlog CodeGen) | 1→N generated_modules |
| `generated_modules` | Módulos gerados (scaffolds) | FK module_candidates |
| `test_specs` | Especificações de teste (ERS vivo) | IEEE 830 |
| `audit_log_global` | Log de auditoria global (hash chain) | Immutable |
| `ai_usage_log` | Rastreamento de uso LLM por criticidade | Criticidade: baixa/média/alta |
| `external_issues` | Integração com Jira/Trello/GitHub Issues | Webhooks |
| `security_findings` | Achados de segurança (SAST) | OWASP categorização |
| `technical_questionnaire` | Questionário técnico + respostas (MVP 35) | 30 regras DSL + LLM sanity |

**~50+ tabelas adicionais** (inferidas via SQL queries). Schema completo requer acesso ao PostgreSQL.

---

## §2. Modelos SQLAlchemy (11 arquivos)

**Localização:** `backend/app/models/`

| Arquivo | Modelo(s) | Relacionamentos |
|---|---|---|
| `auditor_output.py` | `AuditorOutput` | Ref. documento, saída de classificação |
| `base.py` | `Base` (declarative), `OCG`, `OCGDeltaLog` | OCG: 1→N com `ingested_documents` |
| `document_route_map.py` | `DocumentRouteMap` | Auditoria de roteamento de docs |
| `gatekeeper_persona_response.py` | `GatekeeperPersonaResponse` | Respostas das personas no pipeline |
| `human_answer.py` | `HumanAnswer` | Respostas do usuário a HITL |
| `onboarding.py` | `OnboardingStep`, `OnboardingCheckpoint` | Fluxo de onboarding |
| `pillar.py` | `Pillar` | Definição dos 7 pilares do OCG |
| `pipeline_audit.py` | `PipelineAudit` | Auditoria da pipeline n8n |
| `project_member_role.py` | `ProjectMemberRole` | Papel de membro no projeto (RBAC) |
| `tenant.py` | `Tenant` | Dados multi-instância (legado/não-SaaS) |
| `__init__.py` | (exports) | — |

**Nota:** Modelos compactos, sem ORM para `ocg_individual`/`ocg_global` ainda (MVP 31 "decidir"). Queries usam raw SQL via `text()`.

---

## §3. Schemas Pydantic (8 arquivos)

**Localização:** `backend/app/schemas/`

| Arquivo | Schemas | Padrão |
|---|---|---|
| `auditor_output.py` | `AuditorOutputRequest`, `AuditorOutputResponse` | Request/Response |
| `chunk_audit.py` | `ChunkAuditRequest`, `ChunkAuditResult` | Validação de chunks |
| `chunk.py` | `ChunkRequest`, `ChunkResponse` | Chunking e retrieval |
| `gatekeeper.py` | `GatekeeperRequest`, `GatekeeperResponse` | Gate validation |
| `ocg.py` | `OCGResponse`, `OCGReadModel`, pillar scores | Structs internos |
| `questionnaire.py` | `TechnicalQuestionnaireRequest`, `QuestionnaireAnswerResponse` | MVP 35 |
| `user.py` | `UserCreate`, `UserResponse`, `UserUpdate` | CRUD padrão |
| `__init__.py` | (exports) | — |

**Padrão:** Request (input) → Service (business logic) → Response (output).

---

## §4. Funções Canônicas (11 + portas de entrada)

### AIKeyResolver
```python
AIKeyResolver.resolve_project_provider_chain(
    db: AsyncSession, project_id: UUID, include_api_key: bool=False
) → list[dict]
# Retorna cadeia de providers configurados em ordem de preferência
# Arquivo: backend/app/services/ai_key_resolver.py:111

AIKeyResolver.get_gca_key(provider: str=None) → Optional[str]
# Resolve chave global do admin (camada GCA)
# Arquivo: backend/app/services/ai_key_resolver.py:50

AIKeyResolver._resolve_project_provider(
    db: AsyncSession, project_id: UUID
) → Optional[str]
# Lê provedor do projeto em project_settings
# Arquivo: backend/app/services/ai_key_resolver.py:68
```

### VaultService
```python
VaultService.store_secret(
    db: AsyncSession, project_id: UUID, secret_type: str, 
    secret_key: str, secret_value: str, created_by: UUID=None
) → bool
# Criptografa + armazena secret via pgcrypto
# Arquivo: backend/app/services/vault_service.py:26

VaultService.get_secret(
    db, project_id, secret_type, secret_key
) → Optional[str]
# Descriptografa + lê secret do vault
# Arquivo: backend/app/services/vault_service.py
```

### Security & RBAC
```python
generate_temporary_password() → str
# Gera senha temporária canônica (RF-001: 10 chars, 1+ maiúscula, 1+ dígito, 1+ especial)
# Arquivo: backend/app/core/security.py:64

is_active_integrated_member(member: ProjectMember) → bool
# Filtra is_active AND joined_at IS NOT NULL (evita convites pendentes)
# Arquivo: backend/app/services/project_team_service.py:39
```

### OCG & Gatekeeper
```python
OCGUpdaterService.update_ocg_from_arguider(
    self, project_id: UUID, persona_analysis: dict
) → dict
# Aplica análise da persona ao OCG respeitando invariantes
# Arquivo: backend/app/services/ocg_updater_service.py:257

OCGUpdaterService._load_persona_scores(
    self, project_id: UUID
) → dict
# Carrega scores das 12 personas de ocg_individual
# Arquivo: backend/app/services/ocg_updater_service.py:888

OCGUpdaterService._filter_negative_score_deltas(
    old_pillars: dict, new_pillars: dict
) → dict
# Filtra deltas negativos (OCG não contrai)
# Arquivo: backend/app/services/ocg_updater_service.py:98

check_ocg_maturity_gate(
    project_id: UUID, db: AsyncSession
)
# Valida OCG ≥ 95% em todos pilares antes de CodeGen
# Arquivo: backend/app/services/ocg_gate.py

evaluate_ocg_maturity(
    project_id: UUID, db: AsyncSession
) → OCGGateResult
# Avalia maturidade OCG sem levantar exceção (workers Celery)
# Arquivo: backend/app/services/ocg_gate.py:90
```

---

## §5. Endpoints HTTP (389 em 56 routers)

**Padrão:** `GET/POST/PUT/DELETE /api/v1/{resource}`

### Core Routers

| Router | Propósito | Endpoints |
|---|---|---|
| `admin.py` | Admin global (usuários, instância) | 15+ |
| `auth.py` | Autenticação/login | 8 |
| `projects.py` | CRUD projetos | 12 |
| `ingestion_router.py` | Ingestão de documentos | 10 |
| `code_generation.py` | CodeGen scaffold/apply | 8 |
| `gatekeeper_router.py` | Gatekeeper v2 (principal) | 14 |
| `module_router.py` | Módulos (candidatos + gerados) | 16 |
| `ers_router.py` | ERS vivo (IEEE 830) | 11 |

### Especialidades

| Router | Propósito |
|---|---|
| `pipeline_orchestration_router.py` | Orquestração n8n |
| `technical_questionnaire_router.py` | Questionário técnico (novo MVP 35) |
| `iterative_questionnaire_router.py` | Questionário iterativo HITL |
| `pipeline_questions_router.py` | HITL questions |
| `livedocs_router.py` | LiveDocs + versionamento |
| `webhooks.py` | Webhooks (n8n, externos) |
| `external_repos_router.py` | Repos externos (Git integrações) |
| `github.py` | GitHub webhooks |
| `figma_router.py` | Figma integration |
| `gatekeeper_router.py` | Gate validation |
| `member_roles_router.py` | RBAC de projeto |
| `settings_router.py` | Settings de projeto (LLM, etc) |

**Total:** 56 arquivos router, 389 rotas documentadas.

---

## §6. Migrations (72 SQL files)

**Sistema:** Plain SQL (não Alembic).  
**Localização:** `backend/migrations/`

### Últimas 10 migrations

```
072_b5_pfq_nullable_origem.sql
071_b4_...
070_saneamento_dba_bundlado_pós_gatekeeper.sql
069_mvp35_questionnaire_validation.sql
068_mvp34_revert_document_delete_cascades.sql
067_mvp34_parent_document_fk.sql
...
001_add_password_reset_tables.sql
```

**Status:** Aplicadas em init.

---

## §7. Workflow n8n (12 personas)

**Detecção via código:**

- 12 workflows ativos (um por persona): AUD, GP, ARQ, DBA, DEV, QA, UX, UI, SEG, CONF, LGPD, NEG
- Webhook entry: `/api/v1/webhooks/n8n/{persona_tag}`
- Payload: `ocg_summary`, `documento`, `persona_prompts` (via registry)
- Consolidador (Redis accumulator): coleta 12 respostas → update OCG único
- Timeout: 900s (30min em alguns casos)

**Referência:** `backend/app/services/personas/prompts_registry.py` (68 linhas).

---

## §8. 12 Personas LLM (Conjunto B)

**Localização:** `backend/app/services/personas/`

| Tag | Persona | Arquivo | Status | Propósito |
|---|---|---|---|---|
| AUD | Auditor (Router) | `auditor.py` | ✅ | Classificação + fan-out |
| GP | Gerente de Projetos | `gp.py` | ✅ | Orquestrador |
| ARQ | Arquiteto | `arq.py` | ✅ | Stack + padrões |
| DBA | DBA | `dba.py` | ✅ | Schema + retenção |
| DEV | Dev Sênior | `dev.py` | ✅ | Implementabilidade |
| QA | QA/Tester | `qa.py` | ✅ | Testes + cobertura |
| UX | UX Designer | `ux.py` | ✅ | Jornada + acessibilidade |
| UI | UI Designer | `ui.py` | ✅ | Design system |
| SEG | Security Engineer | `seg.py` | ✅ | OWASP + auth |
| CONF | Conformidade **BLOQUEANTE** | `conf.py` | ✅ | Score <60 bloqueia |
| LGPD | Proteção de Dados | `lgpd.py` | ✅ | PII + retenção |
| NEG | Negócio | `negocios.py` | ✅ | Valor + ROI |

**Suporte:**
- Base: `base.py` (145L)
- Registry: `prompts_registry.py` (68L)
- OCG: `ocg_sections_instructions.py` (202L)

---

**Última atualização:** 2026-05-05 (Fase 2)
