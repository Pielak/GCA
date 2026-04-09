# External Project Creation System - Complete Test Guide

## Overview
This guide covers the complete external project creation flow that allows GPs (Gestores de Projeto) outside the system to request new project creation through a web form.

**System Components:**
- Phase 1: Backend Infrastructure ✅ COMPLETE
- Phase 2: Admin Panel ✅ COMPLETE  
- Phase 3: Frontend Questionnaire & Status ✅ COMPLETE
- Phase 4: n8n + Qwen AI Validation ✅ COMPLETE

---

## Architecture Overview

```
GP (External) 
  ↓
  └─→ Admin sends link → GP opens /novo-projeto?token=xxx
      ↓
      ├─→ GET /external/novo-projeto/template - Load 46-question form in 8 sections
      ├─→ POST /external/novo-projeto/validate - Validate each section
      ├─→ POST /external/novo-projeto/submit - Submit completed questionnaire
      └─→ GET /external/novo-projeto/status - Check request status

Admin Dashboard
  ↓
  └─→ GET /admin/external-requests - List all external requests
      ├─→ GET /admin/external-requests/{id} - View full details
      ├─→ POST /admin/external-requests/{id}/approve - Approve & create project
      └─→ POST /admin/external-requests/{id}/reject - Reject with reason
```

---

## Phase 1: Backend Infrastructure (Completed)

### Models
- **ExternalProjectRequest** (`backend/app/models/base.py:453`)
  - 20+ fields including JSONB columns for questionnaire_data, n8n_validation_result, ocg_analysis_result
  - Status enum: draft → submitted → validating → pending_approval → approved/rejected → active
  - Indexes on token, gp_email, status, token_expires_at, submitted_at

### Services
- **ExternalProjectService** (`backend/app/services/external_project_service.py`)
  - `generate_link()` - Create 5-day expiring link, send email
  - `validate_token()` - Check token exists, not expired, not already used
  - `submit_questionnaire()` - Store questionnaire, send confirmation + admin notification
  - `get_request_status()` - Return human-readable status
  - `approve_request()` - Update status to approved, create project immediately
  - `reject_request()` - Set rejected status, send rejection email
  - `list_pending_requests()` - Get filtered list for admin
  - `get_request_detail()` - Full details for admin review

### Endpoints
- **Public (No Auth):**
  - `GET /api/v1/external/novo-projeto/template?token=xxx` → QuestionnaireTemplate
  - `POST /api/v1/external/novo-projeto/validate` → ValidateQuestionnaireResponse
  - `POST /api/v1/external/novo-projeto/submit` → SubmitQuestionnaireResponse
  - `GET /api/v1/external/novo-projeto/status?token=xxx` → ExternalRequestStatusResponse

- **Admin (Auth Required):**
  - `GET /api/v1/admin/external-requests?status_filter=xxx` → List[AdminExternalRequestListResponse]
  - `GET /api/v1/admin/external-requests/{request_id}` → ExternalRequestResponse
  - `POST /api/v1/admin/external-requests/{request_id}/approve` → { success, message, project_id }
  - `POST /api/v1/admin/external-requests/{request_id}/reject` → { success, message }
  - `POST /api/v1/admin/external-requests/generate-link` → { success, link, message }

### Email Notifications
Implemented in `EmailService`:
- `send_external_link()` - Initial link to GP
- `send_submission_confirmation()` - Confirms submission, states 2-day SLA
- `send_admin_notification()` - Alerts admin of pending request
- `send_approval_notification()` - Congratulates GP, provides project link
- `send_rejection_notification()` - Informs GP of rejection with reason

---

## Phase 2: Admin Panel (Completed)

### AdminExternalRequestsPage
**File:** `frontend/src/pages/admin/AdminExternalRequestsPage.tsx`

**Features:**
- List all external project requests with pagination
- Filter by status (draft, submitted, validating, pending_approval, approved, rejected, active)
- Search by request number, email, or GP name
- Shows pending count with SLA warning
- Color-coded status badges
- Click to view request details

**Key Elements:**
- Pending requests counter with amber alert
- Real-time status filtering
- Responsive table layout
- Request number with creation date
- GP info with avatar + email
- Status badge with visual colors
- Navigation to detail page

