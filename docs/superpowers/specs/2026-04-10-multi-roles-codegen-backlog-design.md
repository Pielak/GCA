# Design: Multi-Papéis + Backlog Inteligente + CodeGen Real com QA, Segurança e Compliance

**Data:** 2026-04-10  
**Status:** Aprovado (Revisado)  
**Versão:** 2.0

---

## Contexto

O GP pode acumular múltiplos papéis no projeto (GP + Dev Senior + QA + Compliance, etc.) para executar atividades que exigem papéis específicos. Cada ação registra quem fez e com qual papel (trilha de auditoria). O CodeGen busca escopo do Backlog Inteligente, que é gerado por IA a partir dos documentos ingeridos, stack e OCG. O backlog verifica completude de artefatos e compliance ISO 27001 antes de liberar itens para geração.

**Novo:** Pipeline de CodeGen agora inclui geração automática de testes, análise de segurança, validação de compliance e aprovação de QA antes do commit final.

---

## 1. Modelo de Dados — Múltiplos Papéis

**Nova tabela: `ProjectMemberRole`**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | UUID PK | |
| member_id | FK -> ProjectMember | Membro do projeto |
| role | String | "gp", "tech_lead", "dev_senior", "dev_pleno", "qa", "compliance", "stakeholder" |
| assigned_at | DateTime | Quando o papel foi atribuído |
| assigned_by | FK -> User | Quem atribuiu (o próprio GP ou Admin) |

**Regras:**
- Um membro pode ter múltiplos papéis simultâneos
- GP é o papel base — não pode ser removido pelo próprio GP
- Cada ação no pipeline registra `user_id + role_used` no audit log
- `permissions.py` acumula ações de todos os papéis do membro

---

## 2. Auto-atribuição de Papéis pelo GP

### Na aba Equipe (`/projects/{id}/team`)

O GP vê seus próprios papéis com botão "Adicionar Papel":
- Lista papéis disponíveis (Tech Lead, Dev Senior, Dev Pleno, QA, Compliance, Stakeholder)
- Seleciona um ou mais, salva
- Audit log: "GP pielak@... assumiu papel Dev Senior em 2026-04-10"

### No pipeline (on-demand)

Quando ação exige papel que o GP não tem:
- Mensagem: "Esta ação requer papel de Dev Senior"
- Botão: "Assumir este papel e continuar"
- Papel adicionado + ação executada + audit log registra ambos

### Endpoints

```
POST /projects/{project_id}/members/self/roles
Body: { roles: ["dev_senior", "qa"] }
```
- Requer `project:manage_team`
- Adiciona papéis ao membro logado
- Não pode remover "gp" de si mesmo

```
GET /projects/{project_id}/audit/roles
```
- Histórico de atribuições de papéis

---

## 3. Sistema de Permissões — Múltiplos Papéis

### permissions.py

Nova função:
```python
def get_actions_for_roles(roles: list[str]) -> set[str]:
    """Union de ações de todos os papéis."""
    actions = set()
    for role in roles:
        actions |= get_actions_for_role(role)
    return actions
```

### require_action()

`resolve_user_role_in_project()` retorna lista de papéis em vez de string única.
`require_action()` verifica se qualquer papel tem a ação.

### Retorno do /permissions

```json
{
  "roles": ["gp", "dev_senior"],
  "actions": ["project:view", "project:edit", "project:manage_team", "pipeline:execute", "code:write"],
  "is_read_only": false
}
```

### Frontend useProjectPermissions

- `role` passa a ser `roles` (array)
- `can()` continua igual (verifica na lista de ações acumuladas)

### Audit log

Cada ação protegida registra:
```json
{
  "user_id": "...",
  "action": "code:write",
  "role_used": "dev_senior",
  "project_id": "...",
  "timestamp": "..."
}
```

---

## 4. CodeGen Real com IA — Pipeline Completo com QA, Segurança e Compliance

### Fluxo de 12 Etapas

