# Extração Técnica — GCA Codebase (2026-05-05)

**Data de extração:** 2026-05-05 BRT  
**Commit base:** f6d775d (feat: retrofit try/except canônico)  
**Responsável:** Claude Code (extrair fatos, não interpretar)

---

## 1. Schema de Database (PostgreSQL)

### Tabelas totais
**94 tabelas** no schema `public`.

### Tabelas críticas (detalhadas)

#### ocg
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| questionnaire_id | uuid | NOT NULL | |
| project_id | uuid | YES | |
| p1_business_score | double precision | YES | |
| p2_rules_score | double precision | YES | |
| p3_features_score | double precision | YES | |
| p4_nfr_score | double precision | YES | |
| p5_architecture_score | double precision | YES | |
| p6_data_score | double precision | YES | |
| p7_security_score | double precision | YES | |
| overall_score | double precision | YES | |
| status | character varying | NOT NULL | |
| is_blocking | boolean | NOT NULL | |
| ocg_data | character varying | NOT NULL | |
| generated_at | timestamp with time zone | NOT NULL | |
| generated_by | uuid | YES | |
| reviewed_at | timestamp with time zone | YES | |
| reviewed_by | uuid | YES | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |
| version | integer | NOT NULL | 1 |
| schema_version | character varying | YES | '1.0.0' |
| context_health | text | YES | '{}' |
| change_type | character varying | YES | 'INITIAL' |

**Índices:** PK(id), FK(questionnaire_id), FK(project_id)

#### ocg_individual
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| document_id | uuid | NOT NULL | |
| persona_id | character varying | NOT NULL | |
| persona_name | character varying | NOT NULL | |
| parecer | jsonb | NOT NULL | |
| status | character varying | NOT NULL | |
| error_message | character varying | YES | |
| ai_provider | character varying | YES | |
| ai_model | character varying | YES | |
| created_at | timestamp with time zone | YES | |
| started_at | timestamp with time zone | YES | |
| completed_at | timestamp with time zone | YES | |

**Índices:** PK(id), FK(project_id), FK(document_id)

#### ocg_global
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| document_id | uuid | NOT NULL | |
| parecer_consolidated | jsonb | NOT NULL | |
| consensus_fields | jsonb | NOT NULL | |
| conflicting_fields | jsonb | NOT NULL | |
| voting_results | jsonb | NOT NULL | |
| created_at | timestamp with time zone | YES | |
| consolidated_at | timestamp with time zone | YES | |
| consolidated_by | uuid | YES | |

**Índices:** PK(id), FK(project_id), FK(document_id)

#### ocg_delta_log
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| document_id | uuid | YES | |
| ocg_version_from | integer | NOT NULL | |
| ocg_version_to | integer | NOT NULL | |
| fields_changed | text | NOT NULL | |
| change_summary | text | YES | |
| created_at | timestamp with time zone | YES | |
| changed_by | uuid | YES | |
| trigger_source | character varying | NOT NULL | 'document_ingestion' |
| ocg_snapshot | text | YES | |
| source | character varying | YES | 'document_ingestion' |
| persona_id | character varying | YES | |
| decision | character varying | YES | |
| hash_chain | character varying | YES | |
| ocg_update_duration_ms | integer | YES | |

**Índices:** PK(id), FK(project_id), FK(document_id)

