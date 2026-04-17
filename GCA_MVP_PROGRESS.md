# GCA_MVP_PROGRESS.md

Versão: 1.2  
Data-base: 2026-04-17  
Status: **controle de avanço por fase**

---

## 1. Fase atual

### MVP ativo
**MVP 2 — Contexto vivo e governança de conteúdo** (iniciado 2026-04-17)

### MVP anterior
MVP 1 — Base operacional e saneamento do núcleo — **ENCERRADO 2026-04-17**
com todos os 5 Criticals quitados (ver §4). Gate do MVP 1 permaneceu aberto;
nenhuma regressão observada até a abertura desta fase.

### Objetivo do momento
Ativar o fluxo de contexto vivo: ingestão de documentos, quarentena de PII,
OCG versionado com deltas, backlog derivado do OCG, Arguidor, reavaliação do
Gatekeeper após ingestão. Mantém o rigor do MVP 1: sem expansão além do
escopo da fase; correção local preferível a refatoração sistêmica.

### Princípio desta fase
Mesma do MVP 1:
1. diagnosticar;
2. classificar dívida;
3. corrigir blockers e criticals antes de feature nova;
4. revalidar após cada passo;
5. só então considerar avanço para o MVP 3.

---

## 2. Escopo da fase atual

### Em escopo agora (contrato §7, MVP 2)
- ingestão de documentos;
- quarentena de PII;
- OCG versionado com deltas;
- backlog derivado do OCG;
- Arguidor;
- consolidação de findings;
- reavaliação do Gatekeeper após ingestão;
- extensão da governança de IA para as camadas tocadas (Arguidor, Ingestão):
  remover hardcodes residuais herdados do MVP 1 e aplicar a política de
  criticidade (contrato §6.2).

### Fora de escopo agora
- expansão automática para features de entrega final;
- Release Bundle;
- Documentação Viva completa;
- CodeGen controlado (MVP 3);
- QA Readiness completo (MVP 4);
- hardening operacional avançado (MVP 5);
- automações além do necessário para estabilizar contexto.

---

## 3. Dívida aberta conhecida

### 3.1 Blocker / Critical

#### Abertas (MVP 2)

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-012 | Critical | Governança de IA (Arguidor) | `arguider_service.py:174` faz fallback silencioso a `settings.ANTHROPIC_API_KEY` quando o projeto não tem chave configurada. Contradiz contrato §6.4 (nunca misturar chave global com projeto). | Auditoria MVP 2 | **Quitada 2026-04-17** — ver §4 |
| DT-013 | Critical | Governança de IA (Ingestão) | `ingestion_service.py:288` resolve chave com `provider="anthropic"` hardcoded. Ignora o provedor escolhido pelo GP. | Auditoria MVP 2 | **Quitada 2026-04-17** — ver §4 |
| DT-015 | Major | UX/Ingestão | PDF preenchido do questionário é sempre quarentenado pelo detector de PII (respostas têm email/CPF/telefone de stakeholders). Caminho oficial de alimentar o OCG fica bloqueado na abertura do projeto. Descoberto no smoke E2E do MVP 2 em 2026-04-17. | Smoke E2E MVP 2 | **Quitada 2026-04-17** — commit `8fc52fc`: estratégia B unificada. PDF vira transporte de respostas (não documento), delega a `QuestionnaireService.submit_questionnaire` → pipeline 8 agentes IA → hooks de consistência. Detector de PII não é acionado no caminho oficial. QuestionnairePage reescrita PDF-only (-20KB no bundle). |

#### Herdadas (MVP 1, já quitadas — mantidas para rastreabilidade)

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-001 | Critical | RBAC | Conflito entre documentação histórica com 7 papéis e contrato canônico com 5 papéis. | Docs históricos vs contrato | **Quitada 2026-04-17** — ver §4 |
| DT-002 | Critical | UI/Admin | Aba de usuários/admin modelada com RBAC global ampliado. | Análise completa | **Quitada 2026-04-17** — ver §4 |
| DT-003 | Critical | Contrato de produto | Textos que sugerem plataforma ampla pronta conflitavam com recorte real. | Docs / README / manual | **Quitada 2026-04-17** — ver §4 |
| DT-004 | Critical | Segurança operacional | PAT de Git com fallback plaintext em `decrypt_pat`. | Tutorial / requisitos / roadmap | **Quitada 2026-04-17** — ver §4 |
| DT-005 | Critical | Governança de IA | Falta regra canônica para seleção de provedor/modelo por objetivo. | Requisitos / contrato | **Quitada 2026-04-17** — ver §4 |