```
[1] GP seleciona item "Pronto"
    ↓
[2] CodeGen: LLM gera código
    ↓
[3] TestGen: LLM gera testes (unitários + integração)
    ↓
[4] Test Execution: CI/CD executa testes automaticamente
    ├─ Se FALHA → feedback ao LLM → volta ao [2]
    └─ Se PASSA ↓
[5] Security Review: Análise automática de vulnerabilidades
    ├─ SAST (Semgrep, SonarQube)
    ├─ Dependency scanning (npm audit, pip audit)
    ├─ Secrets scanning
    └─ OWASP Top 10 validation
    ├─ Se FALHA → bloqueia merge, requer revisão manual
    └─ Se PASSA ↓
[6] Compliance Check: ISO 27001 + LGPD + regulamentações
    ├─ Dados sensíveis criptografados?
    ├─ Logs de auditoria configurados?
    ├─ Criptografia de senhas (bcrypt 12+)?
    ├─ Retenção de dados conforme política?
    └─ Acesso granular por papel/tenant?
    ├─ Se FALHA → gera issue, bloqueia merge
    └─ Se PASSA ↓
[7] QA Approval: Papel QA valida contra specs
    ├─ Review manual contra requisitos
    ├─ Testes funcionais (manual se necessário)
    ├─ Validação de UX/fluxos críticos
    └─ Pode rejeitar com motivo → item volta a "Bloqueado"
    ├─ Se APROVADO ↓
[8] GP Review Final + Commit
    ├─ GP revisa código (todos os gates passaram)
    └─ Clica "Commit ao Repositório" → GitHub API
    ↓
[9] Audit Log: Registra trilha completa de todas as etapas
```

### Backend - Endpoints

#### CodeGen
```
POST /projects/{id}/backlog/{item_id}/generate-code
  -> require_action("code:write")
  -> Carrega item do backlog com requisitos e artefatos
  -> Carrega OCG context (stack, architecture, testing, compliance)
  -> Carrega chaves IA do Vault (per-project)
  -> Chama LLM com prompt enriquecido
  -> Retorna código gerado no editor
  -> Muda status para "Em Geração"
  -> Registra billing
```

#### TestGen
```
POST /projects/{id}/backlog/{item_id}/generate-tests
  -> require_action("code:write")
  -> LLM gera testes unitários + integração
  -> Gera arquivo _test.py / .test.ts / _test.go etc
  -> Cobertura mínima obrigatória: 70%+
  -> Retorna testes para revisão
```

#### Test Execution
```
POST /projects/{id}/ci-cd/{item_id}/run-tests
  -> require_action("pipeline:execute")
  -> Executa: pytest --cov=src --cov-report=html
  -> Executa: npm test (frontend)
  -> Verifica cobertura ≥ 70%
  -> Retorna resultado:
     {
       "status": "PASS | FAIL",
       "coverage": 82.5,
       "failed_tests": [],
       "duration_seconds": 24
     }
  -> Se FALHA: autoriza LLM a corrigir automaticamente
```

#### Security Review
```
POST /projects/{id}/security/{item_id}/scan
  -> require_action("code:write")
  -> SAST: Semgrep API para detectar vulnerabilidades
  -> Dependencies: npm audit, pip audit (via API)
  -> Secrets: scanning de hardcoded keys/tokens
  -> OWASP: validação de padrões Top 10
  -> Retorna:
     {
       "vulnerabilities": [
         {"severity": "CRITICAL", "type": "sql_injection", "location": "..."},
         {"severity": "MEDIUM", "type": "hardcoded_secret", "location": "..."}
       ],
       "status": "PASS | FAIL"
     }
  -> CRÍTICO = bloqueia merge
  -> MÉDIO = gera issue, requer ack manual
```

#### Compliance Check
```
POST /projects/{id}/compliance/{item_id}/validate
  -> require_action("code:write")
  -> LLM valida contra checklist ISO 27001 + LGPD
  -> Verifica:
     - Dados sensíveis em dados pessoais do LGPD?
     - Criptografia em trânsito (TLS 1.2+)?
     - Criptografia em repouso (AES-256)?
     - Hashing seguro (bcrypt 12+ rounds para senhas)?
     - Logs de auditoria para ações sensíveis?
     - Retenção de dados conforme política?
     - Acesso baseado em papéis (RBAC)?
  -> Retorna:
     {
       "status": "PASS | FAIL",
       "issues": [
         {"rule": "ISO_27001_A.10.1.1", "issue": "Criptografia de senhas insuficiente", "remediation": "Usar bcrypt 12+"}
       ]
     }
  -> FALHA = bloqueia merge, gera issue
```

