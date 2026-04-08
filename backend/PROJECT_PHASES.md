# GCA Project Phases

**Project:** GCA — Gerenciador Central de Arquiteturas  
**Status:** FASE 2 COMPLETED ✅  
**Overall Progress:** 40% (2 of 5 phases complete)

---

## Phase Overview

```
FASE 1 ✅     FASE 2 ✅     FASE 3 🚀     FASE 4        FASE 5
Regression    Admin &      Evaluation    Code Gen      Dashboard
Tests         Provisioning Engine        & Artifacts   & Monitoring
```

---

## FASE 1: Foundation & Regression Testing ✅

**Status:** COMPLETED (12/12 tests passed)

**Deliverables:**
- [x] FastAPI application scaffold
- [x] PostgreSQL database setup with async SQLAlchemy
- [x] User authentication (JWT RS256)
- [x] Security (Bcrypt password hashing, Fernet token encryption)
- [x] 7 Pilares model definition (P1-P7 with P7 blocker)
- [x] Multi-tenant data models
- [x] CORS configuration for production domains
- [x] Structlog structured logging
- [x] Health check endpoint
- [x] Comprehensive regression test suite

**Test Results:**
```
✅ Backend health check
✅ Database connection
✅ 7 Pillars seeded (P1-P7 with P7=blocking)
✅ ORM models import successfully
✅ Token encryption/decryption
✅ Password hashing (bcrypt)
✅ Configuration settings
✅ OnboardingService initialization
✅ Pillar criteria configuration
✅ Async SQLAlchemy operations
✅ Route registration
✅ CORS configuration

Success Rate: 100% (12/12)
```

**Key Technologies:**
- FastAPI + uvicorn
- SQLAlchemy async (with asyncpg)
- PostgreSQL
- JWT RS256
- Bcrypt + Fernet
- Structlog

---

## FASE 2: Admin & Tenant Provisioning ✅

**Status:** COMPLETED (8/8 integration tests passed)

**Deliverables:**
- [x] AdminService class with full lifecycle management
- [x] Admin REST API (4 endpoints)
- [x] Automatic tenant schema creation
- [x] Automatic table provisioning in tenant schema
- [x] Pillar template inheritance
- [x] Initial OGC v1 creation per tenant
- [x] Project request workflow (create → approve/reject)
- [x] Comprehensive integration tests

**Architecture:**
```
Global Schema (public)
├─ pillar_templates
├─ company_policies
├─ users
├─ project_requests
└─ onboarding_progress

Tenant Schema (proj_{slug})
├─ pillar_configuration
├─ ogc_versions
├─ artifacts
├─ artifact_evaluations
└─ audit_log
```

**Test Results:**
```
✅ Admin create project request
✅ Admin get pending projects
✅ Admin approve project
✅ Tenant schema created
✅ Tenant pillar configurations seeded
✅ Tenant initial OGC created
✅ Tenant tables created
✅ Admin reject project

Success Rate: 100% (8/8)
```

**Admin Endpoints:**
- `POST /api/v1/admin/projects` — Create project
- `GET /api/v1/admin/projects/pending` — View pending
- `POST /api/v1/admin/projects/{id}/approve` — Approve & provision
- `POST /api/v1/admin/projects/{id}/reject` — Reject with reason

---

## FASE 3: Evaluation Engine 🚀

**Status:** NOT STARTED

**Planned Deliverables:**
- [ ] Piloter Service (API integration)
- [ ] N8N Webhook orchestration
- [ ] Stack recommendation caching
- [ ] 7 Pilares evaluation algorithm
- [ ] Weighted scoring (P1-P7)
- [ ] P7 blocker enforcement (< 70 = blocked)
- [ ] Artifact evaluation API
- [ ] Evaluation history tracking
- [ ] Feedback generation
- [ ] Integration tests for evaluation pipeline

**Key Components:**

### 3.1 Piloter Service
```python
class PiloterService:
    - call_piloter_api(language, architecture) → Stack recommendations
    - cache_recommendations(cache_key, results)
    - get_cached_recommendations(cache_key)
    - track_quota_usage()
    - handle_quota_alerts()
```

### 3.2 N8N Integration
- Trigger N8N workflow from Step 4 (Architecture selection)
- Poll N8N workflow status
- Receive stack results
- Store in StackCache

