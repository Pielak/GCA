# GCA_MVP_PROGRESS.md

Versão: 1.1  
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

### Situação atual do gate (MVP 2)
**NÃO AVANÇAR** (features da fase ainda não implementadas)

### Motivo
Dívida de saneamento (DT-012, DT-013, DT-014) quitada em 2026-04-17. O gate
permanece fechado porque as features canônicas do MVP 2 (contrato §7) ainda
não estão entregues: contração de OCG no delete, reavaliação do Gatekeeper
pós-ingestão, Arguidor end-to-end sem quebras no dogfood. O gate só abre
quando o §9 "Próximo marco de saída do MVP 2" for inteiramente atendido.

### Histórico do gate
- MVP 1 → **PODE AVANÇAR** em 2026-04-17 com todos os 5 Criticals quitados
  (DT-001..DT-005). Nenhuma regressão observada.
- MVP 2 → **NÃO AVANÇAR** na abertura (2026-04-17) com 2 Criticals + 1 Major
  herdados de código.
- MVP 2 → Criticals/Major de saneamento (DT-012, DT-013, DT-014) quitados em
  2026-04-17. Gate continua fechado aguardando as features canônicas.

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

## 9. Próximo marco de saída do MVP 2

O MVP 2 poderá ser considerado apto a encerrar quando:
- todos os Criticals da fase (DT-012, DT-013) estiverem quitados;
- OCG Updater aplicar a política de criticidade (DT-014);
- ingestão + quarentena PII estiverem estáveis e testadas;
- OCG versionado com deltas operacional (incluindo contração no delete);
- backlog derivado do OCG consistente com o contexto atual;
- Arguidor funcional sem resíduos de hardcode;
- reavaliação do Gatekeeper após ingestão disparando corretamente;
- testes da fase passando e nenhum Critical do MVP 1 tiver regredido;
- gate mudar para **PODE AVANÇAR** com justificativa registrada.
