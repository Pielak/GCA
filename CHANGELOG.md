# Changelog

All notable changes to GCA will be documented in this file.

## [Unreleased — MVP 2 em andamento] - 2026-04-17

### Dogfood dia inteiro — 20+ DTs quitadas

**Saneamento de compartimentalização (Critical)**
- DT-026: repositório Git compartilhado entre 2 projetos era aceito pelo
  backend. Agora `connect_repository` rejeita com 400 normalizando URL
  (.git/trailing-slash/case/git@ vs https://). `git/status` retorna
  `shared_with: [...]` pro frontend mostrar banner de conflito quando
  pré-existente.

**Saneamento de findings falsos (Critical)**
- DT-024: `Q17 multi-select` causava `TypeError: unhashable type: 'list'`
  em `_check_arch_execution_compat`. Questionários ficavam zumbis em
  `pending_analysis`. Fix renomeia `exec_model` → `exec_models` (list)
  em 6 pontos de uso.
- DT-025: 13 strings hardcoded no `TechnologyVerificationService`
  descasavam com o schema real do PDF ("Criptografia em trânsito" quando
  schema tem "HTTPS", "Plano de testes" vs "Plano testes", etc).
  Resultado: bloqueadores falsos em respostas corretas. Todos alinhados
  e sugestões ("Marque 'X' em QY") citando opção exata.

**UX do questionário (DT-018/020/021/022)**
- DT-018: PDF flattened (sem AcroForm) agora rejeita com 422 orientando
  o GP a usar Adobe Reader/Foxit/Okular em vez do caminho silencioso.
- DT-022: aba Ingestão humaniza erro do Arguidor — `arguider_error_message`
  exposto na listagem com mapa 401/403/429/timeout.
- Editor inline: GP pode corrigir as perguntas bloqueadoras diretamente
  na tela (sem baixar PDF), via novo endpoint `POST /questionnaire/correct`
  que mergeia corrections com responses e re-roda análise.
- Schema Q→label espelhado no frontend em `data/questionSchema.ts`.

**Multi-provider LLM por projeto (novo)**
- Projeto suporta múltiplos provedores simultâneos, um marcado como
  padrão, com Testar/Padrão/Remover por card. Retrocompat on-read do
  formato antigo (`provider`/`model_preference`).
- Endpoints: `POST /settings/llm`, `DELETE .../providers/{p}`,
  `POST .../providers/{p}/default`, `POST .../validate?provider=X`
  (persiste `last_validated_at` e `last_validation_ok`).
- Validate ganhou suporte real a DeepSeek, Grok, Gemini (antes retornava
  `valid: True` falso-positivo). Ollama fica como DT-023 (requer schema
  de `base_url`).
- `agent_service` usa `DEFAULT_AI_MODEL` como fallback quando
  `{PROVIDER}_MODEL` específico não está setado (consistente com
  `ocg_updater_service`).

**Infra de UX (DT-017/hero/badges/DT-026 banner)**
- `/novo-projeto` redireciona para `/solicitar-projeto` (um caminho só).
- Hero âmbar em Configurações quando setup incompleto, desaparece quando
  3/3 passos concluídos + approved. Badges ✓/⚠/○ nas tabs distinguem
  "pendente" de "submetido-com-bloqueadores".
- OCG Scores por Pilar mostra nome + descrição + peso (P1 Caso de
  Negócio, P7 Segurança, etc) em vez de só "P1..P7".

**Operacional / saneamento de dados**
- DT-019: 18 admins fake (`@test.com`/`@example.com`) desativados no DB;
  16 projetos factory + 2 questionários 80% removidos. Guard RFC 2606
  + `test.com` no `EmailService` previne novos vazamentos.
- SMTP por projeto fica como DT-016 aberta, escopo MVP 5 (hardening).

**Regra de deploy (CLAUDE.md §12)**
- Frontend é `vite preview` estático — toda mudança em `frontend/**`
  exige `npm run build` + `docker restart gca-frontend` antes de pedir
  hard refresh ao user. Regra agora documentada.

### OCGs gerados (dogfood validado)
- Smoke MVP2 17abr: `9604b9f6`, score 60.9, status NEEDS_REVIEW.
- Automação Jurídica Assistida: `89b0ec95`, NEEDS_REVIEW.
- FinanceHub Pro (projeto mock): **removido** do DB por solicitação do
  owner — não tinha entregáveis reais, apenas deliverables de teste do
  dia 2026-04-09.

### Testes
- Multi-provider validate testado contra 5 provedores do admin (4
  válidos, DeepSeek do admin inválido — projeto usa chave separada).
- Reprocessamento dos 3 questionários zumbis confirmou que DT-024 +
  DT-025 eram causa 100% dos bloqueadores falsos.

---

## [MVP 1 saneamento] - 2026-04-17

### Governança documental
- Contrato canônico soberano (`GCA_CANONICAL_CONTRACT.md` v1.1) e tracker
  (`GCA_MVP_PROGRESS.md` v1.1) em vigor. Precedência documental formalizada.
- `CLAUDE.md` reescrito em 16 seções (fonte soberana, RBAC canônico, política
  híbrida de IA, debt gates, regras de contenção).
- README, ARQUITETURA e docs históricas marcadas explicitamente como
  não-contrato quando contêm visão futura.

### RBAC (DT-001 + DT-002 quitadas)
- **Breaking:** `ROLE_ACTIONS` reduzido aos 5 papéis canônicos do contrato §4:
  Admin, GP, Dev, Tester, QA (+ `admin_viewer` virtual). Removidos
  `tech_lead`, `dev_senior`, `dev_pleno`, `compliance`, `stakeholder`,
  `viewer` — DB não continha nenhum, sem migration de dados.
- GP perdeu `code:write/code:review/pipeline:execute/git:commit` (contrato
  §4.1 — GP não escreve código).
- QA ganhou `security:review` e `compliance:validate`.
- Frontend alinhado: `Sidebar`, `AdminUsersPage`, `AdminProjectViewPage`,
  `ProjectDashPage`, `ProjectListPage`, `ProjectTeamPage`,
  `RoleAssumptionPrompt`, `StatusBadge` operam apenas com os 5 canônicos.

### Governança de IA (DT-005 + DT-009 quitadas)
- `ai_key_resolver.py` com docstring de política de criticidade
  (baixa/média/alta conforme contrato §6.2).
- `agent_service.py` (camada GCA/pipeline OCG) deixa de fazer fallback
  silencioso para `ANTHROPIC_API_KEY` quando o admin escolheu outro provider
  sem a chave correspondente — `_ensure_key()` levanta `RuntimeError` claro.
- Implementação do roteamento híbrido efetivo (classificar tarefa → escolher
  provedor) permanece como escopo do MVP 3.

### Testes
- 81/81 backend integration + 44/44 unit passando ao fim desta sessão.

---

## [0.1.0-beta] - 2026-04-05

### Added

#### Backend (FastAPI)
- 13 admin endpoints (users, projects, tickets, alerts, integrations)
- JWT authentication with role-based access control
- Async PostgreSQL ORM with SQLAlchemy 2.0
- Redis caching layer
- SMTP email notifications
- Webhook testing (Teams, Slack, Discord)
- Suspicious access tracking with brute-force protection
- Support tickets with response system
- System alerts with severity levels
- Dashboard metrics endpoint
- OpenAPI/Swagger documentation

#### Frontend (React)
- 9 admin pages (Dashboard, Users, Projects, Security, Settings, Tickets, Integrations, Alerts)
- 12 reusable components (Button, Modal, Table, Badge, Card, Toast, etc)
- 10 custom hooks (useAuth, useUsers, useProjects, useTickets, etc)
- Zustand state management
- React Query data fetching & caching
- React Hook Form + Zod validation
- Error Boundary for error handling
- Protected routes with JWT validation
- Dark theme (Tailwind CSS)
- Mobile-responsive design
- Production build (297KB gzipped)

#### Infrastructure
- Docker Compose setup (4 services)
- Cloudflare Tunnel integration
- GitHub integration
- Database migrations
- Automated backups
- Health checks
- Comprehensive documentation (README, API, Architecture, Deployment, Setup)
- Production deployment configuration

#### Testing
- 12/28 backend service layer tests passing
- Test factories for database seeding
- Async test fixtures

### Changed
- Recovered 139GB NVMe space via data migration to SSD
- Optimized frontend bundle size (297KB gzipped)
- Async database operations for better performance

### Security
- bcrypt password hashing
- JWT token authentication
- CORS protection
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (React sanitization)
- RBAC (admin/user roles)

### Known Limitations
- Endpoint HTTP tests need pytest-asyncio configuration (foundation set)
- No refresh token mechanism (session dies on token expiry)
- No real-time updates (WebSocket support needed)
- No bulk operations

### Future (v0.2.0+)
- Refresh token mechanism
- WebSocket real-time updates
- Bulk user operations
- Advanced filtering (date range, text search)
- Full HTTP endpoint test coverage
- Performance monitoring dashboard

---

## [0.0.1] - 2026-03-20

Initial project setup with basic models and CLI.
