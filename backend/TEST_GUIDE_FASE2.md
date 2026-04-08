# FASE 2 Testing Guide

This guide explains how to run the FASE 2 integration tests to validate the admin project creation and tenant provisioning workflow.

---

## Prerequisites

1. **Database:** PostgreSQL running with GCA database initialized
   ```bash
   docker-compose up -d postgres
   ```

2. **Dependencies:** All Python packages installed
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment:** .env file configured with database credentials
   ```bash
   DATABASE_URL=postgresql+asyncpg://gca_user:gca_password@localhost:5432/gca_db
   ```

---

## Running Individual Test Suites

### FASE 1: Regression Tests (Basic Infrastructure)
Validates that core systems are functional.

```bash
cd /home/luiz/GCA/backend

# Run the regression test
python3 app/tests/test_regression_phase1.py
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════════╗
║         TESTE DE REGRESSÃO - FASE 1 GCA                       ║
╚════════════════════════════════════════════════════════════════╝

✅ Backend health check
✅ Database connection
✅ 7 Pillars seeded (P1-P7 with P7 blocking)
✅ ORM models import successfully
✅ Token encryption/decryption working
✅ Password hashing working
✅ Configuration settings loaded correctly
✅ OnboardingService initializes correctly
✅ Pillar criteria properly configured
✅ Async SQLAlchemy operations working
✅ Onboarding routes registered
✅ CORS configuration correct

======================================================================
RESULTADOS DOS TESTES
======================================================================

✅ Passou: 12/12
❌ Falhou: 0/12
📊 Taxa de sucesso: 100.0%

🎉 TODOS OS TESTES PASSARAM!

✨ FASE 1 APROVADA - PRONTO PARA FASE 2
```

---

### FASE 2: Integration Tests (Admin & Provisioning)
Validates complete admin project workflow with automatic tenant provisioning.

```bash
cd /home/luiz/GCA/backend

# Run the integration test
python3 app/tests/test_integration_admin_fase2.py
```

**Expected Output:**
```
╔════════════════════════════════════════════════════════════════╗
║      TESTE DE INTEGRAÇÃO - FASE 2 GCA (Admin & Provisioning) ║
╚════════════════════════════════════════════════════════════════╝

✅ Admin create project request
✅ Admin get pending projects
✅ Admin approve project
✅ Tenant schema created: proj_test-proj-fase2
✅ Tenant pillar configurations seeded
✅ Tenant initial OGC created
✅ Tenant tables created (all 5 tables present)
✅ Admin reject project

======================================================================
RESULTADOS DOS TESTES DE INTEGRAÇÃO - FASE 2
======================================================================

✅ Passou: 8/8
❌ Falhou: 0/8
📊 Taxa de sucesso: 100.0%

🎉 TODOS OS TESTES DE INTEGRAÇÃO PASSARAM!

✨ FASE 2 APROVADA - PRONTO PARA FASE 3 (Evaluation Engine)
```

---

## Running Both Test Suites (Complete Validation)

```bash
#!/bin/bash
cd /home/luiz/GCA/backend

echo "🚀 Starting FASE 1 Regression Tests..."
python3 app/tests/test_regression_phase1.py || exit 1

echo ""
echo "🚀 Starting FASE 2 Integration Tests..."
python3 app/tests/test_integration_admin_fase2.py || exit 1

echo ""
echo "✨ ALL TESTS PASSED! System is ready for FASE 3."
```

Save this as `run_all_tests.sh` and execute:
```bash
chmod +x run_all_tests.sh
./run_all_tests.sh
```

---

## Manual Testing via API

If you want to manually test the admin workflow using the REST API:

### 1. Start the Backend
```bash
cd /home/luiz/GCA/backend
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Create a Project Request
```bash
curl -X POST http://localhost:8000/api/v1/admin/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "project_name": "Test Project",
    "project_slug": "test-project",
    "description": "My test project"
  }'
```

**Response:**
```json
{
  "status": "pending",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "project_name": "Test Project",
  "project_slug": "test-project",
  "schema_name": "proj_test-project",
  "message": "Project request created. Waiting for admin approval.",
  "next_step": "admin_approval"
}
```

### 3. View Pending Projects
```bash
curl -X GET http://localhost:8000/api/v1/admin/projects/pending \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response:**
```json
{
  "pending_projects": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "gp_id": "admin_id",
      "project_name": "Test Project",
      "project_slug": "test-project",
      "requested_at": "2026-04-04T12:00:00+00:00"
    }
  ],
  "count": 1
}
```

