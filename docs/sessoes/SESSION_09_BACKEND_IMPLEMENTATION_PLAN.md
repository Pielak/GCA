# Session 09 — Backend Implementation Plan

**Data**: 05/04/2026  
**Fase**: Backend Services + Endpoints Planning

---

## 📊 SUMMARY OF CHANGES

### Database Schema Changes (COMPLETED ✅)

**File**: `/home/luiz/GCA/backend/app/models/base.py`

#### 1. User Model — Added 2 Fields

```python
first_access_completed = Column(Boolean, default=False, index=True)
password_changed_at = Column(DateTime(timezone=True), nullable=True)
```

#### 2. New Model: ResetToken

```python
class ResetToken(Base):
    __tablename__ = "reset_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, default=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
```

**Note**: ProjectMember model already has `invite_token` + `invite_expires_at` + `accepted_at` fields, so no changes needed there.

---

## 🔧 BACKEND ENDPOINTS TO IMPLEMENT

### Group 1: Authentication & Password Management

#### 1.1 POST `/api/v1/auth/reset-password` (Request Reset)

**Purpose**: User requests password reset (forgot password flow)

**Request**:
```json
{
  "email": "user@example.com"
}
```

**Response** (200 OK):
```json
{
  "message": "Se o email existe no sistema, um link de recuperação foi enviado",
  "security_note": "Por segurança, não confirmamos se o email existe"
}
```

**Behavior**:
- [ ] Accept email only
- [ ] Check if user exists (silently skip if not, for security)
- [ ] If exists:
  - Generate secure token (random 32 chars)
  - Create ResetToken entry with TTL = 1 hour
  - Mark token as unused (used = false)
  - Send email with link: `/reset-password?token={token}`
  - Log to GlobalAuditLog (event_type: "password_reset_requested")