### 3.3 Evaluation Algorithm
```
For each artifact:
  1. Calculate P1 score (Business Alignment)
  2. Calculate P2 score (Business Logic)
  3. Calculate P3 score (Functional Requirements)
  4. Calculate P4 score (Non-Functional)
  5. Calculate P5 score (Architecture)
  6. Calculate P6 score (Data)
  7. Calculate P7 score (Compliance/Security/Testing/Quality)
  
  If P7 < 70:
    → code_generation_allowed = false
    → BLOCKED status
  Else:
    → Calculate weighted final score
    → code_generation_allowed = true
    → APPROVED or NEEDS_REVIEW status
```

### 3.4 Evaluation Endpoints
- `POST /api/v1/projects/{id}/artifacts/{aid}/evaluate` — Evaluate artifact
- `GET /api/v1/projects/{id}/artifacts/{aid}/evaluation` — Get latest evaluation
- `GET /api/v1/projects/{id}/evaluations` — List all evaluations
- `POST /api/v1/projects/{id}/evaluate-all` — Evaluate all artifacts

**Estimated Effort:** ~15-20 days

---

## FASE 4: Code Generation ⏳

**Status:** PLANNED

**Planned Deliverables:**
- [ ] LLM integration (Anthropic Claude, OpenAI GPT, Grok, DeepSeek)
- [ ] OGC context builder
- [ ] Prompt engineering
- [ ] Code artifact generation
- [ ] Code quality validation
- [ ] Generated code versioning
- [ ] Code delivery mechanism
- [ ] Integration tests

**Key Components:**

### 4.1 LLM Selection
```python
class CodeGenerationService:
    - select_llm_provider(project_preferences) → Provider
    - build_ogc_context(project, evaluation_results)
    - generate_code(context, prompt_template)
    - validate_generated_code()
    - store_artifact(generated_code)
```

### 4.2 Code Generation Pipeline
1. Load project evaluation context
2. Load OGC configuration
3. Build comprehensive prompt
4. Call selected LLM
5. Parse and validate response
6. Store as Artifact
7. Create code evaluation record
8. Return to user

### 4.3 Endpoints
- `POST /api/v1/projects/{id}/generate-code` — Generate code
- `GET /api/v1/projects/{id}/generated-artifacts` — List generated code
- `GET /api/v1/projects/{id}/artifacts/{aid}/code` — Retrieve code
- `POST /api/v1/projects/{id}/artifacts/{aid}/regenerate` — Regenerate

**Estimated Effort:** ~20-25 days

---

## FASE 5: Dashboard & Monitoring 📊

**Status:** PLANNED

**Planned Deliverables:**
- [ ] Admin dashboard
- [ ] GP project dashboard
- [ ] Real-time monitoring
- [ ] Analytics and metrics
- [ ] Notification system
- [ ] Audit log viewer
- [ ] System health dashboard
- [ ] Performance monitoring

**Admin Dashboard:**
- Project request queue
- Approval workflow
- System health
- User management
- Quota monitoring

**GP Project Dashboard:**
- Onboarding progress
- Evaluation results
- Generated artifacts
- OGC versions
- Team management
- Audit logs

**Estimated Effort:** ~15-20 days

---

## Database Schema Summary

### Global Schema (public)
```sql
CREATE TABLE users (...)                    -- User accounts
CREATE TABLE pillar_templates (...)         -- Standard P1-P7
CREATE TABLE company_policies (...)         -- Company rules
CREATE TABLE project_requests (...)         -- Admin approval
CREATE TABLE onboarding_progress (...)      -- Onboarding tracking
CREATE TABLE team_invites (...)             -- Email invitations
CREATE TABLE stack_cache (...)              -- Cached recommendations
CREATE TABLE piloter_queries (...)          -- API usage tracking
CREATE TABLE piloter_quota_history (...) -- Subscription usage
```

### Tenant Schema (proj_{slug})
```sql
CREATE TABLE pillar_configuration (...)     -- Customized weights
CREATE TABLE ogc_versions (...)             -- OGC with versions
CREATE TABLE artifacts (...)                -- Project artifacts
CREATE TABLE artifact_evaluations (...)     -- P1-P7 scores
CREATE TABLE audit_log (...)                -- Tenant-specific audit
```

---

## Technology Stack