### 4. Approve Project (Triggers Provisioning)
```bash
curl -X POST http://localhost:8000/api/v1/admin/projects/123e4567-e89b-12d3-a456-426614174000/approve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response:**
```json
{
  "status": "approved",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "project_slug": "test-project",
  "schema_name": "proj_test-project",
  "approved_at": "2026-04-04T12:00:05+00:00",
  "message": "Project approved and tenant provisioned",
  "next_step": "gp_onboarding",
  "gp_onboarding_url": "/projects/test-project/onboarding"
}
```

At this point:
- ✅ Schema `proj_test-project` created in PostgreSQL
- ✅ All tenant tables created
- ✅ 7 pillar configurations seeded
- ✅ Initial OGC v1 created

### 5. Verify Tenant Schema in PostgreSQL
```bash
# Connect to PostgreSQL
psql -U gca_user -d gca_db -h localhost

# List schemas
\dn

# You should see: proj_test-project

# List tables in tenant schema
\dt proj_test-project.*

# You should see:
# - pillar_configuration
# - ogc_versions
# - artifacts
# - artifact_evaluations
# - audit_log

# Query pillar configurations
SELECT pillar_code, pillar_name, weight FROM proj_test-project.pillar_configuration;

# Should return 7 rows (P1-P7)
```

### 6. Reject a Project
```bash
curl -X POST http://localhost:8000/api/v1/admin/projects/123e4567-e89b-12d3-a456-426614174000/reject \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "reason": "Does not meet business requirements"
  }'
```

---

## Troubleshooting

### Test Fails: "Project request not found"
**Cause:** Project ID is invalid or doesn't exist
**Solution:** Ensure you use the correct UUID from the create response

### Test Fails: "Schema already exists"
**Cause:** Previous test run created schema but wasn't cleaned up
**Solution:** Drop the schema manually:
```bash
psql -U gca_user -d gca_db -h localhost
DROP SCHEMA IF EXISTS proj_test_proj_fase2 CASCADE;
```

### Test Fails: "Permission denied for schema"
**Cause:** PostgreSQL user doesn't have CREATE SCHEMA privilege
**Solution:** Grant privileges:
```bash
psql -U postgres -d gca_db
GRANT CREATE ON DATABASE gca_db TO gca_user;
ALTER DEFAULT PRIVILEGES FOR USER postgres GRANT ALL ON SCHEMAS TO gca_user;
```

### Test Fails: "SMTP_ENABLED but credentials missing"
**Cause:** SMTP settings in .env are incomplete
**Solution:** Set SMTP_ENABLED=false in .env or provide all SMTP credentials

---

## Expected Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    ADMIN WORKFLOW                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Admin creates project request                           │
│     Status: PENDING                                         │
│                                                              │
│  2. Admin reviews pending projects                          │
│     Lists all PENDING requests                              │
│                                                              │
│  3. Admin approves project                                  │
│     ├─ Mark as APPROVED                                     │
│     ├─ Create PostgreSQL schema: proj_{slug}               │
│     ├─ Create all tenant tables                             │
│     ├─ Seed 7 pillar configurations                         │
│     ├─ Create initial OGC v1                                │
│     └─ Initialize OnboardingProgress                        │
│                                                              │
│  4. GP receives notification and begins onboarding          │
│     Next: Step 1 - Repository Setup                         │
│                                                              │
│  OR                                                          │
│                                                              │
│  3. Admin rejects project                                   │
│     Status: REJECTED                                        │
│     Reason stored for reference                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## What's Tested in FASE 2

✅ Admin creates project request with validation
✅ Admin can list all pending projects
✅ Admin approves and project is marked APPROVED
✅ PostgreSQL schema is created with correct name
✅ All tenant tables are created (5 tables)
✅ 7 pillar configurations are seeded
✅ Initial OGC v1 is created with correct metadata
✅ Admin rejects projects and stores reason

---

## Next Steps: FASE 3

After successful FASE 2 completion:

1. **Evaluation Engine:** Implement 7 Pilares scoring algorithm
2. **Piloter Integration:** Connect to Piloter API for stack recommendations
3. **Code Generation:** LLM integration for artifact generation
4. **Dashboard:** Admin and GP dashboards for monitoring

---

**FASE 2 validates that multi-tenant provisioning works correctly.
The system is ready for evaluation and code generation in FASE 3.**