#### QA Approval
```
POST /projects/{id}/qa/{item_id}/approve
Body: { approved: bool, notes?: string, rejection_reason?: string }
  -> require_action("qa:approve")
  -> QA faz review manual contra specs
  -> Pode aprovar ou rejeitar
  -> Se rejeitar: item volta a "Bloqueado" com motivo
  -> Audit log: quem aprovou, quando, notas
  -> Se aprovado, libera para commit
```

#### Commit
```
POST /projects/{project_id}/git/commit
Body: { file_path: str, content: str, message: str }
  -> require_action("code:write")
  -> Verifica que todos os gates passaram (tests, security, compliance, qa)
  -> GitService.commit_file() via GitHub API
  -> Commit message: "feat(modulo): description [QA_APPROVED] [SEC_PASS] [COMPLIANCE_PASS]"
  -> Audit log com role_used + commit_sha
  -> Muda item para "Commitado"
```

#### Audit Log
```
GET /projects/{project_id}/audit/code-generation
  -> Lista completa de todas as ações, todas as fases
  -> Cada linha: user_id + role + phase + action + result + timestamp + commit_sha
  -> Filtros: por usuário, por papel, por item, por fase, por data
  -> Exportável para compliance
```

---

## 5. Backlog Inteligente com Verificação de Artefatos

### Geração

Após Ingestão + Gatekeeper + Arguidor, o sistema gera backlog de módulos/tarefas baseado em:
- Documentos de requisitos ingeridos (negociais, técnicos)
- Stack definida no OCG
- Arquitetura recomendada pelo Arguidor
- Compliance ISO 27001

### Estrutura de cada item

| Campo | Descrição |
|-------|-----------|
| modulo | Nome do módulo/componente |
| tipo | service, controller, model, middleware, test, migration, ui_screen, ui_flow |
| prioridade | Crítico / Alto / Médio / Baixo (baseado em dependências) |
| requisitos_vinculados | Quais documentos fundamentam este item |
| artefatos_necessarios | O que precisa existir (spec de tela, ERD, regras de negócio) |
| artefatos_presentes | O que já foi ingerido/aprovado |
| status | Bloqueado / Pronto / Em Geração / Gerado / Testes Executando / Análise de Segurança / Validação de Compliance / Aguardando QA / Pronto para Merge / Commitado / Publicado |
| compliance_iso27001 | Checklist ISO 27001 aplicável ao módulo |
| avisos | Informações sobre artefatos faltantes ou ferramentas não configuradas |

### Ciclo de vida do status

```
Bloqueado
  ├─ Artefatos faltando → fica bloqueado
  └─ Artefatos completados → muda para Pronto

Pronto
  └─ GP clica "Gerar Código" → muda para Em Geração

Em Geração
  └─ CodeGen + TestGen completo → muda para Testes Executando

Testes Executando
  ├─ Falha → volta para Em Geração (feedback ao LLM)
  └─ Passa → muda para Análise de Segurança

Análise de Segurança
  ├─ Vulnerabilidades críticas → bloqueia, gera issue
  └─ Sem críticas → muda para Validação de Compliance

Validação de Compliance
  ├─ Falha compliance → bloqueia, gera issue
  └─ Passa → muda para Aguardando QA

Aguardando QA
  ├─ QA rejeita → volta para Bloqueado + motivo
  └─ QA aprova → muda para Pronto para Merge

Pronto para Merge
  └─ GP commit final → muda para Commitado

Commitado
  └─ Merged to main branch → muda para Publicado
```

### Verificação de artefatos (IA)

Antes de marcar item como "Pronto", verifica:
- Documentos de requisito vinculados ingeridos?
- Definição de telas existe (se módulo frontend)?
- Regras de negócio documentadas?
- Regulamentações aplicáveis mapeadas?
- Critérios ISO 27001 relevantes identificados?

