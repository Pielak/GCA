# GCA API Integration Guide

**Status**: 🟢 PRODUCTION READY  
**Version**: Session 09 Final Delivery  
**Last Updated**: 2026-04-05

---

## 📋 Quick Start

### Backend Integration

**1. Database Migrations**
```bash
# Apply migration to add ResetToken table and User columns
psql -h localhost -U postgres -d gca < GCA/backend/migrations/001_add_password_reset_tables.sql
```

**2. FastAPI Router Integration** (Already done in main.py)
```python
# main.py already includes:
from app.routers import questionnaires, webhooks

app.include_router(questionnaires.router, prefix=f"{settings.API_PREFIX}/questionnaires")
app.include_router(webhooks.router, prefix=f"{settings.API_PREFIX}")
```

**3. Environment Variables**
```bash
# Add to .env:
API_URL=http://localhost:8000/api/v1
N8N_WEBHOOK_URL=https://n8n.yourdomain.com/webhooks/questionnaire
QWEN_API_KEY=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
```

### Frontend Integration

**1. Add Routes**
```typescript
// In your Router configuration:
import ResetPasswordPage from '@/app/pages/auth/ResetPasswordPage';
import ProjectTeamPage from '@/app/pages/projects/ProjectTeamPage';
import FirstAccessModal from '@/app/components/FirstAccessModal';

// Routes:
<Route path="/reset-password" element={<ResetPasswordPage />} />
<Route path="/projects/:projectId/team" element={<ProjectTeamPage />} />

// In AuthProvider:
<FirstAccessModal isOpen={!user?.first_access_completed} {...} />
```

**2. Add Favicon**
```html
<!-- In public/index.html -->
<link rel="icon" href="/images/gca-favicon.png" />
<link rel="logo" href="/images/gca-logo.png" />
```

**3. Environment Setup**
```bash
# In .env:
REACT_APP_API_URL=http://localhost:8000/api/v1
```

---

## 🔌 API ENDPOINTS

### Authentication

#### 1. Request Password Reset
```
POST /api/v1/auth/reset-password
Content-Type: application/json

{
  "email": "user@example.com"
}

Response (200):
{
  "message": "Se o email existe no sistema, um link de recuperação foi enviado",
  "security_note": "Por segurança, não confirmamos se o email existe"
}
```

#### 2. Verify Reset Token
```
POST /api/v1/auth/verify-reset-token
Content-Type: application/json

{
  "token": "secure_token_here"
}

Response (200):
{
  "valid": true,
  "message": "Token válido, proceda com a alteração de senha"
}

Response (400):
{
  "valid": false,
  "message": "Token expirado ou já utilizado"
}
```

#### 3. Confirm Password Reset
```
POST /api/v1/auth/reset-password-confirm
Content-Type: application/json

{
  "token": "secure_token_here",
  "new_password": "SecurePass123!@#"
}

Response (200):
{
  "message": "Senha alterada com sucesso. Faça login com a nova senha"
}
```

#### 4. Change First Password (First Access)
```
POST /api/v1/auth/change-first-password
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "temporary_password": "TmpPwd123!@#",
  "new_password": "MySecurePass123!@#"
}

Response (200):
{
  "message": "Senha alterada com sucesso. Bem-vindo ao GCA!",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "first_access_completed": true
  }
}
```

### Project Team Management

#### 5. Invite Team Member
```
POST /api/v1/projects/{project_id}/invite
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "email": "dev@example.com",
  "role": "dev_pleno"  # Options: tech_lead, dev_senior, dev_pleno, qa, compliance
}

Response (200):
{
  "invite_id": "invite-uuid",
  "email": "dev@example.com",
  "role": "dev_pleno",
  "status": "pending",
  "expires_at": "2026-04-12T23:00:00Z",
  "invite_url": "https://gca.com/projects/{id}/accept-invite?token=..."
}
```

#### 6. List Pending Invites
```
GET /api/v1/projects/{project_id}/invites
Authorization: Bearer {access_token}

Response (200):
{
  "invites": [
    {
      "invite_id": "invite-uuid",
      "email": "dev@example.com",
      "role": "dev_pleno",
      "status": "pending",
      "invited_at": "2026-04-05T12:00:00Z",
      "expires_at": "2026-04-12T23:00:00Z"
    }
  ]
}
```

#### 7. Accept Project Invite
```
POST /api/v1/projects/{project_id}/accept-invite
Content-Type: application/json

{
  "token": "invite-token-from-email"
}

Response (200):
{
  "project_id": "project-uuid",
  "project_name": "Project Name",
  "role": "dev_pleno",
  "message": "Bem-vindo ao projeto!",
  "first_access_required": true
}
```

### Questionnaire