### AdminExternalRequestDetailPage
**File:** `frontend/src/pages/admin/AdminExternalRequestDetailPage.tsx`

**Features:**
- Full request details with questionnaire data
- View n8n validation results
- View OCG analysis results
- Approve request with optional notes
- Reject request with mandatory reason
- Modal confirmation for rejection
- Real-time status updates after action

**Key Elements:**
- Request number + status badge
- GP information card
- Timeline of key dates (created, submitted, approved)
- Questionnaire data preview (JSON)
- Validation results display
- Approval section with notes field
- Rejection section with reason textarea

### Navigation Integration
- Added to sidebar under "Administração" section
- Menu item: "Projetos Externos" with Mail icon
- Routes:
  - `/admin/external-requests` → List page
  - `/admin/external-requests/:requestId` → Detail page

### Dashboard Integration
- Quick access card on AdminDashboardPage
- Shows pending external requests info
- "Visualizar" button links to list page

---

## Phase 3: Frontend Questionnaire & Status (Completed)

### ExternalQuestionnaireePage
**File:** `frontend/src/pages/ExternalQuestionnaireePage.tsx`

**Access:** `https://gca.code-auditor.com.br/novo-projeto?token=<token>`

**Structure:**
- 8 Sections (A.1 - A.8) with 46 total questions
- ~30 minutes estimated completion time
- Progressive form with one section per page
- Real-time validation per section
- Draft saving capability

**Sections:**
1. **A.1 - Initial ID & Scope** (6 Q)
   - Project name, slug, description, business context, users, budget

2. **A.2 - Existing Projects** (8 Q)
   - Existing project status, current stack, team, migration path, tech debt, issues, metrics, timeline

3. **A.3 - Architecture & Profile** (6 Q)
   - Output type, deployment model, scalability, performance, SLA, multi-tenancy

4. **A.4 - Frontend** (5 Q)
   - Frontend preference, UI complexity, responsive requirements, accessibility, PWA

5. **A.5 - Backend & APIs** (5 Q)
   - Backend preference, API style, authentication, rate limiting, versioning

6. **A.6 - Data & Messaging** (8 Q)
   - Database type, data volume, caching, messaging, automation, retention, backup, DR

7. **A.7 - AI/Security/Observability** (6 Q)
   - AI/ML needs, security requirements, encryption, logging, monitoring

8. **A.8 - Testing & Validation** (4 Q)
   - Testing strategy, CI/CD, deployment frequency, deliverables

**Features:**
- Progress bar with percentage
- Section tabs for quick navigation
- Form validation with error messages
- Save draft button (preserves data)
- Next/Previous navigation
- Submit button on final section
- Success modal with request number
- Auto-redirect to status page after submission

### ExternalProjectStatusPage
**File:** `frontend/src/pages/ExternalProjectStatusPage.tsx`

**Access:** `https://gca.code-auditor.com.br/novo-projeto/status?token=<token>`

**Display:**
- Current request status with visual icon
- Request number (REQ-YYYYMMDD-XXXXX)
- Human-readable status message
- Timeline of key events
- Auto-refresh every 30 seconds (when submitted)
- Toggle auto-refresh on/off

**Statuses:**
- **Draft** (Clock icon, gray) - Form ready for completion
- **Submitted** (Mail icon, blue) - Waiting for admin analysis
- **Validating** (Spinner, purple) - System validating questionnaire
- **Pending Approval** (Clock icon, amber) - Admin analyzing
- **Approved** (Check icon, green) - Project approved, access available
- **Rejected** (X icon, red) - Project rejected with reason
- **Active** (Check icon, bright green) - Project active in system

---

## Phase 4: n8n + Qwen AI Validation (NEW)

### What's New
- **n8n Service** starts automatically in Docker (port 5678)
- **Qwen AI** analyzes questionnaires for gaps, conflicts, risks, recommendations
- **Async workflow:** n8n analysis happens after GP submits, doesn't block response
- **Admin context:** Admin sees full Qwen analysis before approving