### 3.2 Major

#### Abertas

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-006 | Major | Fases vs realidade | Materiais descrevendo pipeline completo como se estivessem igualmente maduros. | Manual / tutorial / análise | Aberto |
| DT-007 | Major | Placeholders / continuidade | Placeholders de telas/módulos previstos não promovidos automaticamente a entregas. | TASK_GCA_MASTER | Aberto |
| DT-008 | Major | Consistência documental | Discrepâncias entre documentos sobre readiness, testes e maturidade. | Changelog / docs / task | Aberto |
| DT-014 | Major | Governança de IA (OCG Updater) | `ocg_updater_service.py:250, 413` usa `settings.DEFAULT_AI_PROVIDER` como fallback sem aplicar a política de criticidade (§6.2). OCG updates dependem de decisões críticas. | Auditoria MVP 2 | **Quitada 2026-04-17** — ver §4 |
| DT-016 | Major | Compartimentalização operacional (SMTP) | GCA hoje envia todos os emails (convites, notificações, aprovações) via SMTP global do admin. Sem isolamento por projeto/cliente: identidade do remetente é misturada, compliance LGPD fica exposto. Paralelo ao §6.6 do contrato (IA compartimentalizada por projeto) — mesma lógica aplica a SMTP. | Decisão arquitetural 2026-04-17 | **Aberto — escopo MVP 5 (Hardening)**. Não implementar antes de MVP 5 por: não é blocker do gate MVP 2/3, requer refactor do EmailService, pode afetar caminhos hoje estáveis. |
| DT-017 | Major | UX/Continuidade | `NovoProjetoPage` (rota `/novo-projeto`, linkada do LoginPage) ainda expõe form de 49 perguntas que posta em `POST /questionnaires/`. Contradiz a diretiva "um caminho só" aplicada em 2026-04-17 (DT-015 quitada). Enquanto `/solicitar-projeto` (SolicitarProjetoPage) já segue o fluxo correto (wizard curto + aprovação + PDF dentro do projeto), `/novo-projeto` continua expondo o caminho antigo e confunde a experiência. | Decisão 2026-04-17 | **Quitada 2026-04-17** — ver §4. |
| DT-019 | Major | Operacional / SMTP | 18 usuários admin com emails `@test.com`/`@example.com` ficaram persistidos no DB de produção por suítes de teste (factories `codegen_*`/`regen_*`) rodadas antes do fix `8fe9679`. O filtro `_notify_admins_questionnaire_submitted` inclui todos admins ativos — cada submissão real de questionário disparava 18+ SMTP para destinatários inexistentes. O "From:" configurado (pielak.ctba@gmail.com) recebia bounces. Quebra efetiva de `feedback_no_unauthorized_data` (lixo persistido) + da política de compartimentalização do contrato §6.6, que DT-016 vai endereçar estruturalmente no MVP 5. | Dogfood MVP 2 2026-04-17 | **Quitada 2026-04-17** — ver §4. |
| DT-018 | Major | UX / Questionário PDF | `POST /questionnaire/upload-pdf` aceitava silenciosamente PDF sem AcroForm (flattened pelo leitor do GP — Chrome "Salvar como PDF", algumas versões de Evince/Preview). Caía no `text_fallback` que lê texto visível mas não enxerga estado de checkbox — Q40/Q41/Q43 (multi-select) saíam vazios, validator pré-OCG rejeitava com COMP-008 + SEC-004, e o GP via "Status: Incompleto" sem entender que o problema era o PDF, não as respostas que preencheu. | Smoke E2E MVP 2 2026-04-17 | **Quitada 2026-04-17** — ver §4. |
| DT-022 | Major | UX / Ingestão | Aba Ingestão mostrava apenas "❌ Erro" quando `arguider_status='error'` sem nenhuma pista do motivo. O `arguider_error_message` existia no DB e no endpoint `/ingestion/:id` de detalhe, mas não aparecia na listagem nem era humanizado. O GP ficava sem saber se era chave inválida, rate limit, rede, etc. Descoberto no dogfood quando provider deepseek foi configurado mas o Arguidor hardcoda `AsyncAnthropic` (resíduo MVP 3, multi-provider adapter) — retornava 401 Anthropic sem feedback útil. | Dogfood MVP 2 2026-04-17 | **Quitada 2026-04-17** — ver §4. |
| DT-020 | Major | UX / Questionário | Após submeter PDF via aba Questionário, não há trace visual do arquivo recebido — GP vê só o status da análise ("Incompleto 80%"), não filename, tamanho ou hash. Isso gera confusão ("onde foi parar meu arquivo?") e levou o user a tentar re-upload via aba Ingestão, disparando o caminho errado (ver DT-021). Requer migration de schema para `questionnaires` adicionando `uploaded_filename`, `file_hash`, `file_size_bytes`, `answered_questions`. Escopo pequeno mas envolve DB — trato em commit separado, não no saneamento operacional 2026-04-17. | Dogfood MVP 2 2026-04-17 | Aberto |
| DT-021 | Major | UX / Ingestão | Aba Ingestão aceita qualquer PDF — inclusive o PDF do questionário preenchido, que tem caminho próprio (aba Questionário, DT-015). O user fez upload manual na Ingestão achando que era o fluxo, documento foi para `ingested_documents`, Arguidor tentou analisar e falhou com 401 (ver DT-022). Propostas de correção: (a) backend detecta se PDF é o Questionario_GCA_*.pdf gerado pelo sistema (check de filename + AcroForm de questionário) e retorna 409 com "Use a aba Questionário"; (b) frontend mostra aviso antes de upload se filename combina com template de questionário. Nenhuma opção requer mudança arquitetural — correção localizada. | Dogfood MVP 2 2026-04-17 | Aberto |