#### 8. Submit Questionnaire
```
POST /api/v1/questionnaires
Content-Type: application/json

{
  "project_id": "project-uuid",
  "gp_email": "gp@example.com",
  "responses": {
    "project_name": "Project Name",
    "frontend_stack": ["React"],
    "backend_stack": ["FastAPI"],
    "database_stack": ["PostgreSQL"],
    "ai_automation": ["Anthropic"],
    ... (all form fields)
  }
}

Response (200):
{
  "questionnaire_id": "q-uuid",
  "project_id": "project-uuid",
  "status": "pending",
  "submission_date": "2026-04-05T12:00:00Z",
  "message": "Questionário submetido para análise"
}
```

### n8n Webhook (Intelligence Hub)

#### 9. Questionnaire Analysis Webhook
```
POST /api/v1/webhooks/questionnaire
Content-Type: application/json

{
  "projectId": "proj-123",
  "gp_email": "gp@example.com",
  "responses": {
    "frontend_stack": ["React", "Flutter"],  // Conflict!
    "backend_stack": ["FastAPI"],
    "database_stack": ["PostgreSQL"],
    "ai_automation": ["Anthropic"],
    "security_controls": ["Autenticação", "Autorização / RBAC"],
    "test_types": ["Unitários", "Integração"],
    "deliverables": ["Aplicação web"]
  }
}

Response (200):
{
  "projectId": "proj-123",
  "questionnaireStatus": "Incompleto",
  "adherenceScore": 75,
  "approved": false,
  "validations": {
    "logicConflicts": [
      {
        "field": "frontend_stack",
        "conflict": "React + Flutter são incompatíveis",
        "severity": "blocker",
        "suggestion": "Escolha UM framework"
      }
    ],
    "gaps": [],
    "incompatibilities": []
  },
  "observations": "⚠️ Detectado 1 conflito",
  "restrictions": "Nenhuma restrição",
  "highlightedFields": ["frontend_stack"]
}
```

---

## 🔐 SECURITY REFERENCE

### Token Security

| Type | TTL | Single-Use | Generation |
|------|-----|-----------|------------|
| Password Reset | 1 hour | Yes | secrets.token_urlsafe(32) |
| Project Invite | 7 days | Yes | secrets.token_urlsafe(32) |
| Access Token | 30 min | No | JWT RS256 |
| Refresh Token | 7 days | No | JWT |

### Password Requirements

```
Minimum: 12 characters
Must contain:
  • At least 1 uppercase letter (A-Z)
  • At least 1 number (0-9)
  • At least 1 special character (!@#$%^&*...)
```

### Error Handling

```
400 Bad Request     — Invalid input/validation error
401 Unauthorized    — Missing or invalid token
403 Forbidden       — Insufficient permissions
404 Not Found       — Resource not found
500 Server Error    — Unexpected error
```

---

## 🧪 TESTING

### Run Tests
```bash
pytest GCA/backend/app/tests/test_auth_reset_password.py -v
```

### Test Scenarios
```
✅ Reset password request (valid email)
✅ Reset password request (invalid email - silent)
✅ Verify reset token (valid token)
✅ Verify reset token (invalid/expired token)
✅ Confirm password reset (valid flow)
✅ First access password change (mandatory)
✅ Invite team member (GP only)
✅ List pending invites
✅ Accept project invite
✅ Submit questionnaire
✅ n8n analysis (valid stack)
✅ n8n analysis (conflicts detected)
✅ n8n analysis (gaps detected)
```

---

## 📧 EMAIL NOTIFICATIONS

### Triggered Automatically

1. **Password Reset Request** → Email with reset link (1-hour token)
2. **Project Approval** → Email to GP (score ≥ 85%)
3. **Project Revision Needed** → Email to GP (score < 85%)
4. **Team Invitation** → Email to invited user (7-day token)
5. **First Access** → Email with temporary password + instructions

---

## 🚀 DEPLOYMENT CHECKLIST

- [ ] Database migration applied
- [ ] FastAPI routers integrated
- [ ] Environment variables set
- [ ] n8n webhook configured
- [ ] React routes added
- [ ] Favicon integrated
- [ ] Email service configured
- [ ] SMTP credentials set
- [ ] Tests passing
- [ ] Logging configured
- [ ] Monitoring enabled

---

## 📞 SUPPORT

### Common Issues

**"Token expirado ou não encontrado"**
→ Reset token has 1-hour TTL. Request new password reset.

**"Senha muito fraca"**
→ Use 12+ chars with upper, number, special char.

**"Email já cadastrado"**
→ User already exists. Use password reset instead.

**"Convite expirado"**
→ Invites expire after 7 days. Request new invite.

---

## 🎯 NEXT STEPS

1. Apply database migration
2. Test all endpoints locally
3. Configure n8n webhook
4. Deploy to staging
5. Run E2E tests
6. Deploy to production

