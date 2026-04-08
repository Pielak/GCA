# 📧 Email Notifications — GCA SMTP Setup

## ✅ Configuração Completada

```
SMTP_ENABLED=True
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="pielak.ctba@gmail.com"
SMTP_PASSWORD="bvak gqef wdyt mbyi"
SMTP_FROM_EMAIL="pielak.ctba@gmail.com"
SMTP_FROM_NAME="GCA - Gerenciador Central de Arquiteturas"
```

Configurado em: `.env` (não commitado)

---

## 🔧 Tecnologia

- **SMTP Provider**: Gmail
- **Port**: 587 (TLS)
- **Auth**: OAuth2 App-Specific Password
- **Service**: `app/services/email_service.py`

---

## 📬 Tipos de Email Implementados

### 1. Welcome Email
**Quando**: User bootstrap ou criação

```python
EmailService.send_welcome_email(
    user_email="user@example.com",
    user_name="João"
)
```

### 2. Password Reset
**Quando**: Solicitar redefinição de senha

```python
EmailService.send_password_reset_email(
    user_email="user@example.com",
    user_name="João",
    reset_link="https://gca.com/reset?token=xxx"
)
```

### 3. Project Invitation
**Quando**: Convidar usuário para projeto (OCG Wizard Step 4)

```python
EmailService.send_project_invitation_email(
    to_email="user@example.com",
    inviter_name="Admin",
    project_name="Projeto A",
    invitation_link="https://gca.com/invites/xxx",
    role="tech_lead"
)
```

### 4. Gatekeeper Notification
**Quando**: Avaliação Gatekeeper (M6) concluída

```python
EmailService.send_gatekeeper_notification_email(
    to_email="user@example.com",
    user_name="João",
    project_name="Projeto A",
    blocking_status="none",  # "none" or "blocked_p7"
    overall_score=8.5,
    dashboard_link="https://gca.com/projects/xxx"
)
```

### 5. Custom Email
Para qualquer outro tipo de notificação:

```python
success, error = EmailService.send_email(
    to_email="user@example.com",
    subject="Assunto",
    html_content="<p>Conteúdo HTML</p>",
    text_content="Conteúdo texto",
    cc=["cc@example.com"],
    bcc=["bcc@example.com"]
)

if success:
    print("Email enviado!")
else:
    print(f"Erro: {error}")
```

---

## 🔐 Segurança — Senha do Gmail

A senha usada não é sua senha do Gmail normal. É uma **App-Specific Password** gerada especificamente para este aplicativo.

**Como foi gerado:**
1. Google Account → Security → App passwords
2. Selecionou: Mail + Custom app (GCA)
3. Google gerou: `bvak gqef wdyt mbyi`

**Vantagens:**
- ✅ Mais seguro que usar senha do Gmail diretamente
- ✅ Pode ser revogado sem afetar conta pessoal
- ✅ Acesso apenas para envio de email

**Se comprometer a senha:**
1. Vá para: https://myaccount.google.com/apppasswords
2. Clique em "Remover" (revoke a senha)
3. Gere uma nova App Password
4. Atualize `.env` com a nova senha

---

## 🚀 Uso nos Routers

### Exemplo: Bootstrap Admin com Email

```python
from app.services.email_service import EmailService

@router.post("/bootstrap-admin", response_model=LoginResponse)
async def bootstrap_admin(
    req: BootstrapAdminRequest,
    db: Session = Depends(get_db),
):
    success, user, error = AuthService.bootstrap_admin(...)
    
    if success:
        # Enviar email de boas-vindas
        EmailService.send_welcome_email(
            user_email=user.email,
            user_name=user.full_name
        )
        
        # Retornar tokens
        access_token, refresh_token, expires_in = AuthService.create_tokens(user)
        return LoginResponse(...)
```

### Exemplo: Invitar usuário para projeto (Phase 4)

