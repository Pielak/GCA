# GCA_MVP_PROGRESS.md

Versão: 1.1  
Data-base: 2026-04-17  
Status: **controle de avanço por fase**

---

## 1. Fase atual

### MVP ativo
**MVP 1 — Base operacional e saneamento do núcleo**

### Objetivo do momento
Estabilizar a base já existente do GCA, eliminar conflitos de contrato/RBAC/escopo e impedir que novas features agravem a dívida técnica antes da evolução para os próximos MVPs.

### Princípio desta fase
Nesta fase, o trabalho prioritário é:
1. diagnosticar;
2. classificar dívida;
3. corrigir blockers e criticals;
4. revalidar a base;
5. só então considerar avanço.

---

## 2. Escopo da fase atual

### Em escopo agora
- autenticação;
- RBAC canônico de 5 papéis;
- cadastro/aprovação de projetos;
- questionário;
- OCG básico persistido;
- Gatekeeper básico;
- auditoria mínima;
- configuração básica de provedor de IA;
- política de adequação e roteamento híbrido de IA;
- saneamento de documentação operacional do núcleo;
- saneamento de telas/rotas/componentes que conflitem com o RBAC canônico.

### Fora de escopo agora
- expansão de papéis;
- marketplace;
- billing avançado;
- auto-upgrade avançado;
- hardening completo de produção;
- Release Bundle completo;
- evolução ampla de Documentação Viva;
- expansão livre de módulos apenas porque já aparecem em documentos históricos.

---

## 3. Dívida aberta conhecida

### 3.1 Blocker / Critical

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-001 | Critical | RBAC | Conflito entre documentação histórica com 7 papéis e contrato canônico com 5 papéis. | Docs históricos vs contrato | **Quitada 2026-04-17** — ver §4 |
| DT-002 | Critical | UI/Admin | Há análise apontando que a aba de usuários/admin está modelada com RBAC global ampliado e lista papéis além do recorte canônico. | Análise completa | **Quitada 2026-04-17** — ver §4 |
| DT-003 | Critical | Contrato de produto | Há tensão entre textos que sugerem plataforma ampla pronta e o recorte real que ainda exige saneamento da base. | Docs / README / manual | **Quitada 2026-04-17** — ver §4 |
| DT-004 | Critical | Segurança operacional | PAT de Git ainda aparece documentado em texto plano / criptografia pendente. | Tutorial / requisitos / roadmap | **Quitada 2026-04-17** — ver §4 |
| DT-005 | Critical | Governança de IA | Falta consolidar regra canônica para seleção de provedor/modelo por objetivo do cliente final, evitando default rígido enganoso. | Requisitos / contrato | **Quitada 2026-04-17** — ver §4 |

### 3.2 Major

| ID | Severidade | Tema | Descrição | Origem | Status |
|---|---|---|---|---|---|
| DT-006 | Major | Fases vs realidade | Há materiais descrevendo pipeline completo com módulos avançados como se estivessem igualmente maduros. | Manual / tutorial / análise | Aberto |
| DT-007 | Major | Placeholders / continuidade | Há placeholders de telas/módulos previstos que não devem ser promovidos automaticamente a entregas da fase atual. | TASK_GCA_MASTER | Aberto |
| DT-008 | Major | Consistência documental | Há discrepâncias entre documentos sobre readiness, testes e maturidade operacional. | Changelog / docs / task | Aberto |
| DT-009 | Major | Roteamento híbrido | Falta explicitar em código e docs ativas que tarefas menores podem usar modelo local/Ollama e decisões críticas exigem modelo premium. | Contrato / operação | **Quitada 2026-04-17** (política) — ver §4 |

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

### Situação atual do gate
**PODE AVANÇAR** (atualizado 2026-04-17)

### Justificativa registrada
Todos os 5 Criticals do MVP 1 foram quitados nesta sessão:
- **DT-001** (RBAC 7→5 papéis canônicos em backend + frontend)
- **DT-002** (UI/Admin alinhada aos 5 papéis)
- **DT-003** (narrativa de produto neutralizada; docs históricos marcados)
- **DT-004** (PAT plaintext eliminado; `decrypt_pat` sem fallback silencioso)
- **DT-005** (governança de IA consolidada; OCG sem fallback silencioso)

Critérios do §9 "Próximo marco de saída do MVP 1" — todos atendidos:
- RBAC de 5 papéis coerente em backend, frontend e docs ✅
- Telas e fluxos do núcleo respeitam o RBAC canônico ✅
- Política de IA configurável por cliente explicitada (contrato §6 + CLAUDE §6) ✅
- Roteamento híbrido de IA definido (criticidade baixa/média/alta) ✅
- Conflitos documentais críticos neutralizados (README, ARQUITETURA, docs
  históricos marcados como não-contrato) ✅
- Núcleo auth/projeto/questionário/OCG básico/Gatekeeper básico estável —
  81/81 integration + 44/44 unit + 10/10 crypto passando ✅

Dívida remanescente (Major/Minor, não bloqueante do gate):
- DT-006, DT-007, DT-008 (Major, documental — readiness de materiais,
  placeholders, consistência). Saneamento incremental durante MVP 2.
- DT-009 (Major, roteamento híbrido — política fechada; implementação do
  roteador em código fica para MVP 3, conforme contrato §7).
- DT-010, DT-011 (Minor, terminologia e narrativa promocional).

### Regra se surgir regressão
Se qualquer Critical reabrir ou teste da fase falhar, o gate volta
automaticamente a **NÃO AVANÇAR** até quitação.

---

## 7. Ordem recomendada de saneamento

1. **RBAC canônico**
   - congelar 5 papéis em backend, frontend e docs ativas;
   - marcar documentos históricos como históricos.

2. **Contrato de produto**
   - consolidar instalação por cliente + isolamento por projeto;
   - eliminar leituras ambíguas de SaaS compartilhado.

3. **Admin / gestão de usuários**
   - alinhar páginas e fluxos ao RBAC canônico;
   - remover dependência implícita de papéis históricos.

4. **Política de IA**
   - introduzir recomendação por objetivo do cliente;
   - explicitar roteamento híbrido por criticidade;
   - manter provedores/modelos configuráveis.

5. **Segurança operacional do núcleo**
   - preparar trilha de correção para PAT/segredos;
   - evitar expansão de módulos antes disso.

---

## 8. Procedimento obrigatório para Claude

Antes de qualquer mudança:
1. ler `GCA_CANONICAL_CONTRACT.md`;
2. ler este arquivo;
3. identificar se a solicitação pertence ao MVP 1;
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

## 9. Próximo marco de saída do MVP 1

O MVP 1 poderá ser considerado apto a encerrar quando:
- RBAC de 5 papéis estiver coerente;
- telas e fluxos do núcleo respeitarem esse RBAC;
- política de IA configurável por cliente estiver explicitada;
- roteamento híbrido de IA estiver definido para tarefas menores vs decisões críticas;
- conflitos documentais críticos estiverem neutralizados;
- núcleo auth/projeto/questionário/OCG/Gatekeeper básico estiver estável;
- gate de avanço mudar para **PODE AVANÇAR** com justificativa registrada.