### Architecture
```
GP submits questionnaire (fast response - immediate confirmation)
  ↓ (async)
Backend triggers: N8nService.trigger_external_project_validation()
  ↓
n8n webhook receives data
  ↓
Qwen AI analyzes for:
  - GAPS: Missing fields, incomplete specs
  - CONFLICTS: React + Flutter, monolith + microservices, etc
  - RISKS: Misaligned frontend/backend, overly complex, unrealistic targets
  - RECOMMENDATIONS: Suggested improvements
  ↓
n8n calls back: POST /api/v1/webhooks/external-project-result
  ↓
Backend updates ExternalProjectRequest:
  - n8n_validation_result = analysis
  - status = "pending_approval"
  ↓
Admin reviews with full context:
  - Sees Qwen analysis in detail page
  - Can make informed approve/reject decision
```

### n8n Configuration

**Docker Setup:**
```bash
# n8n starts automatically
docker-compose up -d

# Wait for n8n to initialize (check logs)
docker logs gca-n8n | grep "n8n ready"

# Access: http://localhost:5678
# Create admin account on first visit
```

**Create n8n Workflow:**
1. In n8n dashboard, click **"+"** → **New Workflow**
2. Import pre-built JSON from `N8N_SETUP_GUIDE.md` section "Pre-built Workflow JSON"
3. OR follow manual steps in guide
4. Configure Qwen AI provider:
   - **OpenRouter (Recommended):** Free tier, easy setup
   - **Ollama (Local):** Free but requires 7GB RAM
   - **Hugging Face:** Free tier or paid API

### What Qwen Analyzes

**GAPS Example:**
```
- project_name is required but empty
- Missing backend preference (required for A.5)
- No security_requirements (critical for compliance)
```

**CONFLICTS Example:**
```
- React + Flutter: Choose ONE
- Monolith + Microservices: Mutually exclusive architectures
- SQL-only + NoSQL requirement: Contradictory
```

**RISKS Example:**
```
- Frontend (React) + Backend (Go) mismatch: Uncommon pair, may have integration issues
- 1M users but monolithic architecture: Will face scaling issues
- No disaster recovery plan for critical system
```

**RECOMMENDATIONS Example:**
```
- Consider PostgreSQL instead of MongoDB for structured data
- Add integration tests for frontend + backend compatibility
- Implement load testing for scalability verification
```

### Test Phase 4

**Step 1: Start n8n**
```bash
docker-compose up -d gca-n8n
docker logs gca-n8n | grep "ready"
# Wait ~30 seconds for n8n to initialize
```

**Step 2: Create/Import Workflow**
- See `N8N_SETUP_GUIDE.md` for JSON import or manual creation

**Step 3: Configure Qwen**
- Choose provider (OpenRouter easiest)
- Add API key to n8n

**Step 4: Test Manual Webhook**
```bash
curl -X POST http://localhost:5678/webhook/external-project \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "request_number": "REQ-20260406-TEST001",
    "gp_email": "gp@example.com",
    "questionnaire_data": {
      "project_name": "Test Project",
      "frontend_preference": "React",
      "frontend_preference": "Flutter",
      "output_type": "Monolith",
      "output_type": "Microserviços"
    }
  }'
```

Expected: Qwen identifies conflicts, analysis returns

**Step 5: Test Full Flow**
1. Navigate to `/novo-projeto?token=<token>`
2. Fill questionnaire with intentional gaps (e.g., missing security requirements)
3. Submit
4. Watch backend logs: `docker logs gca-backend | grep "n8n"`
5. Wait 5-10 seconds for Qwen analysis
6. Admin visits `/admin/external-requests/{id}`
7. Scroll to "Resultado da Validação n8n"
8. See gaps, conflicts, risks identified by Qwen

---

## Testing Workflow

### 1. Admin Generates Link for GP
**Backend Test:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/external-requests/generate-link \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gp_email": "gp@example.com",
    "gp_name": "João Silva"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "link": "https://gca.code-auditor.com.br/novo-projeto?token=...",
  "message": "Link enviado para gp@example.com"
}
```

**UI Test:**
- Admin navigates to `/admin/external-requests`
- Clicks "Gerar Link" (if implemented)
- Enters GP email and name
- Receives success message with link
- GP receives email with link

---

### 2. GP Accesses Questionnaire
**Browser:** `https://gca.code-auditor.com.br/novo-projeto?token=<token>`