#### Herdadas (MVP 1, já quitadas)

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-009 | Major | Roteamento híbrido | Política definida; implementação do roteador em código fica para MVP 3. | Contrato / operação | **Quitada 2026-04-17** (política) — ver §4 |

### 3.3 Minor

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-010 | Minor | Terminologia | Uso inconsistente de termos como tenant, projeto, instância e cliente. | Docs históricos | Aberto |
| DT-011 | Minor | Narrativa de produto | Parte da documentação promocional está mais madura que o contrato técnico real. | README / manual | Aberto |

---

## 4. Dívida quitada

| ID | Data | Item quitado | Arquivos/módulos | Evidência |
|---|---|---|---|---|
| DT-001 | 2026-04-17 | RBAC reduzido aos 5 papéis canônicos no backend: `admin_viewer` (virtual) + `gp` + `dev` + `tester` + `qa`. Papéis históricos (tech_lead, dev_senior, dev_pleno, compliance, stakeholder, viewer) removidos. GP perdeu `code:write/review/execute/commit` (contrato §4.1 — GP não escreve código); QA ganhou `security:review` e `compliance:validate`. Comentários dos campos `role` em `models/base.py` atualizados. | `backend/app/core/permissions.py`, `backend/app/models/base.py`, `backend/tests/test_permissions.py`, `backend/tests/test_rbac_integration.py`, `backend/tests/test_multi_roles.py`, `backend/tests/test_project_setup.py` | 81/81 testes backend + 44/44 unit passando. DB com 3 `gp` preservados sem migration. |
| DT-002 | 2026-04-17 | Frontend alinhado ao RBAC canônico. Todos os mapas `ROLE_LABELS`/`ROLE_COLORS`/`ROLE_OPTIONS` e dropdowns de convite agora listam apenas Admin/GP/Dev/Tester/QA. `RoleAssumptionPrompt` remapeado para ações → papéis canônicos. Defaults de convite mudam de `dev_pleno` para `dev`. | `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/components/ui/StatusBadge.tsx`, `frontend/src/components/projects/RoleAssumptionPrompt.tsx`, `frontend/src/pages/admin/AdminUsersPage.tsx`, `frontend/src/pages/admin/AdminProjectViewPage.tsx`, `frontend/src/pages/projects/ProjectDashPage.tsx`, `frontend/src/pages/projects/ProjectListPage.tsx`, `frontend/src/app/pages/projects/ProjectTeamPage.tsx`, `frontend/src/pages/projects/CodeGeneratorPage.tsx` (comentário TODO) | Build frontend limpo (vite preview up). Grep `tech_lead\|dev_senior\|dev_pleno\|stakeholder\|senior_dev\|pleno_dev` no diretório `frontend/src` = 0 ocorrências. |
| DT-005 | 2026-04-17 | Política canônica de IA consolidada no escopo do MVP 1. Docstring de `ai_key_resolver.py` explicita as duas camadas (GCA/Admin vs Projeto/GP), as regras duras do contrato §6.4 e a taxonomia de criticidade (baixa/média/alta) do §6.2. `agent_service.py` (pipeline OCG — camada GCA) deixa de fazer fallback silencioso: se o admin configurou `DEFAULT_AI_PROVIDER=X` mas `X_API_KEY` está ausente, o service levanta `RuntimeError` explícito na primeira chamada a `_call_llm`, em vez de cair silenciosamente em `ANTHROPIC_API_KEY`. | `backend/app/services/ai_key_resolver.py` (docstring expandida), `backend/app/services/agent_service.py` (`__init__` sem fallback silencioso + novo `_ensure_key` chamado no início de `_call_llm`) | 81/81 + 44/44 testes passando; import da classe sem erro. |
| DT-009 (política) | 2026-04-17 | Roteamento híbrido por criticidade explicitado nos docs operacionais ativos (CLAUDE.md §6.2-6.3) e no docstring de `ai_key_resolver.py`. Baixa/Média → Ollama ou modelo barato aceitáveis; Alta → modelo premium obrigatório e sem fallback silencioso. | `GCA_CANONICAL_CONTRACT.md §6.2-6.5`, `CLAUDE.md §6.2-6.3`, `backend/app/services/ai_key_resolver.py` | Doc lido e referenciado pelo código. Pendente a implementação do roteador em si (ver nota abaixo). |
| DT-003 | 2026-04-17 | Narrativa de produto neutralizada. README reescrito apontando o status real (MVP 1 em saneamento), a precedência documental e o modelo instalável-por-cliente. Docs históricos (`ANALISE_COMPLETA_GCA.md`, `ARQUITETURA.md`, `docs/GCA_Documento_Completo.md`) receberam cabeçalho ⚠️ **"DOCUMENTO HISTÓRICO — NÃO É CONTRATO DE IMPLEMENTAÇÃO"** com referência ao contrato canônico. CHANGELOG tem entrada nova cobrindo a sessão de saneamento. | `README.md`, `CHANGELOG.md`, `ARQUITETURA.md`, `ANALISE_COMPLETA_GCA.md`, `docs/GCA_Documento_Completo.md` | Grep por "Production Ready" no README = 0 ocorrências. Cada doc histórico abre com aviso claro de não-contrato. |
| DT-004 | 2026-04-17 | PAT plaintext eliminado do fluxo de crypto. `decrypt_pat` removeu o fallback silencioso que devolvia plaintext quando o valor armazenado não era Fernet. Agora levanta `PatNotEncryptedError` explícito. Introduzida exceção dedicada `PatNotEncryptedError` em `crypto.py`. Docstring do módulo reescrita sem menção a "backward-compat plaintext". Teste `test_decrypt_passes_through_legacy_plaintext` reescrito para garantir que plaintext agora **falha**. | `backend/app/core/crypto.py`, `backend/app/tests/test_crypto.py` | 10/10 crypto + 44/44 unit + 81/81 integration passando. DB inspecionado: 2/2 `pat_encrypted` já em Fernet (`gAAAAAB…`, 140 chars); decrypt OK nos 2 projetos reais. Sem migration de dados necessária. |
| DT-013 | 2026-04-17 | `ingestion_service.py:288` deixou de hardcodar `provider="anthropic"`. Agora chama `AIKeyResolver.get_project_key(db, project_id)` sem provider, que lê o provedor configurado pelo GP em `project_settings.settings_json.provider`. Se o GP não configurou, retorna `None` e o caller decide (arguider levanta erro claro). `AIKeyResolver` ganhou helper `_resolve_project_provider` + `get_project_key` reescrita sem default `"anthropic"`. | `backend/app/services/ai_key_resolver.py`, `backend/app/services/ingestion_service.py` | 44/44 unit + 81/81 integration passando; imports OK. |
| DT-012 | 2026-04-17 | `ArguiderService.__init__` não aceita mais `project_api_key=None`. Fim do fallback a `settings.ANTHROPIC_API_KEY`. Levanta `RuntimeError` explícito pedindo configuração em Settings > LLM. Docstring classifica o Arguidor como ALTA criticidade (contrato §6.2). | `backend/app/services/arguider_service.py` | 44/44 + 81/81 passando; import OK. |
| DT-014 | 2026-04-17 | `ocg_updater_service` recebeu 2 ajustes: (1) metadados de billing (provider/model) agora caem em `"unknown"` + warning quando o `llm_result` não traz, em vez de adivinhar via `DEFAULT_AI_PROVIDER` (evita atribuir custo ao provedor errado); (2) docstring de `_call_llm_for_ocg_update` classifica a operação como ALTA criticidade (contrato §6.2) e explicita que usa camada GCA (admin), não chave de projeto. | `backend/app/services/ocg_updater_service.py` | 44/44 + 81/81 passando. |
| DT-017 | 2026-04-17 | Caminho duplicado `/novo-projeto` eliminado. Rota antiga agora redireciona (`<Navigate to="/solicitar-projeto" replace />`) em vez de renderizar a página obsoleta de 49 perguntas — emails antigos e bookmarks continuam funcionando. `NovoProjetoPage.tsx` (609 linhas) e `questionnaireBlocks.ts` (dado morto após a remoção) deletados. Link residual em `LoginPage.tsx:592` (botão "Continuar" do toast pós-identificação) passa a apontar para `/solicitar-projeto`. `SolicitarProjetoPage` (wizard 2 passos + aprovação + PDF dentro do projeto) vira o único caminho externo para solicitar projeto — coerente com a diretiva "um caminho só" da DT-015. | `frontend/src/routes.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/NovoProjetoPage.tsx` (removido), `frontend/src/data/questionnaireBlocks.ts` (removido) | Grep `novo-projeto\|NovoProjetoPage\|questionnaireBlocks` em `frontend/src` = 1 ocorrência residual (a própria rota de redirect). `npx tsc --noEmit` não gera erro novo em `routes.tsx` nem `LoginPage.tsx`; 23 erros TS pré-existentes em outros arquivos permanecem inalterados. |
| DT-019 | 2026-04-17 | Três camadas de proteção/saneamento contra lixo de teste vazando para produção. (1) **Código (guard SMTP)**: `EmailService` ganhou helper `_is_non_deliverable_email(to_email)` com blocklist RFC 2606 (`.test`, `.example`, `.invalid`, `.localhost`) + domínios reservados (`example.com/org/net`, `test.com/org`, `localhost`). Guard aplicado nos 3 pontos que bypass o wrapper (`send_email`, `send_questionnaire_link_email`, `send_ocg_generated_email`) — mesmo padrão do fix `8fe9679`. Log `email.skipped_non_deliverable` registra auditoria. (2) **DB (admins fake)**: 18 admins fake (`@test.com`/`@example.com`) desativados via `UPDATE users SET is_active=false` em transação — preserva audit log, FKs intactas, reversível. O filtro `_notify_admins_questionnaire_submitted` (checa `is_admin=true AND is_active=true`) não os encontra mais. 1 admin real preservado ativo. (3) **DB (projetos/questionários fake)**: 16 projetos com padrão de factory (`slug LIKE 'p-nogit-%'` / `'p-regen-nogit-%'`, criados entre 19:06-20:40 por suítes antes de `8fe9679`) deletados em transação com CASCADE cuidando de 25 tabelas filhas. 2 questionários 80% `Incompleto` órfãos do projeto real `Smoke MVP2 17abr` também removidos. 0 OCGs órfãos. Estado final: 3 projetos reais preservados (FinanceHub Pro, Automação Jurídica Assistida, Smoke MVP2 17abr) + 4 questionários legítimos. | `backend/app/services/email_service.py`, DB `users` (UPDATE em 18 linhas), DB `projects` (DELETE em 16 linhas + CASCADE), DB `questionnaires` (DELETE em 2 linhas explícitas) | 9/9 testes manuais do guard passam: `@test.com`/`@example.com`/`@bar.test`/`@localhost` bloqueados; `@gmail.com`/`@company.com.br` liberados. `SELECT COUNT(*) FROM users WHERE is_active=true AND email LIKE '%@test.com'` = 0. `SELECT COUNT(*) FROM projects WHERE slug LIKE 'p-nogit-%' OR slug LIKE 'p-regen-nogit-%'` = 0. Zero questionários 80% Incompleto restantes. Relacionado: DT-016 (SMTP compartimentalizado, MVP 5) — fica pendente como endereçamento arquitetural; DT-019 é mitigação tática + saneamento pontual. |
| DT-018 | 2026-04-17 | `questionnaire_pdf_router.upload_questionnaire_pdf` agora faz pré-flight antes de extrair respostas: se `/AcroForm` ausente no Root do PDF (indicador de flatten), rejeita com 422 e mensagem clara orientando o GP a abrir em Adobe Reader / Foxit / Okular e salvar com Ctrl+S (não "Salvar como…" nem "Imprimir → PDF"). Evita o caminho silencioso anterior que entregava análise incompleta com blockers falsos. Log `questionnaire_pdf.flattened_rejected` registra o caso para auditoria. O `text_fallback` preexistente permanece como rede de segurança para o edge case AcroForm-presente-mas-`get_fields()`-vazio (bug raro do pypdf). | `backend/app/routers/questionnaire_pdf_router.py` | Teste manual com 2 PDFs: (a) flattened (user): `root keys=['/Type','/Pages']`, `/AcroForm in root = False` → guard rejeita; (b) fresh gerado por `generate_pdf()`: `root keys=['/AcroForm','/PageMode','/Pages','/Type']`, `/AcroForm in root = True`, 274 campos → guard deixa passar. Hot-reload via uvicorn `--reload` ativou a mudança sem restart. |
| DT-022 | 2026-04-17 | Aba Ingestão agora mostra o motivo do erro do Arguidor humanizado — não mais só "❌ Erro" opaco. Três mudanças: (1) `IngestionService.list_documents` passa a incluir `arguider_error_message` no dict retornado (antes só `get_document_detail` expunha). (2) tipo `IngestedDocument` do frontend ganha o campo. (3) `IngestionPage` renderiza linha expandida `↳ <msg>` abaixo do row quando `status=error`; função `humanizeArguiderError` mapeia padrões (401/403 → chave rejeitada, 429 → rate limit, timeout, connection) para texto acionável, mantendo a crua no `title` como fallback técnico. | `backend/app/services/ingestion_service.py`, `frontend/src/hooks/useIngestion.ts`, `frontend/src/pages/projects/IngestionPage.tsx` | Dogfood: documento `334d3f00-…` com erro real `"Error code: 401 - invalid x-api-key"` passaria a renderizar "Provedor de IA rejeitou a chave (401). Verifique em Configurações → Provedor de IA e use 'Testar conexão'" (doc deletado no mesmo saneamento por ter sido fruto de teste manual). |

