#!/usr/bin/env python3
"""
Gera diagramas Mermaid (sequência / fluxo / estado) do GCA como PNGs
em docs/diagrams/ para serem embedados nos documentos .docx.

Usa `mmdc` (@mermaid-js/mermaid-cli) já instalado em ~/.npm-global/bin/mmdc.
"""
import subprocess
import sys
from pathlib import Path

MMDC = "/home/luiz/.npm-global/bin/mmdc"
OUT = Path("/home/luiz/GCA/docs/diagrams")
OUT.mkdir(parents=True, exist_ok=True)

# Config tema escuro-claro legível em doc
PUPPETEER_CFG = OUT / ".puppeteer-config.json"
# Puppeteer precisa do path do Chrome recém-instalado via `npx puppeteer browsers install`
import os as _os
_chrome_bin = _os.environ.get(
    "PUPPETEER_EXECUTABLE_PATH",
    "/home/luiz/.cache/puppeteer/chrome-headless-shell/linux-147.0.7727.56/chrome-headless-shell-linux64/chrome-headless-shell",
)
PUPPETEER_CFG.write_text(
    f'{{"args": ["--no-sandbox"], "executablePath": "{_chrome_bin}"}}',
    encoding="utf-8",
)


DIAGRAMS = {
    # ─── SEQUÊNCIA ─────────────────────────────────────────────────────
    "seq_login_admin": """
sequenceDiagram
    autonumber
    actor A as Admin
    participant UI as Frontend (React)
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL
    participant JWT as JWT Service

    A->>UI: Acessa /login, digita e-mail e senha
    UI->>API: POST /api/v1/auth/login
    API->>DB: SELECT user WHERE email
    DB-->>API: User (password_hash, is_admin)
    API->>API: verify_password(plain, hash)
    alt Credenciais válidas
        API->>JWT: create_access_token(sub=user.id)
        JWT-->>API: JWT assinado (HS256)
        API->>DB: UPDATE last_login_at
        API-->>UI: 200 { access_token, user }
        UI->>UI: Armazena token em memória + redirect /admin
        UI-->>A: Dashboard Global
    else Inválido
        API-->>UI: 401 Unauthorized
        UI-->>A: Mensagem "Credenciais inválidas"
    end
""",
    "seq_login_projeto": """
sequenceDiagram
    autonumber
    actor U as Usuário (Dev/Tester/QA/GP)
    participant UI as Frontend
    participant API as Backend
    participant DB as PostgreSQL

    U->>UI: Acessa /p/{slug} (URL do projeto)
    UI->>API: GET /projects/by-slug/{slug}
    API->>DB: SELECT project WHERE slug
    DB-->>API: Project (id, name, status)
    API-->>UI: Project resumo
    UI-->>U: Form de login contextualizado
    U->>UI: Digita credenciais
    UI->>API: POST /api/v1/auth/login
    API->>DB: SELECT user
    DB-->>API: User
    API->>DB: SELECT project_members WHERE user AND project
    DB-->>API: Membership (role)
    API->>API: Verifica role ∈ {gp, dev, tester, qa}
    API-->>UI: 200 { token, memberships }
    UI-->>U: Dashboard do Projeto (respeitando RBAC)
""",
    "seq_criar_projeto": """
sequenceDiagram
    autonumber
    actor R as Solicitante
    actor Adm as Admin
    participant UI as Frontend
    participant API as Backend
    participant DB as PostgreSQL
    participant Mail as EmailService

    R->>UI: Acessa /solicitar-projeto
    UI->>API: GET /public/project-requests (fields)
    UI-->>R: Wizard 2 passos (dados + questionário)
    R->>UI: Submete solicitação
    UI->>API: POST /public/project-requests
    API->>DB: INSERT project_requests (PENDING)
    API->>Mail: Notifica admins
    API-->>UI: 201 request_id
    Note over R,UI: Solicitação aguarda aprovação

    Adm->>UI: /admin/projects (lista pendentes)
    UI->>API: GET /admin/projects/pending
    API->>DB: SELECT project_requests ... LEFT JOIN projects
    DB-->>API: Requests + project_lifecycle_status
    API-->>UI: Lista
    Adm->>UI: Aprova
    UI->>API: POST /admin/projects/{id}/approve
    API->>DB: INSERT projects (status=active)
    API->>DB: UPDATE project_requests SET status=APPROVED
    API->>Mail: Notifica solicitante (agora GP)
    API-->>UI: 200 project_id
    UI-->>Adm: Projeto criado + card "Provisionado"
""",
    "seq_ocg_generation": """
sequenceDiagram
    autonumber
    actor GP
    participant UI
    participant API
    participant Q as QuestionnaireService
    participant AG as AgentService (8 agentes)
    participant DB as PostgreSQL
    participant LLM as Provedor IA

    GP->>UI: Upload PDF de questionário em /projects/{id}/settings?tab=questionario
    UI->>API: POST /questionnaire/upload-pdf
    API->>Q: submit_questionnaire (parse AcroForm)
    Q->>DB: INSERT questionnaire
    Q->>Q: TechnologyVerificationService (8 fases)
    Q-->>API: adherence_score + findings
    API->>AG: trigger analyze_questionnaire
    par 7 pilares em paralelo
        AG->>LLM: analyze_pillar P1 (Business)
        LLM-->>AG: pillar_result
        AG->>LLM: analyze_pillar P2..P7
        LLM-->>AG: pillar_results
    end
    AG->>LLM: consolidate_ocg (premium — alta criticidade §6.2)
    LLM-->>AG: OCG completo (STACK, ARCH, COMPLIANCE, TESTING, RISK, DELIVERABLES)
    AG->>DB: UPSERT ocg (por questionnaire_id)
    AG->>DB: INSERT ocg_analysis_log + ai_usage_log
    AG-->>API: OCG ID
    API-->>UI: 200 ocg ready
    UI-->>GP: Dashboard do projeto com OCG preenchido
""",
    "seq_ticket_release": """
sequenceDiagram
    autonumber
    actor Dev as Dev/Tester/QA
    actor GP
    actor Adm as Admin
    participant UI
    participant API
    participant DB

    Dev->>UI: /projects/{id}/incidents → "Abrir ticket"
    UI->>API: POST /projects/{id}/incidents (category, priority, flow_description, section_reference)
    API->>DB: INSERT incident_tickets (target_scope='gp')
    API->>DB: INSERT user_notifications (para GPs)
    API-->>UI: 201 ticket_id
    Note over Dev,UI: Ticket visível em /incidents

    GP->>UI: Detalhe do ticket → comentários + status
    GP->>UI: Resolve ticket
    UI->>API: PATCH /incidents/{id}/status {status: resolved}
    API->>DB: UPDATE incident_tickets
    API->>DB: INSERT user_notifications (evento resolvido)

    Note over Adm,API: Correção entregue na release seguinte
    Adm->>UI: Novo backend/releases/v0.9.0.yaml com ref_id=TICKET-{id}
    UI->>API: GET /admin/releases
    API->>DB: SELECT releases WHERE status='pending'
    API-->>UI: v0.9.0 (pending, is_destructive=true)
    Adm->>UI: "Aplicar com snapshot"
    UI->>API: POST /admin/releases/{id}/apply {confirm:true}
    loop projetos ativos
        API->>DB: create_backup (DT-063)
        DB-->>API: snapshot_id
        API->>DB: INSERT release_application_log (snapshot_taken)
    end
    API->>DB: UPDATE release SET status=applied
    API-->>UI: { snapshots_taken, status: applied }
    UI-->>Adm: Release marcada aplicada + log com snapshots
""",
    "seq_backup_restore": """
sequenceDiagram
    autonumber
    participant S as Scheduler (APScheduler 12:00)
    participant BS as BackupService
    participant DB as PostgreSQL
    participant V as Volume gca-backups
    actor GP

    S->>BS: daily_backup_job()
    BS->>DB: SELECT projects WHERE status='active'
    DB-->>BS: projetos ativos
    loop cada projeto
        BS->>BS: create_backup(trigger='scheduled')
        BS->>DB: SELECT row_to_json(t) por 29 tabelas WHERE project_id
        DB-->>BS: JSONLs
        BS->>BS: zip + sha256 + manifest.json
        BS->>V: grava zip
        BS->>DB: INSERT project_backups (completed)
        BS->>DB: UPDATE projects SET last_backup_at
        BS->>BS: cleanup: mantém 10 últimos
    end

    Note over GP: Precisa reverter algo
    GP->>BS: POST /projects/{id}/backups/{bid}/restore?confirm=true
    BS->>V: lê zip + revalida sha256
    alt SHA OK
        BS->>DB: DELETE linhas do projeto (29 tabelas, ordem inv. FK)
        BS->>DB: INSERT linhas do backup
        BS->>DB: UPDATE project_backups SET restored_at
        BS-->>GP: 200 restore aplicado
    else SHA mismatch
        BS-->>GP: 500 integridade comprometida
    end
""",

    # ─── FLUXO ────────────────────────────────────────────────────────
    "flow_projeto_lifecycle": """
stateDiagram-v2
    [*] --> Solicitado: /solicitar-projeto
    Solicitado --> Pendente: request criada (PENDING)
    Pendente --> Rejeitado: Admin rejeita
    Pendente --> Aprovado: Admin aprova
    Aprovado --> Ativo: projects.status=active
    Ativo --> Pausado: PATCH /admin/projects/{id}/status {status:paused}
    Pausado --> Ativo: reativar
    Ativo --> Desativado: encerramento sem deleção
    Pausado --> Desativado: encerramento sem deleção
    Desativado --> Ativo: reativar
    Rejeitado --> [*]
    note right of Pausado
        Scheduler de backup
        automático é suspenso.
        Dados preservados.
    end note
    note right of Desativado
        Dados preservados
        para consulta/auditoria.
        Sem backup automático.
    end note
""",
    "flow_ticket_lifecycle": """
stateDiagram-v2
    [*] --> Aberto: Dev/Tester/QA cria ticket
    [*] --> Aberto: GP cria ticket (escala p/ Admin)
    Aberto --> EmAndamento: GP/Admin assume
    EmAndamento --> Resolvido: correção entregue
    Resolvido --> EmAndamento: reabertura (bug volta)
    Resolvido --> Fechado: confirmado pelo autor
    Fechado --> [*]
    note right of Aberto
        target_scope automático:
        Dev/Tester/QA → gp
        GP → admin
        Admin → admin
    end note
    note right of Resolvido
        resolved_at + resolved_by
        preenchidos. Rastreável
        na release seguinte.
    end note
""",
    "flow_release_lifecycle": """
stateDiagram-v2
    [*] --> Declarada: YAML em backend/releases/
    Declarada --> Pending: sync_declared_releases no startup
    Pending --> Applied_Auto: apply_nondestructive_pending\\n(se is_destructive=false)
    Pending --> Aguardando_Admin: is_destructive=true
    Aguardando_Admin --> Snapshotted: POST /admin/releases/{id}/apply\\n(take_snapshots=true)
    Snapshotted --> Applied_Manual: migrations OK + logs
    Applied_Auto --> Rolled_Back_Project: projeto específico restaura snapshot
    Applied_Manual --> Rolled_Back_Project: projeto específico restaura snapshot
    Applied_Auto --> [*]
    Applied_Manual --> [*]
    Rolled_Back_Project --> Applied_Auto: release continua aplicada\\n(rollback é por-projeto)
    Rolled_Back_Project --> Applied_Manual
""",

    # ─── RBAC ─────────────────────────────────────────────────────────
    "rbac_papeis": """
flowchart TB
    subgraph INST["Camada da Instância"]
        ADMIN["Admin<br/>(is_admin=true)"]
        SUP["Sustentação<br/>(is_support=true)"]
    end
    subgraph PROJ["Camada do Projeto"]
        GP["GP<br/>(soberano do projeto)"]
        DEV["Dev"]
        TST["Tester"]
        QA["QA"]
    end
    ADMIN -->|herda Sustentação| SUP
    ADMIN -->|pode operar| GP
    GP -->|union de ações| DEV
    GP -->|union de ações| TST
    GP -->|union de ações| QA
    SUP -.recebe tickets target=admin.-> ADMIN
    note1["Emenda 2026-04-19:<br/>GP : projeto :: Admin : instância"]
""",
}


def generate(name: str, mmd: str) -> Path:
    src = OUT / f"{name}.mmd"
    dst = OUT / f"{name}.png"
    src.write_text(mmd.strip(), encoding="utf-8")
    print(f"[mmdc] {name}.mmd → {name}.png")
    r = subprocess.run(
        [MMDC, "-i", str(src), "-o", str(dst),
         "-t", "neutral", "-b", "white",
         "-w", "1400", "-p", str(PUPPETEER_CFG)],
        capture_output=True, text=True, timeout=90,
    )
    if r.returncode != 0:
        print(f"  ERRO: {r.stderr[:400]}", file=sys.stderr)
        return None
    return dst


def main():
    ok = 0
    fail = 0
    for name, mmd in DIAGRAMS.items():
        p = generate(name, mmd)
        if p:
            ok += 1
        else:
            fail += 1
    print(f"\n{ok}/{len(DIAGRAMS)} diagramas gerados em {OUT}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