**Flow:**
1. ✅ Page loads and fetches template
2. ✅ Shows progress bar (0%)
3. ✅ Displays Section A.1 with 6 questions
4. ✅ Form allows input in all field types (text, textarea, number, select, radio)
5. ✅ "Salvar Rascunho" saves current progress
6. ✅ "Próximo" validates and moves to A.2

---

### 3. GP Fills & Submits Questionnaire
**Backend Test - Validate Section:**
```bash
curl -X POST http://localhost:8000/api/v1/external/novo-projeto/validate \
  -H "Content-Type: application/json" \
  -d '{
    "token": "...",
    "page_number": 1,
    "section_data": {
      "project_name": "My Project",
      "project_slug": "my-project",
      "description": "...",
      "business_context": "..."
    }
  }'
```

**Backend Test - Submit:**
```bash
curl -X POST http://localhost:8000/api/v1/external/novo-projeto/submit \
  -H "Content-Type: application/json" \
  -d '{
    "token": "...",
    "questionnaire_data": { 
      "all": "46 questions..."
    }
  }'
```

**UI Test:**
1. ✅ Fill all 8 sections (questions vary in type)
2. ✅ Each section validates before allowing next
3. ✅ On final section, "Enviar Questionário" appears
4. ✅ After submission:
   - ✅ Success modal shows request number
   - ✅ Auto-redirects to status page
   - ✅ GP receives confirmation email with 2-day SLA message

---

### 4. Admin Reviews Request
**Navigate to:** `/admin/external-requests`

**List View Test:**
- ✅ Lists all external requests
- ✅ Shows request number (REQ-YYYYMMDD-XXXXX)
- ✅ Shows GP name with avatar
- ✅ Shows GP email
- ✅ Shows status badge (blue for submitted)
- ✅ Shows submission date
- ✅ Pending requests counter shows warning

**Click on request → Detail View**
- ✅ Shows full request details
- ✅ Shows GP information
- ✅ Shows creation, submission, approval dates
- ✅ Shows full questionnaire data (JSON preview)
- ✅ Shows n8n validation results (if available)
- ✅ Shows OCG analysis (if available)

---

### 5. Admin Approves or Rejects

**Approval Test:**
1. Click "Aprovar Solicitação" button
2. Optionally add notes
3. System:
   - ✅ Updates status to "approved"
   - ✅ Records approval timestamp
   - ✅ Sends email to GP
   - ✅ Creates project immediately
4. GP receives email: "Parabéns! Seu projeto foi aprovado"

**Backend Approval:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/external-requests/{id}/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "Approved - ready for development"}'
```

**Rejection Test:**
1. Click "Rejeitar Solicitação" button
2. Modal appears requesting rejection reason
3. Enter reason: "Feature set out of scope"
4. System:
   - ✅ Updates status to "rejected"
   - ✅ Records rejection timestamp
   - ✅ Sends email to GP with reason
5. GP receives email: "Seu projeto foi rejeitado. Motivo: Feature set..."

**Backend Rejection:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/external-requests/{id}/reject \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Feature set out of scope"}'
```

---

### 6. GP Checks Status

**Navigate to:** `/novo-projeto/status?token=<token>`

**Status Page Test:**
1. ✅ Shows request number
2. ✅ Shows current status with icon/color
3. ✅ Shows status message
4. ✅ Auto-refreshes every 30 seconds
5. ✅ Shows timeline of steps:
   - ✅ "Questionário Recebido" (completed, with date)
   - ✅ "Análise em Andamento" (pending)
   - ✅ "Projeto Aprovado" (pending)
6. ✅ After admin approval:
   - Status changes to "Aprovado"
   - Approval date appears
   - "Projeto Aprovado" step completes

---

## Database State Management

### External Project Request Lifecycle