### Resíduos conhecidos (fora do escopo do MVP 1; programados para MVPs posteriores)

- `arguider_service.py:174` ainda faz fallback a `settings.ANTHROPIC_API_KEY` quando projeto não tem chave. Arguidor é escopo do MVP 2.
- `module_codegen_service.py:164, 298` e `llm_service.py:73, 81` instanciam Anthropic diretamente. CodeGen controlado é escopo do MVP 3.
- `ingestion_service.py:288` hardcode `provider="anthropic"`. Ingestão profunda é escopo do MVP 2.
- `ocg_updater_service.py:250, 413` e `ai_service.py:86, 100` usam `DEFAULT_AI_PROVIDER`/`ANTHROPIC_API_KEY` em camadas compartilhadas. Saneamento deve acompanhar o refactor do MVP 2/3.
- Implementação efetiva de roteamento por criticidade (classificação de tarefa → seleção de provedor) é escopo do MVP 3 (análise de adequação do provedor ao uso pretendido no CodeGen, contrato §7).

> Regra: toda quitação relevante deve ser adicionada aqui com data, módulos afetados e evidência.

---

## 5. Gaps e conflitos que precisam ser reconhecidos pelo Claude

### 5.1 Papéis
- Backend/contrato caminham para 5 papéis canônicos.
- Manual, tutorial e análises ainda carregam 7+ papéis em vários pontos.
- Claude não pode usar esses papéis históricos para expandir o sistema.