- [ ] Always return 200 OK (even if email doesn't exist)
- [ ] Rate limit: Max 5 requests per email per hour

#### 1.2 POST `/api/v1/auth/verify-reset-token` (Verify Token)

**Purpose**: Verify reset token is valid before user submits new password

**Request**:
```json
{
  "token": "xyz123..."
}
```

**Response** (200 OK):
```json
{
  "valid": true,
  "message": "Token válido, proceda com a alteração de senha"
}
```

**Response** (400 Bad Request):
```json
{
  "valid": false,
  "message": "Token expirado ou já utilizado"
}
```

**Behavior**:
- [ ] Accept token string
- [ ] Look up in ResetToken table
- [ ] Check: expires_at > now AND used == false
- [ ] If invalid: return 400 with message
- [ ] If valid: return 200 with valid=true

#### 1.3 POST `/api/v1/auth/reset-password-confirm` (Confirm Reset)

**Purpose**: User submits new password with reset token

**Request**:
```json
{
  "token": "xyz123...",
  "new_password": "SecurePass123!@#"
}
```

**Response** (200 OK):
```json
{
  "message": "Senha alterada com sucesso. Faça login com a nova senha"
}
```

**Behavior**:
- [ ] Accept token + new password
- [ ] Verify token validity (same as endpoint 1.2)
- [ ] Validate password strength (min 12 chars, uppercase, number, special)
- [ ] Hash new password with bcrypt
- [ ] Update user.password_hash
- [ ] Update user.password_changed_at = now
- [ ] Mark token as used (used = true, used_at = now)
- [ ] Log to GlobalAuditLog (event_type: "password_reset_completed")
- [ ] Send confirmation email
- [ ] Return 200 OK

#### 1.4 POST `/api/v1/auth/change-first-password` (Mandatory First Change)

**Purpose**: User must change temporary password on first login

**Request** (requires access token):
```json
{
  "temporary_password": "TmpPwd123!@#",
  "new_password": "MySecurePass123!@#"
}
```

**Response** (200 OK):
```json
{
  "message": "Senha alterada com sucesso. Bem-vindo ao GCA!",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "User Name",
    "first_access_completed": true
  }
}
```

**Behavior**:
- [ ] Require valid access token
- [ ] Get current_user_id from token
- [ ] Verify temporary_password matches user.password_hash
- [ ] Validate new_password strength
- [ ] Hash new password with bcrypt
- [ ] Update user:
  - password_hash = hash(new_password)
  - password_changed_at = now
  - first_access_completed = true
- [ ] Log to GlobalAuditLog (event_type: "first_password_changed")
- [ ] Return 200 OK with user data
- [ ] Return 400 if temporary password doesn't match
- [ ] Return 400 if new password invalid

---

### Group 2: Project Team Management

#### 2.1 POST `/api/v1/projects/{project_id}/invite` (GP Invites Team Member)

**Purpose**: GP invites user to join project with specific role

**Request** (requires valid access token):
```json
{
  "email": "dev@example.com",
  "role": "dev_senior"  // dev_senior, dev_pleno, tech_lead, qa, compliance
}
```

**Response** (201 Created):
```json
{
  "invite_id": "uuid",
  "email": "dev@example.com",
  "role": "dev_senior",
  "status": "pending",
  "expires_at": "2026-04-12T23:00:00Z",
  "invite_url": "https://gca.com/accept-invite?token=xyz123"
}
```

**Behavior**:
- [ ] Require valid access token
- [ ] Get current_user_id (GP making invite)
- [ ] Verify current user is GP of the project
- [ ] Check if user exists by email:
  - If exists: use existing user_id
  - If not exists: create new user with temp password (send initial access email)
- [ ] Check if user already in project (reject if yes)
- [ ] Create ProjectMember entry:
  - Generate unique invite_token
  - Set invite_expires_at = now + 7 days
  - invited_by = current_user_id
  - accepted_at = NULL (pending)
  - joined_at = NULL (pending)
- [ ] Send invitation email with link:
  - `/projects/{project_id}/join?token={token}`
- [ ] Log to project audit log
- [ ] Return 201 Created

#### 2.2 GET `/api/v1/projects/{project_id}/invites` (List Pending Invites)

**Purpose**: GP sees pending team invitations

**Response** (200 OK):
```json
{
  "invites": [
    {
      "invite_id": "uuid",
      "email": "dev@example.com",
      "role": "dev_senior",
      "status": "pending",
      "invited_at": "2026-04-05T12:00:00Z",
      "expires_at": "2026-04-12T23:00:00Z"
    }
  ]
}
```

#### 2.3 POST `/api/v1/projects/{project_id}/accept-invite` (User Accepts Invite)

**Purpose**: Invited user accepts project invitation

**Request** (no auth required, token in URL):
```json
{
  "token": "xyz123..."
}
```

**Response** (200 OK):
```json
{
  "project_id": "uuid",
  "project_name": "Project Name",
  "role": "dev_senior",
  "message": "Bem-vindo ao projeto! Se for sua primeira vez, configure sua senha",
  "first_access_required": true
}
```

**Behavior**:
- [ ] Accept token (no auth required)
- [ ] Look up in ProjectMember (by invite_token)
- [ ] Verify token not expired
- [ ] Verify user exists
- [ ] Update ProjectMember:
  - accepted_at = now
  - joined_at = now
- [ ] If user.first_access_completed == false:
  - Return first_access_required = true
  - Client should redirect to first access flow
- [ ] Log to GlobalAuditLog (event_type: "project_invite_accepted")
- [ ] Return 200 OK

---

### Group 3: Questionnaire & n8n Integration

#### 3.1 POST `/api/v1/questionnaires` (Create/Submit Questionnaire)

**Purpose**: Save questionnaire submission (from external form)

**Request**:
```json
{
  "project_id": "uuid",
  "project_name": "Project Name",
  "responses": {
    "project_slug": "project-slug",
    "criticality": "Alta",
    "business_area": "Tech",
    "frontend_stack": ["React", "Vite"],
    "backend_stack": ["FastAPI"],
    // ... all form fields
  }
}
```

**Response** (201 Created):
```json
{
  "questionnaire_id": "uuid",
  "project_id": "uuid",
  "status": "pending",
  "submission_date": "2026-04-05T12:00:00Z",
  "message": "Questionário submetido para análise. Você receberá um email com o resultado"
}
```

**Behavior**:
- [ ] Accept questionnaire JSON
- [ ] Create Questionnaire record (new table, see schema below)
- [ ] Store JSON in questionnaire.responses field
- [ ] Trigger n8n webhook (async):
  - POST to n8n with questionnaire_id + responses
  - n8n analyzes and returns score + conflicts
  - Store n8n result in questionnaire.n8n_analysis JSON
- [ ] Set initial status = "pending" (waiting for n8n analysis)
- [ ] Return 201 Created
- [ ] Send confirmation email to GP

#### 3.2 GET `/api/v1/questionnaires/{questionnaire_id}/status`

**Purpose**: Get questionnaire status with n8n analysis results (GP-visible)

**Response** (200 OK):
```json
{
  "questionnaire_id": "uuid",
  "status": "OK",  // Pendente, Incompleto, OK
  "submission_date": "2026-04-05T12:00:00Z",
  "observations": "Campo X apresentou conflito...",
  "restrictions": "Não usar IA externa...",
  "highlighted_fields": ["frontend_stack", "backend_stack"],
  "internal": {
    "adherence_score": 92,  // HIDDEN from GP in frontend
    "approved": true,
    "gaps_count": 0
  }
}
```

**Behavior**:
- [ ] Get questionnaire from DB
- [ ] If internal request (admin): include adherence_score + gaps
- [ ] If external request (GP): hide internal fields
- [ ] Return questionnaire status + n8n analysis

#### 3.3 GET `/api/v1/questionnaires/{questionnaire_id}` (Admin View)

**Purpose**: Admin views complete questionnaire with all scores

**Response** (200 OK):
```json
{
  "questionnaire_id": "uuid",
  "project_id": "uuid",
  "status": "OK",
  "submitted_at": "2026-04-05T12:00:00Z",
  "responses": { /* all form data */ },
  "n8n_analysis": {
    "adherence_score": 92,
    "approved": true,
    "validations": {
      "logic_conflicts": [...],
      "gaps": [...],
      "incompatibilities": [...]
    },
    "observations": "...",
    "restrictions": "...",
    "highlighted_fields": [...]
  }
}
```

---

## 📊 NEW DATABASE TABLE: Questionnaire

```python
class Questionnaire(Base):
    __tablename__ = "questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # Submission
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=now)
    
    # Form data (JSON)
    responses = Column(String, nullable=False)  # JSON field
    
    # n8n Analysis (JSON)
    n8n_analysis = Column(String, nullable=True)  # JSON field
    analysis_completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    status = Column(String(50), default="pending")  # pending, ok, incomplete, rejected
    approval_status = Column(String(50), nullable=True)  # approved, approved_with_notes, rejected
    adherence_score = Column(Integer, nullable=True)  # 0-100
    
    # Observations & Restrictions
    observations = Column(String, nullable=True)  # For n8n to populate
    restrictions = Column(String, nullable=True)  # For n8n to populate
    
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    
    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    submitted_by_user = relationship("User", foreign_keys=[submitted_by])
```

---

## 📧 EMAIL TEMPLATES (3 Types)

### Template 1: Project Approval Email

**When**: Questionnaire approved (Score ≥ 85%)

```
Assunto: ✅ Projeto [ProjectName] — Aprovado para Ingestão

Olá [GP_Name],

Seu questionário técnico foi analisado e APROVADO! 🎉

📊 Resultado da Análise:
  • Status: OK
  • Stack Recomendado: [Suggested_Stack]
  • Próximo Passo: Inicie a ingestão de artefatos

ℹ️ Observações Técnicas:
[Observations from n8n]

🔗 Próximos Passos:
  1. Convide sua equipe: /project/[id]/invite
  2. Configure credenciais: /project/[id]/credentials
  3. Inicie a ingestão: /project/[id]/ingest

[Footer com suporte]
```

### Template 2: Project Needs Revision Email

**When**: Questionnaire incomplete (Score < 85%)

```
Assunto: ⚠️ Projeto [ProjectName] — Revisão Necessária

Olá [GP_Name],

Seu questionário apresenta 1 conflito que precisa ser resolvido.

🚨 Conflitos Detectados:
  1. React + Flutter não são compatíveis
     └─ Solução: Escolha UM framework

📊 Análise:
  • Aderência Atual: 72%
  • Threshold: 85%
  • Diferença: -13%

🔗 Revisar Questionário:
[Link para corrigir]

O sistema reavaluará automaticamente após suas correções.

[Footer]
```

### Template 3: Team Invitation Email

**When**: User is invited to join project

```
Assunto: 🎉 Convite para participar do projeto [ProjectName]

Olá [UserName],

Você foi convidado para participar do projeto [ProjectName] como [Role].

📋 Dados do Projeto:
  • Nome: [ProjectName]
  • Seu Papel: [RoleName]
  • Projeto Manager: [GP_Name]

🔗 Aceitar Convite:
[Link com token]

⏰ Este convite expira em 7 dias.

[Footer]
```

---

## 🔐 SECURITY REQUIREMENTS

### Password Reset Flow
- ✅ Tokens generated with secrets.token_urlsafe(32)
- ✅ TTL: 1 hour (3600 seconds)
- ✅ Single-use: token.used flag
- ✅ Rate limiting: 5 requests per email per hour
- ✅ Generic error messages (don't reveal if email exists)
- ✅ Audit logging for all password resets

### First Access Flow
- ✅ Temporary password unique per user (generated server-side)
- ✅ Temporary password expires after 24 hours or first use
- ✅ First access forces modal (cannot be skipped)
- ✅ Middleware checks first_access_completed before allowing access
- ✅ New password replaces temporary immediately
- ✅ Password strength validation (min 12 chars, upper, number, special)

### Team Invitations
- ✅ Invite tokens unique per user + project
- ✅ Tokens expire after 7 days
- ✅ Only GP can invite to project
- ✅ Invited users get email with acceptance link
- ✅ Audit log tracks who invited whom

---

## 🚀 IMPLEMENTATION ORDER

### Phase 1 (Now)
1. ✅ Database schema (User + ResetToken models) — DONE
2. **Next**: Password reset endpoints (auth service methods)
3. **Next**: First access endpoint (auth service methods)

### Phase 2 (Session 09 continuation)
4. Project team invite endpoints (projects service)
5. Questionnaire submission + status endpoints
6. Email service integration

### Phase 3 (Session 10)
7. n8n webhook handler (mock for now)
8. Frontend integration (React components)
9. End-to-end testing

---

## 📁 FILES TO CREATE/UPDATE

### New Files
- [ ] `GCA/backend/app/schemas/questionnaire.py` (Questionnaire schemas)
- [ ] `GCA/backend/app/schemas/reset_token.py` (ResetToken schemas)
- [ ] `GCA/backend/app/services/questionnaire_service.py`
- [ ] `GCA/backend/app/routers/questionnaires.py`

### Updated Files
- [x] `GCA/backend/app/models/base.py` (User + ResetToken)
- [ ] `GCA/backend/app/routers/auth.py` (new endpoints)
- [ ] `GCA/backend/app/services/auth_service.py` (new methods)
- [ ] `GCA/backend/app/services/email_service.py` (new templates)

---

## ✅ CHECKLIST

### Database Schema
- [x] Add `first_access_completed` to User
- [x] Add `password_changed_at` to User
- [x] Create ResetToken model
- [ ] Create Questionnaire model
- [ ] Run migration

### Auth Endpoints
- [ ] POST `/auth/reset-password` (request)
- [ ] POST `/auth/verify-reset-token` (verify)
- [ ] POST `/auth/reset-password-confirm` (confirm)
- [ ] POST `/auth/change-first-password` (first access)

### Project Endpoints
- [ ] POST `/projects/{id}/invite` (invite team)
- [ ] GET `/projects/{id}/invites` (list invites)
- [ ] POST `/projects/{id}/accept-invite` (accept)

### Questionnaire Endpoints
- [ ] POST `/questionnaires` (submit)
- [ ] GET `/questionnaires/{id}/status` (get status)
- [ ] GET `/questionnaires/{id}` (admin view)

### Services
- [ ] AuthService.reset_password()
- [ ] AuthService.verify_reset_token()
- [ ] AuthService.confirm_password_reset()
- [ ] AuthService.change_first_password()
- [ ] ProjectService.invite_team_member()
- [ ] ProjectService.accept_invite()
- [ ] QuestionnaireService.submit()
- [ ] QuestionnaireService.get_status()

### Email
- [ ] Template: Project Approved
- [ ] Template: Project Needs Revision
- [ ] Template: Team Invitation
- [ ] Template: First Access (password change required)
- [ ] Template: Password Reset Confirmation

---

## 🎯 STATUS

🟡 **IN PROGRESS**: 
- Database schema — COMPLETE
- Backend endpoints — PLANNED
- Services — PLANNED

🟢 **NEXT STEP**: Implement password reset auth endpoints

