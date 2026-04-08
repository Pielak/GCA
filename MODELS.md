# GCA — Models (Pydantic)

Estrutura de dados em Python para o GCA.

## 📊 Global Models

### User
```python
from pydantic import BaseModel, EmailStr
from datetime import datetime
from uuid import UUID

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str  # min 12 chars

class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True
```

### Organization
```python
class OrganizationCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str]

class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    owner_id: UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
```

### Project (Global Metadata)
```python
class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str]

class ProjectResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: Optional[str]
    status: str  # initializing, wizard_step_1-4, active, archived
    wizard_completed_at: Optional[datetime]
    provisioning_status: str  # pending, in_progress, completed, failed
    created_at: datetime

    class Config:
        from_attributes = True
```

### ProjectMember
```python
class ProjectMemberInvite(BaseModel):
    email: EmailStr
    role: str  # gp, tech_lead, dev, qa, compliance, viewer

class ProjectMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    role: str
    joined_at: Optional[datetime]
    invited_at: datetime

    class Config:
        from_attributes = True
```

### Session & Auth
```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenData(BaseModel):
    user_id: UUID
    email: str
    is_admin: bool
    organizations: List[UUID]
    projects: Dict[UUID, List[str]]  # {project_id: [roles]}
```

---

## 🏗️ Tenant Models (OCG)

### ProjectProfile
```python
class ProjectProfile(BaseModel):
    """Características do projeto"""
    project_type: str  # standalone, saas, corporate, open_source
    deployment_model: str  # cloud, on_premises, hybrid, local
    is_critical: bool
    requires_audit: bool
    team_size: int
    github_repo_url: Optional[str]

class OutputProfile(BaseModel):
    """Tipo de saída esperada"""
    output_type: str  # web_app, desktop, mobile, api, executável, daemon, library
    frontend_framework: Optional[str]  # react, vue, angular, svelte
    backend_framework: Optional[str]  # fastapi, nestjs, spring, django
    target_platforms: List[str]  # windows, macos, linux, ios, android

class StackProfile(BaseModel):
    """Tecnologias selecionadas"""
    language: str
    framework: Optional[str]
    orm: Optional[str]
    database: Optional[str]
    cache: Optional[str]
    message_broker: Optional[str]
    testing_framework: Optional[str]
    additional_tools: List[str]

class ComplianceProfile(BaseModel):
    """Regulamentação e compliance"""
    compliance_level: str  # leve, moderado, rigoroso
    requires_lgpd: bool
    requires_gdpr: bool
    requires_hipaa: bool
    requires_pci_dss: bool
    ai_provider_restrictions: List[str]  # allowed AI providers
    data_residency: Optional[str]  # br, eu, us, none
    encryption_required: bool
    audit_log_retention_days: int
```

### OCG (Objeto de Contexto Global)
```python
class OCG(BaseModel):
    """Contexto centralizado do projeto"""
    id: UUID
    project_id: UUID
    
    # Profiles
    project_profile: ProjectProfile
    output_profile: OutputProfile
    stack_profile: StackProfile
    compliance_profile: ComplianceProfile
    
    # Estado
    status: str  # initializing, configuring, ready, active
    
    # Integração
    vcs_provider: Optional[str]  # github, gitlab
    vcs_repo_url: Optional[str]
    vcs_webhook_id: Optional[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    propagated_at: Optional[datetime]

    class Config:
        from_attributes = True
```

### OCG Wizard Steps

**Step 1: Credenciais e Integrações**
```python
class OCGWizardStep1(BaseModel):
    # IA Provider
    ai_provider: str  # claude, openai, etc
    ai_api_key_secret_id: UUID  # referência para credencial armazenada
    
    # VCS
    vcs_provider: str  # github, gitlab
    vcs_personal_access_token_secret_id: UUID
    vcs_repo_url: str
    
    # Slack (opcional)
    slack_webhook_url_secret_id: Optional[UUID]
    
    # Teams (opcional)
    teams_webhook_url_secret_id: Optional[UUID]
```

**Step 2: Repositório**
```python
class OCGWizardStep2(BaseModel):
    vcs_provider: str
    vcs_repo_url: str
    vcs_branch_default: str  # main, develop, master
    vcs_webhook_registered: bool
```

**Step 3: Dados Básicos + Profiles**
```python
class OCGWizardStep3(BaseModel):
    project_profile: ProjectProfile
    output_profile: OutputProfile
    stack_profile: StackProfile
    compliance_profile: ComplianceProfile
```