Se falta artefato crítico → item "Bloqueado" com mensagem específica.

### Endpoints

```
POST /projects/{project_id}/backlog/generate
-> IA analisa documentos + stack + OCG -> gera backlog
-> Verifica artefatos de cada item
-> Retorna backlog com status por item

GET /projects/{project_id}/backlog
-> Lista itens com status e artefatos faltantes
-> Filtrar por status, prioridade, tipo
-> Retorna trilha de cada item (pipeline status)

PATCH /projects/{project_id}/backlog/{item_id}
-> Atualizar prioridade, vincular artefatos manualmente
-> Mover item para status diferente (com validações)
```

---

## 6. Integração com Ferramentas de Design

### Chaves de ferramentas externas

Na aba Settings, além de LLM, o GP pode configurar:

| Ferramenta | Chave | Uso |
|-----------|-------|-----|
| Figma | API token | Gerar telas a partir de specs de UI |
| Semgrep | API token | SAST - análise de segurança |
| SonarQube | API token | Análise de código estática |
| Outras futuras | Token | Extensível por config |

Armazenadas no Vault por projeto, mesmo padrão das chaves LLM.

### Itens de backlog tipo "design"

| Tipo | Exemplo | Ferramenta | Artefato necessário |
|------|---------|-----------|-------------------|
| ui_screen | Tela de Login | Figma (se disponível) | Spec de tela |
| ui_flow | Fluxo de Onboarding | Figma (se disponível) | Fluxo de dados |

### Sem ferramenta de design configurada

- Item NÃO fica bloqueado
- Aviso: "Sem ferramenta de design configurada. Documentação detalhada de telas (wireframes, layout, componentes) será necessária para geração de código frontend."
- OCG verifica se documentação ingerida tem especificação suficiente
- Se documentação insuficiente → OCG contrai (confidence cai) e aponta gaps

### Com ferramenta de design configurada

- OCG reconhece ferramenta disponível → exige menos documentação de layout
- Geração automática complementa artefatos faltantes

### OCG como verificador central

- Após cada ingestão, OCG reavalia completude do backlog
- Aponta gaps: "Módulo UserDashboard tem requisitos de negócio mas falta definição visual"
- Score de confidence reflete completude dos artefatos

---

## 7. Orquestração do Pipeline com n8n

O pipeline completo de CodeGen → Tests → Security → Compliance → QA pode ser orquestrado automaticamente via **n8n**:

### Workflow n8n

```
Trigger: Item muda status para "Pronto"
  ↓
[1] Webhook: POST /projects/{id}/backlog/{item_id}/generate-code
    ├─ Chama Anthropic API (CodeGen)
    └─ Salva código em memória
  ↓
[2] Webhook: POST /projects/{id}/backlog/{item_id}/generate-tests
    ├─ Chama Anthropic API (TestGen)
    └─ Salva testes em memória
  ↓
[3] HTTP POST: GitHub API
    ├─ Cria branch temporária
    ├─ Commit código + testes
    └─ Dispara GitHub Actions (CI/CD)
  ↓
[4] Wait for: GitHub Actions completa
    ├─ Polls status a cada 5 segundos
    ├─ Se teste falha → volta ao [1] com feedback
    └─ Se passa → continua
  ↓
[5] HTTP POST: Semgrep API (SAST)
    ├─ Scan de vulnerabilidades
    └─ Retorna resultado
  ↓
[6] HTTP POST: Anthropic API (Compliance Check)
    ├─ LLM valida ISO 27001 + LGPD
    └─ Retorna status
  ↓
[7] HTTP POST: Discord/Slack
    ├─ Notifica QA: "Código pronto para review em [branch]"
    └─ Link para PR
  ↓
[8] Wait for: QA approval (manual trigger ou webhook)
    ├─ Se aprovado → continua
    └─ Se rejeitado → fecha branch, muda status
  ↓
[9] HTTP POST: GitHub API (Merge)
    ├─ Merge branch para main
    ├─ Deleta branch temporária
    └─ Tag de release se necessário
  ↓
[10] HTTP POST: Audit Log
     └─ Registra toda a trajetória: user, roles, fases, timestamps, commit_sha
```