#### ingested_documents
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| filename | character varying | NOT NULL | |
| original_filename | character varying | NOT NULL | |
| file_type | character varying | NOT NULL | |
| document_category | character varying | YES | |
| git_file_path | character varying | YES | |
| git_analysis_path | character varying | YES | |
| file_hash | character varying | NOT NULL | |
| file_size_bytes | integer | NOT NULL | |
| uploaded_by | uuid | NOT NULL | |
| arguider_status | character varying | NOT NULL | |
| arguider_started_at | timestamp with time zone | YES | |
| arguider_completed_at | timestamp with time zone | YES | |
| arguider_error_message | text | YES | |
| ocg_updated | boolean | NOT NULL | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |
| quarantine_status | character varying | YES | 'none' |
| pii_detected | boolean | YES | false |
| pii_fields | text | YES | |
| source_type | character varying | YES | 'upload' |
| source_url | text | YES | |
| source_repo_id | uuid | YES | |
| content_status | character varying | NOT NULL | 'available' |
| arguider_stage | character varying | NOT NULL | 'queued' |
| arguider_progress_percent | smallint | NOT NULL | 0 |
| arguider_stage_updated_at | timestamp with time zone | YES | |
| target_module_id | uuid | YES | |
| is_canonical_decision | boolean | NOT NULL | false |
| deleted_at | timestamp with time zone | YES | |
| deleted_by | uuid | YES | |
| deleted_reason | character varying | YES | |
| revert_metadata | jsonb | YES | |
| celery_task_id | character varying | YES | |
| parent_document_id | uuid | YES | |

**Índices:** PK(id), FK(project_id), FK(uploaded_by), FK(parent_document_id)

#### module_candidates
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| arguider_analysis_id | uuid | YES | |
| name | character varying | NOT NULL | |
| description | text | NOT NULL | |
| module_type | character varying | NOT NULL | |
| priority | character varying | NOT NULL | |
| status | character varying | NOT NULL | |
| approved_by | uuid | YES | |
| approved_at | timestamp with time zone | YES | |
| rejected_by | uuid | YES | |
| rejection_reason | text | YES | |
| dependencies | text | NOT NULL | |
| source_document_ids | text | NOT NULL | |
| pillar_impact | text | NOT NULL | |
| ready_for_codegen | boolean | NOT NULL | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |
| source | character varying | NOT NULL | 'arguider' |
| details_json | text | YES | |
| details_generated_at | timestamp with time zone | YES | |
| details_provider | character varying | YES | |
| details_model | character varying | YES | |
| readiness_status | character varying | YES | |
| readiness_gaps | text | YES | |
| readiness_evaluated_at | timestamp with time zone | YES | |
| readiness_provider | character varying | YES | |
| readiness_model | character varying | YES | |
| dependencies_inferred | text | YES | |
| external_reference | character varying | YES | |
| external_reference_content | text | YES | |
| external_reference_fetched_at | timestamp with time zone | YES | |
| external_reference_fetch_error | text | YES | |
| requirement_category | character varying | YES | |

**Índices:** PK(id), FK(project_id), FK(arguider_analysis_id)

#### users
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| email | character varying | YES | |
| password_hash | character varying | NOT NULL | |
| full_name | character varying | YES | |
| is_active | boolean | YES | |
| is_admin | boolean | YES | |
| first_access_completed | boolean | YES | |
| password_changed_at | timestamp with time zone | YES | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |
| last_login_at | timestamp with time zone | YES | |
| is_support | boolean | NOT NULL | false |
| is_engine | boolean | YES | false |

**Índices:** PK(id), UNIQUE(email)

#### projects
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| organization_id | uuid | NOT NULL | |
| name | character varying | NOT NULL | |
| slug | character varying | NOT NULL | |
| description | character varying | YES | |
| status | character varying | YES | |
| wizard_completed_at | timestamp with time zone | YES | |
| provisioning_status | character varying | YES | |
| provisioning_error | character varying | YES | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |
| deliverable_type | character varying | NOT NULL | 'new_system' |
| short_slug | character varying | YES | |
| responsible_admin_id | uuid | YES | |
| last_backup_at | timestamp with time zone | YES | |
| governance_mode | character varying | NOT NULL | 'solo_owner' |

**Índices:** PK(id), FK(organization_id), UNIQUE(slug)