### 5.2 Produto
- O produto canônico é instalável por cliente.
- Documentos históricos podem sugerir plataforma mais ampla ou linguagem de multi-tenant central.
- Claude deve manter o modelo: **instância por cliente + isolamento por projeto**.

### 5.3 IA
- O sistema suporta múltiplos provedores/modelos em documentação e serviços.
- Claude deve tratar a IA como componente configurável por objetivo do cliente.
- O sistema pode operar em modo híbrido:
  - tarefas auxiliares e repetitivas com modelo local/Ollama;
  - consolidação e decisão crítica com modelo premium.
- Não pode assumir um único provedor como verdade universal do produto.
- **Contexto A (IA para construir o GCA) é distinto de Contexto B (IA operacional do cliente)** — contrato §6.6, CLAUDE.md §6.5. A escolha de IA feita no desenvolvimento do produto nunca se torna dependência obrigatória do cliente final.

---

## 6. Gate de avanço

A fase atual **não pode avançar** se qualquer um destes itens estiver aberto:
- blocker aberto;
- critical aberto;
- contradição estrutural entre contrato e código do núcleo;
- RBAC ambíguo;
- teste quebrado da fase;
- alteração sem migração/compatibilidade onde ela seria obrigatória;
- feature nova adicionada para “contornar” dívida não resolvida.