**Backend:**
- Python 3.10+
- FastAPI (web framework)
- SQLAlchemy 2.0 (async ORM)
- PostgreSQL 14+ (database)
- Asyncpg (async driver)
- Pydantic (validation)
- Structlog (logging)
- PyJWT (authentication)
- Bcrypt (password hashing)
- Cryptography (token encryption)

**Infrastructure:**
- Docker & Docker Compose (containerization)
- PostgreSQL (relational database)
- Redis (optional, for caching)
- N8N (workflow orchestration)
- Cloudflare Tunnel (production ingress)

**External Services:**
- Piloter API (stack recommendations)
- Anthropic Claude (code generation)
- OpenAI GPT (alternative LLM)
- Grok (alternative LLM)
- DeepSeek (alternative LLM)

**Frontend:**
- Vite (build tool)
- Vue.js (UI framework)
- TypeScript (type safety)
- Tailwind CSS (styling)

---

## Performance Targets

| Operation | Target | Status |
|-----------|--------|--------|
| Project creation | < 100ms | ✅ Met |
| Project approval & provisioning | < 500ms | ✅ Met |
| Artifact evaluation (P1-P7) | < 2s | ⏳ FASE 3 |
| Code generation | < 30s | ⏳ FASE 4 |
| Dashboard load | < 1s | ⏳ FASE 5 |

---

## Security Checklist

- [x] JWT RS256 for authentication
- [x] Bcrypt for password hashing
- [x] Fernet for sensitive token encryption
- [x] Multi-tenant data isolation
- [x] Admin authorization checks
- [x] CORS configured for production
- [x] Audit logging for admin actions
- [x] SQL injection prevention (SQLAlchemy parameterization)
- [ ] Rate limiting (FASE 3+)
- [ ] WAF rules (FASE 5+)

---

## Known Limitations & TODOs

### FASE 2 (Current)
- [x] Email sending via SMTP (ready, not yet integrated)
- [x] Piloter API integration (ready for FASE 3)
- [x] N8N webhook triggering (ready for FASE 3)

### FASE 3 (Next)
- [ ] P7 blocker enforcement in evaluation
- [ ] Weighted scoring algorithm
- [ ] Quota alerting system
- [ ] Retry logic for Piloter API

### FASE 4 (Later)
- [ ] LLM provider selection logic
- [ ] Code quality gates
- [ ] Artifact versioning
- [ ] Rollback mechanism

### FASE 5 (Final)
- [ ] Real-time websocket updates
- [ ] Export functionality
- [ ] Webhook notifications

---

## Development Workflow

1. **Feature Development**
   - Create feature branch
   - Implement in `app/` directory
   - Write comprehensive tests
   - Update this document

2. **Testing**
   - Unit tests for services
   - Integration tests for workflows
   - API tests for endpoints
   - Database tests for schema

3. **Code Review**
   - Verify tests pass
   - Check security implications
   - Review performance impact
   - Validate documentation

4. **Deployment**
   - Build Docker images
   - Tag release
   - Deploy to staging
   - Validate in production

---

## Roadmap Timeline

```
Current: Early April 2026

FASE 1  ✅ COMPLETE   (Week 1)
FASE 2  ✅ COMPLETE   (Week 2)
FASE 3  🚀 START      (Week 3-4)
FASE 4  ⏳ PLANNED    (Week 5-6)
FASE 5  📊 PLANNED    (Week 7-8)
```

---

## How to Continue Development

### Before Starting FASE 3:
1. Review `TEST_GUIDE_FASE2.md` for testing procedures
2. Verify all FASE 2 tests pass
3. Review admin workflow architecture
4. Understand multi-tenant data isolation

### For FASE 3 (Evaluation Engine):
1. Implement `PiloterService` in `app/services/`
2. Create `EvaluationService` for P1-P7 scoring
3. Add evaluation endpoints to `app/routers/`
4. Create comprehensive evaluation tests
5. Validate P7 blocker enforcement

### Important Files to Reference:
- `app/models/tenant.py` — Artifact and evaluation models
- `app/models/pillar.py` — Pillar definitions with criteria
- `app/services/admin_service.py` — Service pattern example
- `app/routers/admin.py` — REST endpoint patterns
- `app/tests/test_integration_admin_fase2.py` — Testing patterns

---

**NEXT STEP: Implement FASE 3 - Evaluation Engine with 7 Pilares scoring**