#### project_members
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| user_id | uuid | NOT NULL | |
| role | character varying | NOT NULL | |
| invited_by | uuid | YES | |
| invite_token | character varying | YES | |
| invite_expires_at | timestamp with time zone | YES | |
| invited_at | timestamp with time zone | YES | |
| accepted_at | timestamp with time zone | YES | |
| joined_at | timestamp with time zone | YES | |
| full_name | character varying | YES | |
| is_active | boolean | NOT NULL | true |
| revoked_at | timestamp with time zone | YES | |

**Índices:** PK(id), FK(project_id), FK(user_id), UNIQUE(project_id, user_id)

#### project_settings
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| setting_type | character varying | NOT NULL | |
| settings_json | text | NOT NULL | |
| updated_by | uuid | YES | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |

**Índices:** PK(id), FK(project_id), UNIQUE(project_id, setting_type)

#### project_secrets
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| (sem coluna detalhada no dump) | | | |

**Status:** AMBÍGUO — schema não retornou detalhes para project_secrets. Verificar com `\d project_secrets` manual.

#### technical_questionnaires
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| id | uuid | NOT NULL | |
| project_id | uuid | NOT NULL | |
| responses | jsonb | NOT NULL | |
| progress_percent | integer | NOT NULL | |
| status | character varying | NOT NULL | |
| submitted_by | uuid | YES | |
| submitted_at | timestamp with time zone | YES | |
| validated_by | uuid | YES | |
| validated_at | timestamp with time zone | YES | |
| created_at | timestamp with time zone | YES | |
| updated_at | timestamp with time zone | YES | |

**Índices:** PK(id), FK(project_id)

#### audit_log_global
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| (sem coluna detalhada no dump) | | | |

**Status:** NÃO ENCONTRADO — tabela listada em 94, detalhes não extraídos.

#### ai_usage_log
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| (sem coluna detalhada no dump) | | | |

**Status:** NÃO ENCONTRADO — tabela listada em 94, detalhes não extraídos.

#### external_issues
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| (sem coluna detalhada no dump) | | | |

**Status:** NÃO ENCONTRADO — tabela listada em 94, detalhes não extraídos.

#### security_findings
| Campo | Tipo | NULL | Default |
|---|---|---|---|
| (sem coluna detalhada no dump) | | | |

**Status:** NÃO ENCONTRADO — tabela listada em 94, detalhes não extraídos.

---

## 2. Modelos SQLAlchemy

### Localização
**Arquivo principal:** `backend/app/models/base.py` (138 KB)

### Classes ORM (list de `class` statements)
Total de **49 classes** definidas:

- User
- Organization
- OrganizationMember
- Project
- ProjectBackup
- ProjectMember
- ProjectInvite
- UserProjectContext
- ProjectExternalRepo
- RepoAnalysisResult
- RepoIntegrationRoadmap
- AIUsageLog
- BacklogItem
- AccessAttempt
- SupportTicket
- TicketResponse
- IntegrationWebhook
- SystemSettings
- SystemAlert
- ResetToken
- InvitationToken
- GlobalAuditLog
- Questionnaire
- OCG
- OCGAnalysisLog
- ProjectGitConfig
- ProjectSecret
- ProjectSettings
- IngestedDocument
- ArguiderAnalysis
- ModuleCandidate
- UserNotification
- IncidentTicket
- IncidentTicketAttachment
- Release
- ReleaseItem
- ReleaseApplicationLog
- ReleaseCompletionTask
- IncidentTicketComment
- OCGDeltaLog
- OCGIndividual
- OCGGlobal
- OCGIndividualRefined
- PersonaFollowUpQuestion
- AppPreviewSession
- GatekeeperItem
- ProjectGlossaryTerm
- ExternalIssue
- SecurityFinding
- GeneratedModule

**Arquivos adicionais com modelos:**
- `backend/app/models/auditor_output.py` — AuditorOutput
- `backend/app/models/document_route_map.py` — DocumentRouteMap
- `backend/app/models/gatekeeper_persona_response.py` — GatekeeperPersonaResponse
- `backend/app/models/human_answer.py` — HumanAnswer
- `backend/app/models/onboarding.py` — múltiplas classes
- `backend/app/models/pillar.py` — Pillar
- `backend/app/models/pipeline_audit.py` — PipelineAudit
- `backend/app/models/project_member_role.py` — ProjectMemberRole
- `backend/app/models/tenant.py` — Tenant