### Situação atual do gate (MVP 2)
**NÃO AVANÇAR** (1 item do §10 ainda pendente — validação manual)

### Motivo
Dívida de saneamento (DT-012, DT-013, DT-014) quitada em 2026-04-17.
Features canônicas entregues em 2026-04-17:

- ✅ **OCG versionado com deltas operacional (incluindo contração no delete)** — commit `3942f6a`. `IngestionService._contract_ocg_for_deleted_document` reverte campos tocados pelo doc, respeita deltas posteriores (fields_skipped), grava delta `trigger_source=document_removal`. 4 testes passando.
- ✅ **Quarentena de PII estável e testada** — commit `3942f6a`. `_detect_pii` passa a validar CPF/CNPJ via mod-11 e cartão via Luhn, elimina falso-positivo de runs de 14 dígitos em xref de PDF que causava quarentena espúria do questionário. 33 testes passando.
- ✅ **Arguidor sem resíduos de hardcode** — DT-012 (commit `1947340`, 2026-04-17) removeu o fallback a `ANTHROPIC_API_KEY` e agora o `__init__` levanta `RuntimeError` explícito se não houver chave do projeto. O SDK `AsyncAnthropic` direto na linha 184 é conhecido residual, mas cai em escopo MVP 3 (multi-provider adapter, §4 resíduos).
- ✅ **Reavaliação do Gatekeeper após ingestão disparando corretamente** — commit `1a2e917`. `_reevaluate_gatekeeper_async` fire-and-forget adjacente ao `_propagate_async` grava evento `GATEKEEPER_REEVALUATED` no audit_log com `blocking_pillars`, `derived_status` e `ocg_version`. 3 testes passando.
- ✅ **Backlog derivado do OCG consistente com o contexto atual** — commit `96eb131`. `_fire_ocg_change_hooks` centraliza o disparo de propagate + gatekeeper reeval nos 3 pontos onde OCG muda: ingestão (já existia), contração no delete (antes não disparava), e geração inicial via questionário (antes não disparava). Projeto novo agora tem backlog populado automaticamente. 4 testes passando.
- ⏸️ **Ingestão madura end-to-end** — quarentena + contração + reavaliação + backlog seeding OK; falta validar integração no dogfood sem quebras.