### Configuração n8n

**Nodes necessários:**
- HTTP Request (Anthropic, GitHub, Semgrep APIs)
- Wait for Webhook (QA approval)
- Set (transformar dados entre chamadas)
- Switch (decisões: PASS/FAIL)
- Merge (consolidar resultados)
- Slack/Discord Notification

**Variáveis de ambiente:**
```
ANTHROPIC_API_KEY=sk-...
GITHUB_TOKEN=ghp_...
SEMGREP_API_KEY=...
QA_WEBHOOK_URL=https://n8n.mockn8n.com/webhook/qa-approval
```

---

## 8. Exemplo: Fluxo Completo de um Item

**Cenário:** GP com papéis `["gp", "dev_senior", "qa"]` seleciona item "UserAuthService" no backlog.

**Etapa 1: Status = Pronto**
```json
{
  "item_id": "auth-service-001",
  "modulo": "UserAuthService",
  "status": "Pronto",
  "artefatos_presentes": [
    "spec_auth_flow.md",
    "user_model_erd.sql",
    "compliance_gdpr_checklist.md"
  ]
}
```

**Etapa 2: GP clica "Gerar Código"**
- Endpoint: `POST /projects/proj-123/backlog/auth-service-001/generate-code`
- Resposta: Código gerado em editor (await review)

**Etapa 3: LLM gera testes**
- Endpoint: `POST /projects/proj-123/backlog/auth-service-001/generate-tests`
- Resposta: `auth_service_test.py` com 25 testes, cobertura projetada 85%

**Etapa 4: GitHub Actions executa testes**
```
✓ 25/25 tests passed
✓ Coverage: 85.2%
✓ All assertions green
```

**Etapa 5: Semgrep scans segurança**
```
✓ No critical vulns
⚠ 1 medium: password reset token expiry (can be fixed)
✓ No hardcoded secrets
```

**Etapa 6: LLM valida compliance**
```
✓ Dados de usuário (PII): criptografados em repouso + TLS 1.3 em trânsito
✓ Logs de login: registrados, retenção 90 dias conforme LGPD
✓ Reset de senha: token expiry 1h, bcrypt 12+ rounds
✓ Acesso: RBAC com papéis granulares
✓ Auditoria: mudanças de permissão logadas
```

**Etapa 7: QA approval**
- Notificação: Slack → "Código pronto em branch `feature/user-auth` | [Review]"
- QA: Testa fluxo login/logout/password-reset manualmente
- QA: Aprova via `POST /projects/proj-123/qa/auth-service-001/approve`
- Status: "Pronto para Merge"

**Etapa 8: GP final commit**
- Clica "Commit ao Repositório"
- Merge `feature/user-auth` → `main`
- Tag: `v2.5.0-auth-service`
- Audit log registra: `user=luiz, role=dev_senior, phase=commit, commit_sha=abc123..., timestamp=2026-04-10T14:32:00Z`

---

## 9. Audit Log - Formato Completo