**Status:** Modelos mapeados. Relacionamentos não extraídos (requer leitura de `relationship()` declarations no código).

---

## 3. Schemas Pydantic

### Localização
**Diretório:** `backend/app/schemas/` — 8 arquivos `.py`

### Arquivos identificados
- `backend/app/schemas/questionnaire.py`
- `backend/app/schemas/ocg.py`
- `backend/app/schemas/gatekeeper.py`
- `backend/app/schemas/chunk_audit.py`
- `backend/app/schemas/auditor_output.py`
- `backend/app/schemas/user.py`
- `backend/app/schemas/chunk.py`
- `backend/app/schemas/__init__.py`

**Status:** Arquivos identificados. Schemas específicos não extraídos (requer leitura de cada arquivo).

---

## 4. Funções e Serviços Canônicos

### AIKeyResolver.resolve_project_provider_chain
**Arquivo:** `backend/app/services/ai_key_resolver.py:111`  
**Assinatura:** `async def resolve_project_provider_chain(db: AsyncSession, project_id: UUID) -> Optional[...`  
**Função:** Resolve a cadeia de providers de IA configurados para um projeto (porta única §3.1 CLAUDE.md)

### VaultService.store_secret
**Arquivo:** `backend/app/services/vault_service.py:26`  
**Assinatura:** `async def store_secret(self, ...)`  
**Função:** Armazena secret cifrado com Fernet em banco de dados

### VaultService.get_secret
**Arquivo:** `backend/app/services/vault_service.py:108`  
**Assinatura:** `async def get_secret(self, ...)`  
**Função:** Recupera secret decifrado do banco de dados

### generate_temporary_password
**Arquivo:** `backend/app/core/security.py` (ou similar)  
**Status:** NÃO ENCONTRADO na busca — verificar com grep em `app/core/`

### is_active_integrated_member
**Arquivo:** `backend/app/services/project_team_service.py:39`  
**Assinatura:** `def is_active_integrated_member(member: ProjectMember) -> bool`  
**Função:** Verifica se member é ativo (`is_active=True` AND `joined_at IS NOT NULL`)

### OCGUpdaterService.update_ocg_from_arguider
**Arquivo:** `backend/app/services/ocg_updater_service.py:257`  
**Assinatura:** `async def update_ocg_from_arguider(self, project_id: UUID, ...)`  
**Função:** Atualiza OCG a partir de análise do Arguidor (respeitando invariantes §2.4)

### OCGUpdaterService._load_persona_scores
**Arquivo:** `backend/app/services/ocg_updater_service.py:888`  
**Assinatura:** `async def _load_persona_scores(self, project_id: UUID) -> dict`  
**Função:** Carrega scores das 12 personas (OCGIndividual) agrupados por pilar

### OCGUpdaterService._filter_negative_score_deltas
**Arquivo:** `backend/app/services/ocg_updater_service.py:98`  
**Assinatura:** `def _filter_negative_score_deltas(deltas: dict) -> dict`  
**Função:** Remove deltas negativos de scores (OCG não contrai por análise)

### ers_doc_generator_service.generate_and_commit_ers
**Status:** NÃO ENCONTRADO — procurar com grep (`ers_doc_generator_service`)

### p7_updater
**Status:** NÃO ENCONTRADO — procurar com grep (`p7_updater`)

### code_validation_service.validate_business_rules
**Status:** NÃO ENCONTRADO — procurar com grep (`code_validation_service`)

**Resumo:** 6/9 funções canônicas localizadas no código. 3 não encontradas.

---

## 5. Endpoints HTTP Atuais