```python
@router.post("/api/v1/projects/{project_id}/invite-member")
async def invite_member(
    project_id: UUID,
    invite_req: ProjectMemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Criar convite no BD
    invitation = ProjectMember(
        project_id=project_id,
        email=invite_req.email,
        role=invite_req.role,
        invite_token=generate_token(),
        invite_expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db.add(invitation)
    db.commit()
    
    # Enviar email de convite
    EmailService.send_project_invitation_email(
        to_email=invite_req.email,
        inviter_name=current_user.full_name,
        project_name=project.name,
        invitation_link=f"http://localhost:8000/invites/{invitation.invite_token}",
        role=invite_req.role
    )
```

---

## 📊 Fluxo de Emails no GCA

```
Phase 1: Autenticação
├── Bootstrap Admin
│   └── → Welcome Email ✅
├── User Login
│   └── (Sem email)
└── Password Reset
    └── → Password Reset Email (TODO)

Phase 4: OCG Wizard
├── Step 4: Team
│   └── → Project Invitation Email ✅

Phase 6: Gatekeeper (M6)
├── Evaluation Complete
│   └── → Gatekeeper Notification Email ✅

Future Phases:
├── M4: Artifacts approved
│   └── → Notification
├── M8: Code generation complete
│   └── → Notification
└── M9: QA insights ready
    └── → Notification
```

---

## ⚙️ Configuração de Produção

### Cambiar de Gmail para outro provedor

Se você quiser usar outro provedor SMTP (SendGrid, Mailgun, AWS SES, etc):

```env
# SendGrid
SMTP_HOST="smtp.sendgrid.net"
SMTP_PORT=587
SMTP_USER="apikey"
SMTP_PASSWORD="your-sendgrid-api-key"

# Mailgun
SMTP_HOST="smtp.mailgun.org"
SMTP_PORT=587
SMTP_USER="postmaster@your-domain.com"
SMTP_PASSWORD="your-mailgun-password"

# AWS SES
SMTP_HOST="email-smtp.region.amazonaws.com"
SMTP_PORT=587
SMTP_USER="your-ses-username"
SMTP_PASSWORD="your-ses-password"
```

---

## 🧪 Testar Email Localmente

```python
# No Python shell ou teste
from app.services.email_service import EmailService

success, error = EmailService.send_email(
    to_email="seu-email@gmail.com",
    subject="Teste GCA",
    html_content="<p>Teste de email do GCA</p>"
)

if success:
    print("✅ Email enviado com sucesso!")
else:
    print(f"❌ Erro: {error}")
```

---

## 🔍 Troubleshooting

### Erro: "SMTP authentication failed"
**Causa**: Senha incorreta ou credenciais inválidas

**Solução**:
1. Verifique `.env` está com as credenciais corretas
2. Regenere a App Password no Gmail
3. Atualize `.env`

### Erro: "Connection refused"
**Causa**: SMTP_HOST ou SMTP_PORT incorretos

**Solução**: Verifique que está usando:
- Host: `smtp.gmail.com`
- Port: `587` (TLS)

### Erro: "Less secure app access"
**Causa**: Gmail bloqueou acesso (raro com App Password)

**Solução**: Use App Password em vez de senha normal

### Email não chega
**Causa**: Pode estar em spam

**Solução**: 
1. Cheque pasta de spam
2. Aumente reputação do domínio (SPF, DKIM)
3. Use SendGrid ou outro provedor profissional em produção

---

## 📋 Checklist

- [x] SMTP configurado em `.env`
- [x] App Password gerado no Gmail
- [x] EmailService implementado
- [x] 4 templates de email criados
- [x] Documentação completa
- [ ] Integrado em Bootstrap Admin router
- [ ] Integrado em Project Invitation (Phase 4)
- [ ] Integrado em Gatekeeper (Phase 6)
- [ ] Testes unitários para EmailService

---

## 📚 Arquivo Relevante

- `app/services/email_service.py` — Implementação completa
- `app/core/config.py` — Configuração SMTP
- `.env` — Credenciais (não commitado)
- `.env.example` — Template

---

**Configuração**: ✅ Completa  
**Status**: Pronto para uso em routers  
**Próximo**: Integrar em routers conforme necessário (Phase 4+)

**Última atualização**: 2026-04-04