**Step 4: Equipe**
```python
class OCGWizardStep4(BaseModel):
    members: List[ProjectMemberInvite]
```

---

## 📄 Artifact Models

```python
class ArtifactCreate(BaseModel):
    filename: str
    mime_type: str
    file_size: int

class ArtifactResponse(BaseModel):
    id: UUID
    filename: str
    status: str  # ingested, classified, quarantined, approved, merged
    
    # Scores P1-P7
    p1_score: Optional[float]
    p2_score: Optional[float]
    p3_score: Optional[float]
    p4_score: Optional[float]
    p5_score: Optional[float]
    p6_score: Optional[float]
    p7_score: Optional[float]
    
    # LGPD
    pii_detected: bool
    pii_details: Optional[dict]
    
    content_hash: str
    created_at: datetime

    class Config:
        from_attributes = True
```

---

## ⚙️ Gatekeeper Models

```python
class GatekeeperEvaluation(BaseModel):
    id: UUID
    project_id: UUID
    
    # Scores
    p1_score: float
    p2_score: float
    p3_score: float
    p4_score: float
    p5_score: float
    p6_score: float
    p7_score: float
    overall_score: float
    
    # Status
    gaps: List[dict]
    recommendations: List[str]
    blocking_status: str  # none, blocked_p7
    
    created_at: datetime

    class Config:
        from_attributes = True

class GatekeeperQuestion(BaseModel):
    pillar: str
    question: str
    priority: str  # critical, high, medium

class GatekeeperResponse(BaseModel):
    question_id: UUID
    response: str
    evidence_urls: Optional[List[str]]
```

---

## 🧪 QA Models

```python
class TestPlan(BaseModel):
    id: UUID
    project_id: UUID
    test_type: str  # unit, integration, regression
    test_name: str
    test_code: str
    expected_outcome: str
    status: str  # draft, approved, deprecated
    created_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class TestExecution(BaseModel):
    id: UUID
    test_plan_id: UUID
    status: str  # running, passed, failed, timeout
    output: str
    coverage_percentage: float
    duration_seconds: float
    executed_at: datetime

    class Config:
        from_attributes = True
```

---

## 🔐 Credential Models

```python
class CredentialCreate(BaseModel):
    name: str
    type: str  # vcs_token, docker_registry, api_key, etc
    provider: str
    secret_value: str  # será criptografado
    expires_at: Optional[datetime]

class CredentialResponse(BaseModel):
    """Response nunca mostra secret em texto claro"""
    id: UUID
    name: str
    type: str
    provider: str
    is_active: bool
    expires_at: Optional[datetime]
    last_rotated_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
```

---

## 📊 Audit Log Models

```python
class AuditLogEvent(BaseModel):
    id: UUID
    event_type: str
    actor_id: Optional[UUID]
    actor_email: Optional[str]
    resource_type: str
    resource_id: Optional[UUID]
    details: dict
    previous_hash: Optional[UUID]  # para chain
    created_at: datetime

    class Config:
        from_attributes = True
```

---

## 🔗 Estrutura de Pastas (Backend)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── database.py
│   │   └── constants.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── global.py        # User, Organization, Project, etc
│   │   ├── ocg.py           # OCG, Artifact, etc
│   │   ├── gatekeeper.py    # Gatekeeper, Evaluation
│   │   └── audit.py         # AuditLog
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── organization.py
│   │   ├── project.py
│   │   ├── ocg.py
│   │   └── artifact.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          # Login, signup, token refresh
│   │   ├── users.py
│   │   ├── organizations.py
│   │   ├── projects.py
│   │   ├── ocg.py           # OCG Wizard, context
│   │   ├── artifacts.py
│   │   ├── gatekeeper.py
│   │   └── qa.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── credential_service.py
│   │   ├── ocg_service.py   # OCG Wizard logic
│   │   ├── provisioning_service.py
│   │   ├── artifact_service.py
│   │   └── gatekeeper_service.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── session.py
│   │   └── tenant_aware.py
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py          # JWT validation
│       └── tenant.py        # Tenant context
├── tests/
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── .env.example
```

---

## 📌 Próximo Passo

Com base nesses modelos, vou criar:
- **FastAPI app base**
- **Routers para Auth + OCG Wizard**
- **Serviços para lógica de negócio**
- **Middleware para multi-tenancy**