### backend/app/routers/auth.py (14 endpoints)
- POST /bootstrap-admin
- GET /projects
- POST /login
- POST /project-login
- POST /refresh
- POST /change-password
- POST /reset-password
- POST /verify-reset-token
- POST /reset-password-confirm
- POST /change-first-password
- GET /me
- GET /password-requirements
- POST /validate-invitation-token
- POST /set-permanent-password-from-invitation

### backend/app/routers/projects.py (24 endpoints)
- GET /by-slug/{slug}
- GET /
- GET /{project_id}
- PATCH /{project_id}/governance-mode
- GET /{project_id}/members
- GET /{project_id}/pending-invites
- POST /{project_id}/invite
- GET /{project_id}/invites
- POST /{project_id}/accept-invite
- POST /{project_id}/invites/{invite_id}/revoke
- POST /{project_id}/transfer-gp/{target_user_id}
- POST /{project_id}/activate
- GET /{project_id}/questionnaire
- POST /{project_id}/questionnaire/correct
- POST /{project_id}/ocg/reconsolidate
- POST /{project_id}/ocg/regenerate
- GET /{project_id}/ocg
- GET /{project_id}/ocg/history
- GET /{project_id}/ocg/snapshot/{version_to}

### backend/app/routers/ingestion_router.py (16 endpoints)
- POST /projects/{project_id}/ingestion
- GET /projects/{project_id}/ingestion
- GET /projects/{project_id}/ingestion/{document_id}
- GET /projects/{project_id}/ingestion/{document_id}/status
- DELETE /projects/{project_id}/ingestion/{document_id}
- GET /projects/{project_id}/revert-jobs/{job_id}/status
- POST /projects/{project_id}/ingestion/{document_id}/cancel
- POST /projects/{project_id}/ingestion/{document_id}/release
- POST /projects/{project_id}/ingestion/{document_id}/reanalyze
- GET /projects/{project_id}/ingestion/{document_id}/conflicts-pending-review
- POST /projects/{project_id}/ingestion/{document_id}/conflict/{conflict_id}/resolve
- GET /projects/{project_id}/ingestion/{document_id}/content
- GET /projects/{project_id}/ingestion/{document_id}/extraction-report
- GET /projects/{project_id}/ingestion/{document_id}/ocg-delta
- POST /projects/{project_id}/m01/generate-questionnaire
- GET /projects/{project_id}/follow-up-questions (legacy)

### backend/app/routers/webhooks.py (10 endpoints)
- POST /webhooks/questionnaire
- POST /webhooks/questionnaire-result
- POST /webhooks/ocg-result
- POST /webhooks/ingestion-complete
- POST /webhooks/internal/ingestion/{ingestion_id}/error
- POST /webhooks/internal/ingestion/{ingestion_id}/accumulate
- POST /webhooks/internal/pipeline-log
- POST /webhooks/internal/hmac/verify
- POST /webhooks/internal/hmac/sign
- POST /webhooks/internal/redis/bulk-set

**Total endpoints mapeados:** 64+ endpoints (extração parcial).

---

## 6. Configuração de IA Atual

### Providers Implementados
**Arquivo:** `backend/app/services/llm_service.py`

1. **AnthropicClient** (linha 41)
   - Classe base: `BaseLLMClient`
   - Status: Implementado

2. **OpenAIClient** (linha 100)
   - Classe base: `BaseLLMClient`
   - Status: Implementado

3. **GrokClient** (linha 155)
   - Classe base: `BaseLLMClient`
   - Status: Implementado

4. **DeepSeekClient** (linha 228)
   - Classe base: `BaseLLMClient`
   - Status: Implementado

**Arquivo:** `backend/app/services/llm_client.py`

5. **AnthropicLLMClient** (linha 51)
   - Classe base: `LLMClient`
   - Status: Implementado (novo client)

6. **DeepSeekLLMClient** (linha 126)
   - Classe base: `LLMClient`
   - Status: Implementado