Gate abre apenas quando §10 estiver inteiramente atendido.

### Histórico do gate
- MVP 1 → **PODE AVANÇAR** em 2026-04-17 com todos os 5 Criticals quitados
  (DT-001..DT-005). Nenhuma regressão observada.
- MVP 2 → **NÃO AVANÇAR** na abertura (2026-04-17) com 2 Criticals + 1 Major
  herdados de código.
- MVP 2 → Criticals/Major de saneamento (DT-012, DT-013, DT-014) quitados em
  2026-04-17. Gate continua fechado aguardando as features canônicas.
- MVP 2 → 2 de 5 features canônicas entregues em 2026-04-17 (contração OCG
  + quarentena PII). 3 pendentes: backlog, Arguidor, Gatekeeper reavaliação.
- MVP 2 → 4 de 6 itens canônicos entregues em 2026-04-17 (+ Gatekeeper
  reavaliação commit `1a2e917`, + Arguidor sem resíduos por reinterpretação
  correta da DT-012). 2 pendentes: backlog-OCG consistente, validação
  ingestão end-to-end no dogfood.
- MVP 2 → 5 de 6 itens canônicos entregues em 2026-04-17 (+ backlog
  consistente commit `96eb131` cobrindo os 3 pontos de mudança de OCG).
  Resta apenas validação ingestão end-to-end no dogfood.
- MVP 2 → Sessão fim do dia 2026-04-17 (dogfood): DT-017 (`/novo-projeto`
  redundante), DT-018 (PDF flattened silencioso), DT-019 (SMTP vazando
  para admins fake + limpeza de 18 users/16 projetos/2 questionários
  órfãos de factory), DT-022 (erro do Arguidor opaco) quitadas. DT-020
  (trace do PDF na aba Questionário — requer migration) e DT-021
  (bloquear upload de questionário via Ingestão) abertos, mas não são
  blocker do gate. Refator de consolidação de Configurações (IA/SMTP/
  Repo/Questionário como abas unificadas + Dashboard bloqueado por
  `RequireProjectSetup`) entregue no commit `cda35fe`. Botões "Testar
  conexão" (LLM) e "Enviar email de teste" (SMTP) agora presentes na
  UI via commit `51ea5c2`. Gate permanece fechado apenas pela validação
  end-to-end manual no dogfood.

### Regra se surgir regressão
Se qualquer Critical reabrir ou teste da fase falhar, o gate volta
automaticamente a **NÃO AVANÇAR** até quitação.

---

## 7. Ordem recomendada de saneamento (MVP 2)