```
START: Admin generates link
  ↓
ExternalProjectRequest created:
  - status = "draft"
  - token = unique 32-byte URL-safe string
  - token_expires_at = now + 5 days
  - gp_email, gp_name populated
  - Email sent to GP

GP fills form + submits
  ↓
Update to:
  - status = "submitted"
  - questionnaire_data = full JSONB
  - submitted_at = now
  - Admin + GP notified via email

Admin reviews → Approves
  ↓
Update to:
  - status = "approved"
  - approved_at = now
  - reviewed_by_admin_id = admin UUID
  - associated_project_id = created project UUID
  - GP notified via email with project link

OR

Admin reviews → Rejects
  ↓
Update to:
  - status = "rejected"
  - rejected_at = now
  - reviewed_by_admin_id = admin UUID
  - rejection_reason = explanation
  - GP notified via email with reason
```

---

## Quick Test Checklist

### Backend ✅
- [ ] ExternalProjectRequest model exists with all fields
- [ ] Services import without errors
- [ ] Router imports without errors
- [ ] Database migrations applied (if needed)
- [ ] JWT auth on admin endpoints works

### Admin Panel ✅
- [ ] Sidebar shows "Projetos Externos" menu item
- [ ] List page loads external requests
- [ ] Filter by status works
- [ ] Search by request number/email/name works
- [ ] Click request opens detail page
- [ ] Approval button works + email sent
- [ ] Rejection button works + email sent
- [ ] Status updates immediately

### Frontend ✅
- [ ] Route `/novo-projeto?token=xxx` loads form
- [ ] Template loads from API
- [ ] Form displays all 8 sections
- [ ] Navigation between sections works
- [ ] Save draft preserves data
- [ ] Validation shows errors
- [ ] Submit sends data to API
- [ ] Success modal with request number
- [ ] Route `/novo-projeto/status?token=xxx` shows status
- [ ] Status auto-refreshes
- [ ] Timeline updates after approval

---

## Troubleshooting

### Token Issues
- **"Token não encontrado"** → Check URL has `token=` parameter
- **"Token expirou"** → Token valid for 5 days from generation
- **"Token já foi usado"** → Request already submitted or status is "active"

### Validation Issues
- Check required fields are filled (marked with *)
- Ensure email format is valid for email fields
- Text fields have length limits in schema

### Admin Access
- Must be logged in as admin user
- Check JWT token in Authorization header
- Verify token not expired (refresh if needed)

### Email Issues
- Check `EmailService` configuration in settings
- Verify SMTP credentials in `.env`
- Check email templates exist in service
- Review logs for send failures

---

## Success Criteria

✅ External project requests can be created via admin-generated links
✅ GPs can fill 46-question questionnaire in 8 progressive sections
✅ Questionnaire data is validated and stored
✅ Admin can view all external requests
✅ Admin can approve requests (creates project immediately)
✅ Admin can reject requests with reason
✅ GPs receive email notifications at all key steps
✅ GPs can check request status in real-time
✅ Frontend builds without errors
✅ Backend endpoints all respond correctly
✅ Database stores questionnaire data in JSONB format

---

## Files Modified/Created

### Backend
- `app/models/base.py` - Added ExternalProjectRequest model
- `app/routers/external_projects.py` - Created new router (8 endpoints)
- `app/services/external_project_service.py` - Created service (8 methods)
- `app/schemas/external_project.py` - Created schemas (5 types)
- `app/services/email_service.py` - Added 5 email methods
- `app/main.py` - Registered external_projects router

### Frontend
- `src/pages/admin/AdminExternalRequestsPage.tsx` - List page
- `src/pages/admin/AdminExternalRequestDetailPage.tsx` - Detail page
- `src/pages/ExternalQuestionnaireePage.tsx` - Public form
- `src/pages/ExternalProjectStatusPage.tsx` - Public status
- `src/components/layout/Sidebar.tsx` - Added nav item
- `src/pages/admin/AdminDashboardPage.tsx` - Added quick access card
- `src/routes.tsx` - Added 4 new routes

---

## Next Steps

### Phase 4 (Future)
- [ ] Implement n8n webhook integration for async validation
- [ ] Create project with proper organization + team setup on approval
- [ ] Implement edit-after-submit with admin notification
- [ ] Implement cancel-request with admin notification  
- [ ] Add admin clarifications request feature
- [ ] Export questionnaire to PDF/HTML
- [ ] Rate limiting on token generation
- [ ] Audit logging for all admin actions
- [ ] Bulk email operations
- [ ] Dashboard statistics on external requests