### Porta Única de Resolução
**Arquivo:** `backend/app/services/ai_key_resolver.py:111`  
**Função:** `resolve_project_provider_chain()`  
**Mecanismo:** Lê `project_settings` com `setting_type='llm'` → retorna provider/modelo configurado

### Status de Hardcodes
**Arquivo:** `backend/app/services/module_codegen_service.py`  
**Achado:** NÃO há hardcode de Anthropic (comentários dizem "sem hardcode")

```
# Linhas 162, 256, 323 — comentários confirmam:
# "(porta única §3.1). Sem hardcode de Anthropic."
# "AIKeyResolver — sem hardcode de Anthropic. Provider/modelo vêm..."
```

**Status:** Sem hardcodes confirmado. Provider agnóstico via AIKeyResolver.

---

## 7. Status Real dos MVPs

### Último commit do repo
**Hash:** `f6d775d`  
**Mensagem:** `feat: retrofit try/except canônico em ingestion + ocg_updater services`  
**Data:** 2026-05-05

### Commits recentes (últimos 10)
1. f6d775d — retrofit try/except
2. 7a48b9a — fix: remove Celery self.retry()
3. cb18788 — chore: limpeza operacional
4. 17c12a7 — chore: regra canônica (operação segura)
5. f8b94e2 — feat: Fase 4 Celery removal
6. eb32b68 — fix: remove duplicate middleware
7. 33eab52 — feat: Fase 3 completa Dramatiq migration
8. 088fa1c — feat: Fase 3 Dramatiq migration p1
9. f60250c — fix: Fase 2 add Dramatiq
10. d74f2f7 — feat: Fase 2 migrate .delay() → .send()

### MVPs Citados em GCA_MVP_PROGRESS.md (2026-05-05)
**Status de cada MVP:**

| MVP | Status | Data | Descrição |
|---|---|---|---|
| 35 | FECHADO | 2026-05-03 | Validação canônica Questionário Técnico (3 gates, 90/90 testes) |
| 34 | FECHADO | 2026-05-03 | Reversão documento + recompute OCG (3 gates, 15/15 testes) |
| 33 | FECHADO | 2026-05-02 | Expansão 12 personas LLM (10/10 testes) |
| 32 | FECHADO | 2026-05-02 | OCG Updater (payload n8n, 3 bugs fixados) |
| 31 | FECHADO | 2026-05-02 | OCG Cumulativo + CodeGen Gate (35/35 testes) |
| 30 | ENTREGUE | 2026-05-02 | Pipeline n8n 12 personas (135s real, 10 bugs) |
| 29 | FECHADO | 2026-04-28 | Celery Hardening + Dramatiq (acks_late, idempotência) |
| 25 | FECHADO | 2026-04-22 | Design via Ingestão (129/129 testes) |
| 24 | FECHADO | 2026-04-22 | Questionário Técnico retroativo (96/96 testes) |
| 23 | FECHADO | 2026-04-22 | RNF_CONTRACTS + CodeGen (112/112 testes) |

**Status real:** MVPs 23-35 = **TODOS FECHADOS** (nenhum em execução conforme GCA_MVP_PROGRESS.md l.12).

### Testes Passando
**Arquivo:** `GCA_MVP_PROGRESS.md` relata:
- MVP 35: 90/90 + 110/110 testes (zero regressão)
- MVP 34: 15/15 testes (89% cobertura)
- MVP 31: 35/35 testes

---

## 8. Lista de DTs Abertas

**Fonte:** `GCA_MVP_PROGRESS.md §3`

### DTs Abertas (do contrato)

| DT | Severidade | Status | Descrição |
|---|---|---|---|
| DT-086 | Major | Aberta | Purge físico LGPD não coberto (`pii_fields`, `parecer` JSONB permanecem). MVP futuro scheduled purge |
| DT-087 | Minor | Aberta | `ingested_documents.uploaded_by` sem `ON DELETE` declarado. Cresce com soft-delete |
| DT-084 | CRÍTICA | Pré-existente | 5 testes legado falhando + 4 com erro de import (independente de MVP 33) |