1. **Governança de IA nos serviços do escopo MVP 2** (DT-012, DT-013)
   - remover fallback silencioso em `arguider_service.py` e `ingestion_service.py`;
   - aplicar resolver canônico (`AIKeyResolver.get_project_key` sem fallback
     ao `ANTHROPIC_API_KEY` global);
   - toda chamada deve falhar explicitamente se o projeto não tem chave.

2. **OCG Updater alinhado à política** (DT-014)
   - tratar uso de `DEFAULT_AI_PROVIDER` em `ocg_updater_service.py` com
     classificação de criticidade;
   - OCG updates = alta criticidade (consolidação → modelo premium).

3. **Features do MVP 2** (ordem canônica do contrato §7)
   - ingestão madura + quarentena de PII;
   - OCG versionado com deltas + contração no delete (feedback do user);
   - backlog derivado do OCG consistente;
   - Arguidor funcional end-to-end;
   - reavaliação do Gatekeeper após ingestão.

> Cada passo exige revalidação de testes e gate antes do próximo.

---

## 8. Procedimento obrigatório para Claude

Antes de qualquer mudança:
1. ler `GCA_CANONICAL_CONTRACT.md`;
2. ler este arquivo;
3. identificar se a solicitação pertence ao MVP ativo;
4. verificar blockers/criticals;
5. se houver impedimento, corrigir só o necessário;
6. atualizar este arquivo ao concluir a correção.

### Resposta mínima esperada do Claude por ciclo
- fase avaliada;
- dívida encontrada;
- item corrigido;
- item pendente;
- status do gate: pode avançar / não pode avançar.

---

## 9. Emendas de governança documental

| Data | Emenda | Arquivos | Motivo |
|---|---|---|---|
| 2026-04-17 | Separação explícita entre Contexto A (IA de desenvolvimento do GCA) e Contexto B (IA operacional do cliente). Regra dura de não acoplamento: escolha de IA no desenvolvimento do produto não vira dependência obrigatória do cliente. | `GCA_CANONICAL_CONTRACT.md §6.6` (novo), `CLAUDE.md §6.5` (novo), `GCA_MVP_PROGRESS.md §5.3` (nota) | Prevenir que conveniência de desenvolvimento (ex.: usar Claude/Anthropic para construir o GCA) seja lida como obrigação do cliente final. Preserva flexibilidade multi-provedor por instância/projeto. Sem mudança de código. |
| 2026-04-17 | Saneamento de working tree acumulada: 5 commits organizando 3 frentes (bugfixes, MVP 2 core, automação session 22). Trabalho anterior não commitado foi agrupado por coerência; senha em plaintext em `scripts/capturar_telas_gca.py` extraída para env var antes do commit. | commits `32e12a8`, `80d438d`, `3942f6a`, `f3db454`, `609ca1c` | Reduzir risco de rollback confuso. Trabalho de sessão anterior (contração OCG + PII + scripts manual/tutorial + bugfixes de aprovação GP e axios multipart) estava misturado na working tree sem trilha clara. |

Regra: emendas de governança documental não são dívida técnica. São registradas aqui para preservar trilha de auditoria sobre a evolução do contrato soberano.

---

## 10. Próximo marco de saída do MVP 2

O MVP 2 poderá ser considerado apto a encerrar quando:
- [x] todos os Criticals da fase (DT-012, DT-013) estiverem quitados — 2026-04-17;
- [x] OCG Updater aplicar a política de criticidade (DT-014) — 2026-04-17;
- [~] ingestão + quarentena PII estiverem estáveis e testadas — quarentena OK (commit `3942f6a`, 33 testes); integração end-to-end falta validar no dogfood;
- [x] OCG versionado com deltas operacional (incluindo contração no delete) — commit `3942f6a`, 4 testes;
- [x] backlog derivado do OCG consistente com o contexto atual — commit `96eb131`, 4 testes; `_fire_ocg_change_hooks` centraliza o disparo nos 3 pontos: ingestão, contração no delete, geração inicial via questionário;
- [x] Arguidor funcional sem resíduos de hardcode — DT-012 quitada em commit `1947340` (`arguider_service.py:174` agora é o guard `RuntimeError`, não o fallback). Multi-provider adapter permanece escopo MVP 3;
- [x] reavaliação do Gatekeeper após ingestão disparando corretamente — commit `1a2e917`, 3 testes; emite evento `GATEKEEPER_REEVALUATED` com `{trigger, ocg_version, blocking_pillars, derived_status}`;
- [x] testes da fase passando e nenhum Critical do MVP 1 tiver regredido — 313/336 passando; 23 failures pré-existentes inalteradas;
- [ ] gate mudar para **PODE AVANÇAR** com justificativa registrada.