```json
{
  "entry_id": "audit-20260410-auth-service-001",
  "project_id": "proj-123",
  "item_id": "auth-service-001",
  "user_id": "luiz@agilize.com",
  "roles": ["gp", "dev_senior", "qa"],
  "role_used": "dev_senior",
  "phases": [
    {
      "phase": "code_generation",
      "status": "COMPLETED",
      "timestamp": "2026-04-10T13:00:00Z",
      "duration_seconds": 45,
      "context": {
        "model": "claude-sonnet-4",
        "tokens_used": 4200,
        "prompt_version": "v2.1"
      }
    },
    {
      "phase": "test_generation",
      "status": "COMPLETED",
      "timestamp": "2026-04-10T13:01:30Z",
      "duration_seconds": 35,
      "context": {
        "tests_generated": 25,
        "coverage_projected": 85.2
      }
    },
    {
      "phase": "test_execution",
      "status": "COMPLETED",
      "timestamp": "2026-04-10T13:02:15Z",
      "duration_seconds": 24,
      "context": {
        "tests_passed": 25,
        "tests_failed": 0,
        "coverage_actual": 85.2,
        "ci_system": "github_actions"
      }
    },
    {
      "phase": "security_review",
      "status": "COMPLETED_WITH_WARNINGS",
      "timestamp": "2026-04-10T13:03:00Z",
      "duration_seconds": 18,
      "context": {
        "critical_vulns": 0,
        "medium_vulns": 1,
        "issues": [
          {
            "type": "token_expiry",
            "severity": "MEDIUM",
            "description": "Password reset token should expire in < 1h",
            "remediation": "Set token TTL = 3600 seconds"
          }
        ],
        "scanner": "semgrep"
      }
    },
    {
      "phase": "compliance_check",
      "status": "COMPLETED",
      "timestamp": "2026-04-10T13:04:00Z",
      "duration_seconds": 22,
      "context": {
        "iso27001_checks_passed": 12,
        "iso27001_checks_failed": 0,
        "lgpd_compliant": true,
        "issues": []
      }
    },
    {
      "phase": "qa_approval",
      "status": "APPROVED",
      "timestamp": "2026-04-10T13:45:00Z",
      "approved_by": "qa-team@agilize.com",
      "approved_by_role": "qa",
      "notes": "Login flow tested manually. Password reset verified. 2FA not in scope for this item."
    },
    {
      "phase": "commit",
      "status": "COMPLETED",
      "timestamp": "2026-04-10T14:00:00Z",
      "commit_sha": "a1b2c3d4e5f6g7h8...",
      "commit_message": "feat(auth): UserAuthService with bcrypt, 2FA support, LGPD compliant [SEC_PASS] [COMPLIANCE_PASS] [QA_APPROVED]",
      "branch": "main",
      "merged_by": "luiz@agilize.com"
    }
  ],
  "total_duration_minutes": 4.25,
  "result": "SUCCESS",
  "conclusion": "Item deployable to production"
}
```

---

## 10. Permissões por Papel (Matriz de Ações)

| Ação | GP | Tech Lead | Dev Senior | Dev Pleno | QA | Compliance | Stakeholder |
|------|----|-----------|-----------|-----------|----|------------|-------------|
| project:view | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| project:edit | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ |
| project:manage_team | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| code:write | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| code:review | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| pipeline:execute | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| security:review | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ |
| compliance:validate | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| qa:approve | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| git:commit | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| backlog:manage | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ |
| audit:view | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ |
| audit:export | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |

---

## 11. Considerações de Segurança e Compliance

### ISO 27001 - Controles Implementados

**A.10.1.1 - Política de controle de acesso**
- Papéis granulares com matriz de permissões
- Audit log em todas as ações

**A.12.4 - Logging e monitoramento**
- Cada fase do pipeline registrada com timestamps
- Acesso a segredos via Vault (nunca em logs)

**A.13.1 - Criptografia**
- Tráfego TLS 1.2+
- Senhas com bcrypt 12+ rounds (validado por compliance check)
- Dados sensíveis criptografados em repouso

**A.14.1 - Gestão de vulnerabilidades**
- SAST automático em cada código
- Dependency scanning obrigatório
- Secrets scanning em toda ingestão

### LGPD - Conformidade

- Dados pessoais (PII) identificados e marcados
- Retenção conforme política (default 90 dias para logs)
- Direito ao esquecimento (Delete flag + purge job)
- Criptografia de dados pessoais

---

## 12. Próximos Passos

1. **Implementar tabela `ProjectMemberRole`** no banco de dados
2. **Expandir `permissions.py`** com função `get_actions_for_roles()`
3. **Criar endpoints** de CodeGen → TestGen → Security → Compliance → QA
4. **Configurar n8n** para orquestração automática
5. **Integrar Semgrep, SonarQube, npm audit** via APIs
6. **Treinar LLM** com exemplos de código + testes + compliance checks
7. **Construir dashboard** de audit log para fins de compliance
8. **Documentar playbook** de remediação de vulnerabilidades

---

**Documento preparado por:** Luiz Carlos Pielak  
**Última atualização:** 2026-04-10  
**Versão:** 2.0