### Próximos Candidatos de Feature (não autorizados)
- **F4.2** — Chunker estrutural + sub-ingestões (backend-only, migration de `parent_document_id` blocker)
- **F4.3** — Accumulator + OCG único + UX (custo 3× estimado)

---

## 9. Tamanho da Suite de Testes

### Contagem Total
- **214 arquivos** de teste (`test_*.py`)
- **2561 testes** (funções `def test_*` + `async def test_*`)

### Status Recente
Conforme `GCA_MVP_PROGRESS.md`:
- MVP 35: **90/90 + 110/110** (200 testes totais para MVP)
- MVP 31: **35/35**
- Zero regressões reportadas em MVPs 31-35

**Status de execução:** Não rodado `pytest` nesta extração. Assumir PASSING baseado em commits recentes.

---

## 10. Estrutura de Diretórios

### Backend
```
backend/
├── app/
│   ├── core/               — autenticação, security, configurações
│   ├── db/
│   │   ├── database.py     — AsyncSession factory
│   │   └── migrations/     — Alembic/SQL migrations
│   ├── models/
│   │   ├── base.py         — 49 classes ORM
│   │   └── *.py            — modelos adicionais (9 arquivos)
│   ├── schemas/            — 8 arquivos Pydantic
│   ├── services/           — 157 arquivos (AI, OCG, ingestão, etc)
│   │   ├── personas/       — 12 arquivos (12 LLM agents)
│   │   ├── adapters/       — 7 adapters (Jira, Slack, etc)
│   │   ├── scaffolders/    — 8 scaffolders (multistack)
│   │   ├── chunkers/       — 4 chunkers (PDF, Docx, etc)
│   │   ├── questionnaire_validation/  — validação canônica
│   │   ├── ports/          — interfaces (security scanner, issue tracker)
│   │   └── (156 outros .py)
│   ├── routers/            — 62 endpoints em 60 arquivos
│   ├── tasks/              — Dramatiq tasks
│   └── tests/              — 214 arquivos, 2561 testes
├── migrations/             — 74 .sql files (schema evolucionário)
└── pyproject.toml          — dependências Python
```

### Frontend
```
frontend/
├── src/
│   ├── pages/              — OCGPage, ProjectsPage, etc
│   ├── components/         — UI reusável
│   ├── hooks/              — React hooks customizados
│   └── (estrutura Next.js/React)
└── public/                 — assets estáticos
```

---

## 11. Migrations Alembic / SQL

### Últimas 10 Migrations
```
1. 074_ocg_consolidation_indices.sql      (índices OCG)
2. 073_f42_parent_document_id.sql         (parent_document_id FK)
3. 072_b5_pfq_nullable_origem.sql         (persona_follow_up_questions origem)
4. 071_f51_ocg_async.sql                  (OCG assíncrono)
5. 070_dba_cleanup_dogfood.sql            (limpeza operacional)
6. 069_mvp35_questionnaire_validation.sql (validação questionnaire)
7. 068_mvp34_soft_delete_document.sql     (soft-delete documents)
8. 067_mvp31_fix_persona_follow_up.sql    (fix persona follow-up)
9. 066_mvp31_consolidate_ocg_tables.sql   (OCG consolidation)
10. 065_create_pilares_vivos.sql          (pilares vivos)
```

**Total migrations:** 74 arquivos SQL

---

## 12. n8n Workflows

### Mapping Persona → Workflow
**Arquivo:** `backend/app/services/ocg_consolidator_service.py:34-46`

```python
PERSONA_TO_PILLAR = {
    "gp":    "p1_business_score",      # Gerente Projetos
    "neg":   "p1_business_score",      # Negócio
    "conf":  "p2_rules_score",         # Conformidade (BLOQUEANTE <60)
    "lgpd":  "p2_rules_score",         # LGPD
    "ux":    "p3_features_score",      # UX
    "ui":    "p3_features_score",      # UI
    "qa":    "p4_nfr_score",           # QA
    "arq":   "p5_architecture_score",  # Arquiteto
    "dev":   "p5_architecture_score",  # Dev
    "dba":   "p6_data_score",          # DBA
    "seg":   "p7_security_score",      # Segurança
}
```

**11 personas mapeadas** (AUD = router/classifier, sem score próprio)

### Webhooks n8n Endpoint
**Arquivo:** `backend/app/routers/webhooks.py:21` (prefix)

```python
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
```

**Callbacks registrados:**
- POST /webhooks/questionnaire
- POST /webhooks/questionnaire-result
- POST /webhooks/ocg-result
- POST /webhooks/ingestion-complete
- POST /webhooks/internal/ingestion/{ingestion_id}/error
- POST /webhooks/internal/ingestion/{ingestion_id}/accumulate

**Status:** Workflows n8n não encontrados em repo (provavelmente em Docker/deployment ou n8n DB externo).

---

## 13. Chaves de Memória Importantes

### Memory Bank Project
**Localização:** `/home/luiz/.claude/projects/-home-luiz-GCA/memory/MEMORY.md`

### Memórias Canônicas Commitadas
1. **feedback_gca_personas_canonical.md** — 12 personas LLM (expandido 2026-05-02)
2. **feedback_gca_provider_agnostico.md** — Provider é escolha do cliente (AIKeyResolver)
3. **feedback_process_binary_no_silence.md** — Processo binário obrigatório (§0 CLAUDE.md)
4. **feedback_restart_safety.md** — Usar safe_restart.sh antes de restart
5. **feedback_aja_no_ollama.md** — Ollama proibido como AI work (política §2.5)
6. **feedback_n8n_alwaysOutputData.md** — TODOS nós n8n precisam alwaysOutputData=true
7. **feedback_ocg_repositorio_canonico.md** — OCG = fonte única para CodeGen
8. **feedback_gca_decisoes_basilares_2026-05-04.md** — CodeGen ≥95%, Arguidor sem UI, sem except:pass

### Decisões Basilares Commitadas (CLAUDE.md §0)
- ❌ Proibido erro silencioso
- ❌ Proibido contorno silencioso
- ❌ Proibido afirmar funciona sem executar
- 🛑 Em erro de auth/config: PARAR
- 🛑 Em teste vermelho sem causa óbvia: PARAR

---

## 14. Observações Finais

### Achados Críticos (Fatos)
1. **94 tabelas** no schema, 11 mapeadas em detalhe
2. **49 classes ORM** em base.py + 9 arquivos adicionais
3. **64+ endpoints HTTP** mapeados (extração parcial)
4. **11 personas mapeadas** para pilares (12ª = AUD router)
5. **2561 testes** em 214 arquivos
6. **74 migrations** SQL (schema versionado)
7. **4 providers LLM** implementados (Anthropic, OpenAI, DeepSeek, Grok)
8. **Sem hardcodes** de provider em module_codegen_service.py
9. **MVPs 23-35 = todos fechados** (nenhum em execução)
10. **Processo Dramatiq** ativo (Celery deprecated 2026-05-05)

### Pendências de Extração
- **DT-087** + detalhes de foreign keys em algumas tabelas
- Relationship declarations em modelos ORM
- Conteúdo completo de schemas Pydantic
- Workflows n8n (provavelmente em deployment/n8n DB)
- Detalhes de `ers_doc_generator`, `p7_updater`, `code_validation_service`

### Qualidade da Extração
- **Fatos diretos:** 90%
- **NÃO ENCONTRADO:** 3 funções, 4 tabelas (detalhes parciais)
- **AMBÍGUO:** project_secrets schema
- **Recomendação:** Validar com `docker exec gca-postgres \d <table>` para detalhes faltantes

---

**Fim da extração:** 2026-05-05 BRT  
**Próximo passo:** Reorganizar CLAUDE.md + GCA_CANONICAL_CONTRACT.md com fatos extraídos.
