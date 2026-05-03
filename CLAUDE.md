# CLAUDE.md

Operacional do Claude Code no GCA. Para contrato formal do produto (extenso), ver `GCA_CANONICAL_CONTRACT.md`. Para estado atual do MVP, ver `GCA_MVP_PROGRESS.md`. Para histórico, ver `docs/_deprecated/`.

> **Atenção ao reler este arquivo:** as regras com `❌`, `🛑` e `⚠` são vinculantes em ordem decrescente — `❌` é proibição absoluta, `🛑` é parada obrigatória, `⚠` é alerta. Não há regra "soft" aqui. Se uma seção parece restritiva, é intencional.

---

## 0. Honestidade técnica (precede tudo)

Estas regras valem em todos os turnos, em todos os modos, em todas as fases.

- ❌ **Proibido afirmar que algo "funciona", "está 100%", "está pronto" ou "passa nos testes" sem ter executado o comando que prova.** Se não rodou, dizer: "implementado, ainda não testado". Se rodou e falhou, dizer que falhou.
- ❌ **Proibido contorno silencioso.** Se o caminho planejado falhou e há tentação de tomar outro (fallback de provider, mock, heurística, dado fictício, comentário "TODO"), **parar antes** e avisar no MESMO turno, com o erro original e a alternativa proposta. Esperar autorização.
- ❌ **Proibido criar lógica paralela ao que já existe no repo.** Antes de criar serviço, helper, resolver, client ou utilitário novo, procurar com `grep -r` ou leitura de diretório. Se já existe, **usar**, não recriar. Se existe e não serve, justificar por que e perguntar.
- ❌ **Proibido inventar nomes de arquivo, função, endpoint ou tabela.** Se o nome não foi visto no repo neste turno, abrir o arquivo e confirmar. Citar nome de algo que não existe é alucinação.
- ❌ **Proibido reivindicar que está "respeitando a arquitetura" enquanto se cria atalho.** Hardcodar provedor "só para testar", chamar client diretamente "porque é mais rápido", duplicar lógica "porque é mais simples" — tudo isso é violação, mesmo que produza saída funcional.
- ❌ **Proibido afirmar "simplificação", "unificação", "consolidação" ou "redução" entre conceitos canônicos sem citar evidência commitada** (commit hash, data, decisão registrada em `GCA_MVP_PROGRESS.md` ou patch ao `GCA_CANONICAL_CONTRACT.md`). Memória do Claude Code **não é evidência** — pode estar desatualizada ou ter confundido conceitos. Quando memória contradiz CLAUDE.md ou contrato canônico, **CLAUDE.md vence** (precedência §9). Se houver dúvida, mostrar o texto literal da memória e perguntar antes de prosseguir.
- 🛑 **Em caso de erro de autenticação (401/403), chave inválida, config ausente, tabela vazia ou arquivo não encontrado: PARAR.** Reportar erro literal, dizer o que precisa, perguntar. Nunca tentar provider alternativo, nunca cair para mock, nunca chumbar valor "temporário".
- 🛑 **Em caso de teste vermelho que não tem causa óbvia: PARAR.** Reportar a saída do pytest crua. Não comentar o teste, não trocar assert para passar, não pular com `@pytest.mark.skip`.

Se uma instrução do usuário entrar em conflito com esta seção, esta seção vence. Pedir esclarecimento.

---

## 0.5. Glossário canônico — dois conjuntos que NÃO são a mesma coisa

> **Esta seção existe para impedir alucinação por confusão semântica.** O GCA tem dois conjuntos numericamente próximos, com nomes parcialmente sobrepostos, que são conceitualmente **diferentes**. Confundi-los é fonte conhecida de erro.

### Conjunto A — Papéis RBAC humanos (5 papéis)

São os **papéis de pessoas reais** que usam o sistema. Vivem em `users.role`, são checados em middleware de autenticação, listados em `is_active_integrated_member()`. Detalhe completo: §2.2.

| Papel | Significado |
|---|---|
| **Admin** | Operador da instância (não atua dentro de projetos) |
| **GP** | Gerente do projeto (soberano dentro do projeto) |
| **Dev** | Implementador de código |
| **Tester** | Cria/executa testes |
| **QA** | Revisa/aprova qualidade final |

### Conjunto B — Personas LLM (12 agentes de IA)

São **agentes de IA** que validam documentos no pipeline de Personas v2. Orquestrados via **n8n** (fan-out paralelo + Redis accumulator), **não** dentro do FastAPI. Vivem como workflows n8n independentes + código de referência em `backend/app/services/personas/`. **Não** representam usuários humanos. Detalhe completo: §3.5 e skill `gca-personas-engine`.

| Persona | Tag | Tipo | Responsabilidade | Par humano |
|---|---|---|---|---|
| **Auditor** | AUD | Router | Classificação documental + roteamento + briefing | (sem par — interno ao GCA) |
| **Gerente de Projetos** | GP | **Orquestrador** | Supervisiona equipe, valida escopo, viabilidade, ROI | Gerente do cliente |
| Arquiteto | ARQ | Especialista | Stack, padrões, integrações, NFRs | Tech Lead |
| DBA | DBA | Especialista | Modelo de dados, retenção, queries | DBA do cliente |
| Dev Sr. | DEV | Especialista | Implementabilidade, dependências | Líder técnico |
| QA | QA | Especialista | Testes, cobertura, BDD | QA Lead |
| UX | UX | Especialista | Jornada, acessibilidade, WCAG, microcopy | UX Designer |
| UI | UI | Especialista | Design system, estados, responsividade | UI Designer |
| Segurança | SEG | Especialista | OWASP, AuthN/Z, secrets, superfície de ataque | Security Engineer |
| **Conformidade** | CONF | Especialista **BLOQUEANTE** | Aderência regulatória — score <60 bloqueia ingestão | Compliance Officer |
| Proteção de Dados | LGPD | Especialista | Dados pessoais, base legal, consentimento, retenção | DPO |
| Negócio | NEG | Especialista | Valor, alinhamento estratégico, risco operacional | Product Owner |

### Regras duras sobre os dois conjuntos

- ❌ **Os dois conjuntos NÃO são reconciliáveis.** GP/DEV/QA aparecem nos dois com significado diferente: no Conjunto A são papéis humanos no sistema; no Conjunto B são personas LLM no pipeline. Coincidência de nome é intencional (a persona LLM "GP" valida sob a perspectiva de um Gerente de Projetos), **não** é redundância a eliminar.
- ❌ **NUNCA afirmar que houve "simplificação de 12 para 5" ou "unificação".** Não houve. Memória do Claude Code que sugerir isso está errada ou confundindo os conjuntos. Verificar contra CLAUDE.md vigente.
- ❌ **NUNCA criar um terceiro conjunto "intermediário"** que tenta unificar os dois. Permanece sempre 5 + 12.
- ✅ **Quando o contexto mencionar "papel" ou "role", é Conjunto A (5).** Quando mencionar "persona" ou "agente IA" ou "validador LLM", é Conjunto B (12).
- ✅ **Quando ambíguo, perguntar antes de assumir.**

### Por que isso está aqui

Houve um caso real (sessão de 2026-04-30) em que o Claude Code, com base em memória, sugeriu que o CLAUDE.md poderia estar desatualizado por mencionar 8 personas quando "só haveria 5". A memória estava confundindo o Conjunto A com o Conjunto B. Em 2026-05-02, o Conjunto B foi expandido de 8 para 12 personas (adição de SEG, CONF, LGPD, NEG + GP promovido a orquestrador). Esta seção existe para que esse erro não se repita.

---

## 1. Antes de qualquer trabalho

### 1.1. Toda sessão (mínimo absoluto)

1. Ler `GCA_CANONICAL_CONTRACT.md` — fonte soberana para decisões formais.
2. Ler `GCA_MVP_PROGRESS.md` — MVP ativo + próximo marco.
3. Se for fase de MVP aberto, confirmar autorização explícita antes de codar.
4. Se detectar contradição entre docs, reportar e seguir o contrato. Não reconciliar silenciosamente.

### 1.2. Protocolo de leitura obrigatória por área

Antes de **editar, escrever ou criar** arquivo nas áreas abaixo, abrir e ler os símbolos canônicos correspondentes. Se o símbolo não existir no repo, **PARAR e perguntar** — não inventar substituto. Skills listadas em `.claude/skills/` são lidas sob demanda pelo próprio Claude Code quando o contexto bate com a `description` da skill.

| Área tocada | Skill / símbolos canônicos |
|---|---|
| LLM, IA, provider, prompt, completion, embedding, multi-LLM | skill `gca-llm-resolver` · classe `AIKeyResolver` · tabela `project_settings` |
| OCG, contexto global, expansão, propagação, backlog vivo | skill `gca-ocg-engine` · contrato §5 |
| Personas LLM (Conjunto B), validação assistida, Auditor, 12 agentes, HITL, ConflictDetector | skill `gca-personas-engine` · §0.5 (glossário) |
| Papéis RBAC humanos (Conjunto A), permissões, autorização | helper `is_active_integrated_member` · contrato §4 (5 papéis canônicos) · §0.5 (glossário) |
| Secrets, tokens, PAT, chaves, senhas | classe `VaultService` · função `generate_temporary_password` em `app.core.security` |
| Gatekeeper, validação, pilares, arbitragem | módulo Gatekeeper (7 pilares) · contrato §6.2 (Conformidade é blocker em score < 60) |
| Migrations Alembic, schema | últimas migrations no diretório, regenerar com `alembic revision --autogenerate` |
| Frontend (rotas, componentes, páginas) | componente vizinho mais próximo para herdar padrão de estilo |

A regra é: **se você não leu o símbolo canônico antes, não escreve código que depende dele**. O custo de ler é minutos; o custo de retrabalho é horas.

---

## 2. Invariantes do produto (do contrato canônico — inline neste arquivo)

Estes pontos são lidos em toda sessão. Detalhe extenso em `GCA_CANONICAL_CONTRACT.md`.

### 2.1. Modelo de deployment e isolamento

- ✅ GCA é **instalável por cliente** (on-premises). Uma instância por cliente.
- ❌ Não é SaaS multi-tenant compartilhado. `gca.code-auditor.com.br` é **dogfood**, não prova de SaaS.
- ✅ Isolamento principal **por projeto** dentro da instância.
- ❌ Sem compartilhamento de OCG, artefatos, credenciais ou contexto entre projetos.
- ✅ Toda query de dado de projeto inclui `project_id` no WHERE. Sem exceção.

### 2.2. RBAC canônico — Conjunto A (5 papéis humanos imutáveis)

> **Atenção:** este é o **Conjunto A** do glossário §0.5. Não confundir com as 8 personas LLM (§3.5).

**Admin · GP · Dev · Tester · QA**. Não inventar outros.

- **Admin**: opera a instância, configura provedores/políticas/SMTP, aprova projetos. Não atua dentro de projetos. Não escreve código.
- **GP**: soberano do projeto (emenda 2026-04-19). Acima de Dev/Tester/QA dentro do projeto, com acesso a todas as funcionalidades. Pode operar CodeGen, pipeline e testes. Análogo: GP está para o projeto assim como Admin está para a instância.
- **Dev**: implementa código. Opera ingestão, Arguidor, CodeGen e commits. Não aprova módulo no Gatekeeper.
- **Tester**: cria/edita/executa testes. Registra evidências.
- **QA**: revisa/aprova resultados. Valida qualidade final. Não edita conteúdo de teste.

**Não canônicos nesta versão** (podem aparecer em docs históricos, **não implementar como roles**): Tech Lead, Compliance, Stakeholder, Viewer, Dev Sênior/Pleno como roles distintos.

### 2.3. Modelo de IA — provider configurável por cliente

- ✅ Cliente final usa suas próprias chaves, provedores e modelos.
- ✅ Sistema oferece análise de adequação antes de fixar default.
- ❌ Nenhum provedor é "melhor universal".
- ✅ Modo híbrido por tipo de tarefa permitido, desde que configurável e auditável.
- **Porta única para resolução**: `AIKeyResolver.resolve_project_provider_chain(db, project_id)`. Detalhe em skill `gca-llm-resolver`.

### 2.4. OCG — fonte única de verdade do projeto

> **REGRA ATUAL** (substitui versão anterior):

- ✅ OCG nasce do questionário aprovado.
- ✅ OCG é evolutivo e auditável.
- ✅ **OCG só expande quando recebe informação de valor**. Nunca contrai por análise.
- ✅ Ingestão ruim ou conflitante: documento vai para **quarentena** e **não afeta o OCG**. Não há mais "contração de confiança" como behavior do motor.
- ✅ Módulos não podem assumir defaults invisíveis quando o OCG estiver incompleto: bloquear ou exigir complementação.
- ✅ Toda mudança gera versionamento e trilha de auditoria.

#### Reversão por deleção legítima da fonte (MVP 34, 2026-05-03)

Complementa — **não viola** — a regra "OCG não contrai por ingestão". A regra acima protege contra LLM hallucination, ingestão maliciosa ou conflitante. **Quando o GP soft-deleta um `ingested_documents` row** (operação humana de gestão: smoke fixture, erro de upload, PII em LGPD, doc obsoleto), os efeitos derivados devem ser revertidos:

- ✅ Endpoint `DELETE /api/v1/projects/{pid}/ingestion/{did}?reason=manual|lgpd|smoke_cleanup` é o caminho canônico — retorna **202 Accepted** + `revert_job_id`.
- ✅ Soft-delete imediato (`deleted_at IS NOT NULL`) — doc some de queries de listagem/CodeGen/specs/livedocs/consistência (12 pontos canônicos filtrados).
- ✅ Celery job em background recompute o OCG ignorando o doc (via JOIN `WHERE deleted_at IS NULL` em `_load_persona_scores`).
- ✅ Versão do OCG incrementa com `change_type='REVERT_DOCUMENT_DELETE'` e `ocg_delta_log` ganha row com `trigger_source='document_revert'`.
- ✅ Tabelas auxiliares limpas: `persona_follow_up_questions` → `expired`, `conflicts_pending_review`/`chunk_errors_pending_review` → `archived_doc_deleted`.
- ✅ `module_candidates` órfãos (única fonte = doc deletado) viram `archived`. Múltiplas fontes: remove `doc_id` da lista, mantém candidato.
- ✅ Audit event `DOCUMENT_REVERTED` em `audit_log_global` (hash chain íntegro).
- ✅ `maturity_warning` populado em PT-BR quando `score_after < SCORE_MATURIDADE` (gate CodeGen).
- ⚠ **LGPD parcial:** `pii_fields`, `ocg_individual.parecer` e `ocg_global.parecer_consolidated` permanecem (DT-086 — purge físico em MVP futuro).

**Conceitualmente:** a regra "OCG não contrai" continua. O que muda é o caminho de **gestão da fonte**: deletar o doc é operação humana, e o sistema garante que efeitos derivados sigam a deleção da fonte. Não é contração arbitrária — é integridade.

Detalhe da máquina de estado, schema e propagação: skill `gca-ocg-engine`. Detalhe operacional do MVP 34: [`docs/MVP_34_REVERT_DOCUMENT_DELETE.md`](docs/MVP_34_REVERT_DOCUMENT_DELETE.md).

#### Cascata especial para `file_type='questionnaire'` (MVP 35, 2026-05-03)

Quando o doc deletado é o IngestedDocument sintético do questionário técnico (criado no submit), a cascata estende:

- ✅ `TechnicalQuestionnaire.status` → `archived` (preserva histórico, força novo questionário)
- ✅ `Questionnaire.approved` (legacy, FK do OCG) → `False`
- ✅ `setup_status.questionnaire_approved` → `False` → `ready_to_activate` → `False`
- ✅ Pipeline n8n bloqueado até novo questionário ser submetido
- ✅ Frontend redireciona para `/settings?tab=questionario`

Pipeline canônico, NESTA ORDEM (MVP 35 §_check_setup_status):
1. **Repositório Git** (ou similar) configurado
2. **Chave LLM** válida e validada
3. **Questionário técnico** APROVADO E SUBMETIDO (sem aprovação, gate fica fechado)

Estado canônico do Questionário Técnico (MVP 35):
- `draft` — rascunho/auto-save
- `validated` — passou Validar Escopo (Camada 1 = 30 regras DSL determinísticas), pré-submit
- `submitted` — terminal, dispara personas + cria IngestedDocument sintético (após Camada 2 LLM sanity check)
- `archived` — deletado via Ingestão (volta projeto a setup)

Validação canônica (2 camadas):
- **Camada 1 — RulesEvaluator** (`backend/app/services/questionnaire_validation/`): 30 regras DSL JSON em 5 temas (NoSQL×ACID, Stack runtime, FE×BE, Compliance×PII, Infra×escala). Stateless, determinístico, < 50ms. Espelha frontend via `GET /api/v1/projects/technical-questionnaire/rules`.
- **Camada 2 — LLM sanity check** (apenas no submit): detecta incoerências semânticas. Em falha, **bloqueia submit** (sem fallback silencioso, alinha §0 deste arquivo).

Detalhe operacional do MVP 35: [`docs/MVP_35_QUESTIONNAIRE_VALIDATION.md`](docs/MVP_35_QUESTIONNAIRE_VALIDATION.md).

### 2.5. Política de criticidade de IA (3 níveis)

- **Baixa**: local/barato (Ollama ou modelo econômico).
- **Média**: qualquer provider configurado.
- **Alta**: premium obrigatório (OCG consolidação, arbitragem, compliance crítico, codegen crítico).

Sem rota de criticidade alta passando por modelo barato. Sem fallback automático para modelo inferior.

### 2.6. Fluxo de MVP

- ✅ Cada fase de MVP exige autorização explícita do GP antes de codar (§7.0 contrato).
- ❌ Nada executa em bloco sem luz verde.
- ✅ Fixes descobertos em dogfood viram commit `fix:`, não MVP novo. MVP é reservado para escopo novo planejado.

---

## 3. Pontos arquiteturais com porta de entrada única

### 3.1. Resolução de provider de IA

- ✅ Porta única: `AIKeyResolver.resolve_project_provider_chain(db, project_id)`.
- ✅ Configuração: tabela `project_settings`, `setting_type='llm'`. UI em **Settings > IA**.
- ❌ Proibido instanciar `AnthropicLLMClient`, `OpenAIClient`, `DeepSeekClient`, `GeminiClient` ou `OllamaClient` diretamente em rotas, services ou personas.
- ❌ Proibido `provider = "anthropic"` chumbado em código.
- ❌ Proibido fallback automático entre providers em caso de falha de auth. Falhou auth → §0 §🛑.
- ✅ Se `resolve_project_provider_chain` retornar vazio: `raise HTTPException(400, "Projeto sem LLM configurado. Abra Settings > IA")`.
- ✅ Critério de provider segue §2.5 (criticidade). Não inventar critério próprio.

### 3.2. Secrets e tokens

- ✅ Porta única para guardar: `VaultService.store_secret`. Para ler: `VaultService.get_secret`.
- ⚠ `VaultService.store_secret` commita internamente — testes que o chamam dentro de `session.begin()` quebram. Use sessões separadas.
- ✅ PAT do Git é cifrado com Fernet (M03). Master key em `/var/lib/gca/secrets/fernet.key`. Prefixo obrigatório: `fernet:v1:`.
- ✅ Senhas temporárias para convite: `generate_temporary_password()` de `app.core.security` (RF-001: 10 chars, 1 maiúscula, 1 dígito, 1 especial).
- ❌ Proibido `secrets.token_urlsafe(12)` para senha canônica. Não atende RF-001.
- ❌ Proibido logar valor de secret, mesmo em DEBUG. Nem em comentário, nem em mensagem de erro, nem em response body.

### 3.3. RBAC — listagem de membros

- ✅ Listagem filtra `is_active AND joined_at IS NOT NULL`. Use `is_active_integrated_member()`.
- ❌ Filtrar só por `is_active` inclui convite pendente como membro ativo, vaza dado.

### 3.4. OCG (Objeto de Contexto Global)

- ✅ Toda decisão arquitetural, funcional ou de código **lê o OCG antes** e **atualiza depois**. Não é sugestão.
- ❌ Pular leitura do OCG porque "a mudança é pequena" — proibido. OCG existe para garantir consistência cross-cutting.
- ✅ Detalhe da máquina de estado, propagação e backlog vivo: skill `gca-ocg-engine`.

### 3.5. Personas LLM — Conjunto B (12 agentes de IA — não confundir com os 5 papéis RBAC de §2.2)

> **Atenção:** este é o **Conjunto B** do glossário §0.5. **12 personas LLM**, agentes de IA do pipeline de validação. **Não são** os 5 papéis humanos do RBAC. Lista canônica completa em §0.5.

- ✅ 12 personas: AUD (router) + GP (orquestrador) + 10 especialistas (ARQ, DBA, DEV, QA, UX, UI, SEG, CONF, LGPD, NEG).
- ✅ **Orquestração via n8n** — cada especialista é um workflow independente com webhook próprio. Conferente (AUD) faz fan-out paralelo. Consolidador agrega via Redis accumulator.
- ✅ **CONF é bloqueante** — score <60 bloqueia a ingestão (§6.2 do contrato).
- ✅ **GP é orquestrador** — supervisiona o resultado da equipe de especialistas, como um gerente com sua equipe.
- ✅ Filosofia "Assistida": LLM tem permissão explícita de **não saber**. Quando atinge limite dos insumos, gera questionário estruturado para humano e pausa o pilar afetado.
- ✅ Detalhe da arquitetura em 4 camadas, HITL, ConflictDetector, KPIs: skill `gca-personas-engine`.

### 3.6. Banco de testes

- ✅ Pytest do GCA roda contra `gca_test`, nunca contra `gca`. `conftest.py` força — não passe por cima.
- ✅ Se schema mudou: `pg_dump gca --schema-only | psql gca_test` após recreate.
- ❌ Criar dados no banco de produção (`gca`) sem autorização explícita — proibido. É dogfood; mock vira ruído real.

---

## 4. Plan Mode obrigatório

Para as áreas abaixo, **iniciar em Plan Mode** (Shift+Tab × 2). Apresentar plano, esperar aprovação, só então executar.

- Mudanças em resolução de provider de IA (§3.1).
- Mudanças em RBAC, autorização ou middleware de auth.
- Mudanças em VaultService, criptografia, rotação de chave.
- Mudanças em licenciamento (Marco 4: RSA, Base58, fingerprint, ciclo de 4 estados).
- Mudanças em OCG, Gatekeeper, Arguidor ou sistema de Personas LLM.
- Mudanças em migrations Alembic.
- Mudanças em mais de 3 arquivos simultaneamente.
- Refactor que cruza diretórios.

Plan Mode não é "modo lento". É a versão barata do retrabalho — corrigir um plano custa segundos; corrigir código já implementado custa tokens, contexto e revisão humana.

---

## 5. Estratégia de trabalho

A ordem importa. Pular passo é fonte conhecida de retrabalho.

1. **Localizar.** Antes de criar X, `grep -r "X"` no repo. Se existir, ler. Se não existir, confirmar.
2. **Diagnosticar.** Reproduzir o problema com comando concreto antes de propor solução.
3. **Classificar dívida** se encontrar inconsistência. Não tentar corrigir tudo no mesmo PR.
4. **Corrigir blocker/critical primeiro**, depois revalidar com pytest contra `gca_test`.
5. **Só então** expandir para feature nova.
6. Fixes descobertos em dogfood viram commit `fix:`, não MVP novo.

Correção cirúrgica > refactor amplo (§10 contrato). Não tocar código vizinho funcionando, mesmo que pareça "melhorável".

---

## 6. Gotchas operacionais

### Banco e migrations

- ❌ `pytest` do GCA sempre contra `gca_test`, nunca `gca`. Conftest já força.
- ❌ Schema mudou? `pg_dump gca --schema-only | psql gca_test` após recreate. Antes disso, pytest mente.
- ❌ Não criar dados no DB de produção sem autorização explícita.

### Docker e build

- ❌ `docker-compose.yml` editado → `docker compose up -d`, **não** `restart <serviço>`. Restart não vê config novo.
- ❌ Frontend editado → `docker exec gca-frontend npm run build` + `docker restart gca-frontend` + informar hard-refresh ao usuário. Vite preview não recarrega.

### Vault e secrets

- ❌ `VaultService.store_secret` commita internamente. Testes que o chamam dentro de `session.begin()` quebram — use sessões separadas.
- ❌ `secrets.token_urlsafe(12)` não é senha canônica. Use `generate_temporary_password()` de `app.core.security`.

### Membros e RBAC

- ❌ Listagem de membros filtra `is_active AND joined_at IS NOT NULL`. Use `is_active_integrated_member()`.

### MVP e contrato

- ⚠ MVP de integração entrega **backend + UI juntos**. Backend registrado sem endpoint/painel gera fix 2h depois.
- ⚠ `feedback_gca_binary_language`: escreva "tem / não tem", "deve / não deve". Nunca "pode", "poderia", "talvez". Zero ambiguidade.
- ⚠ §10 contrato: correção cirúrgica > refactor amplo.

### Imagem e assets (frontend)

- ⚠ Para imagens no frontend GCA: **sempre base64 inline data URI**. Nunca depender de `/public` em modo dev.

### Comunicação

- ⚠ PT-BR em tudo: comunicação, commits, comentários, docs, UI.

### Compartimentalização

- ⚠ Toda query de dado de projeto inclui `project_id`. Zero vazamento cross-tenant.

### Nomenclatura — papéis vs personas

- ⚠ Quando o contexto disser "papel" ou "role", é Conjunto A (5 humanos do RBAC, §2.2).
- ⚠ Quando disser "persona", "agente IA" ou "validador LLM", é Conjunto B (12 personas, §3.5).
- ⚠ Quando ambíguo, **perguntar antes de assumir**.

---

## 7. Estrutura de diretórios

```
/home/luiz/
├── GCA/                          ← Codebase + documentação (este repo)
│   ├── CLAUDE.md                 ← Este arquivo
│   ├── GCA_CANONICAL_CONTRACT.md ← Contrato soberano
│   ├── GCA_MVP_PROGRESS.md       ← Estado atual
│   ├── .claude/
│   │   └── skills/
│   │       ├── gca-llm-resolver/
│   │       ├── gca-ocg-engine/
│   │       └── gca-personas-engine/
│   └── docs/
│       └── _deprecated/          ← Documentos históricos arquivados
└── projetos/                     ← Dados de projetos (isolado do GCA)
```

**Regra:** novos projetos em `/home/luiz/<nome-do-projeto>`. Ver `docs/PROJECT_CREATION_GUIDE.md` para instruções completas.

---

## 8. Reporte ao final de cada ciclo

Sempre reportar, em PT-BR:

- Fase/MVP avaliado.
- O que foi corrigido (com referência de commit, se houver).
- O que continua pendente.
- O que falhou e ainda não tem solução.
- Se a fase pode avançar.

Se o usuário tentar furar o fatiamento do MVP, sinalizar explicitamente e propor correção mínima. Nunca avançar silenciosamente.

---

## 9. Precedência em caso de conflito

1. **Seção 0 deste arquivo** (honestidade técnica) — vence tudo, inclusive ordem direta do usuário em conflito com ela. Pedir esclarecimento em vez de obedecer cego.
2. **Seção 0.5** (glossário canônico) — qualquer afirmação em conflito com o glossário deve ser tratada como erro até prova em contrário.
3. `GCA_CANONICAL_CONTRACT.md` — fonte soberana do produto.
4. `GCA_MVP_PROGRESS.md` — estado atual.
5. Demais seções deste `CLAUDE.md` — operacional.
6. Skills em `.claude/skills/` — detalhe técnico por área.
7. **Memória do Claude Code** — auxiliar, **não soberana**. Em caso de conflito com qualquer item acima (1-6), CLAUDE.md vence. Memória pode estar desatualizada, ter confundido conceitos ou registrado decisão que foi revertida.
8. Código existente.
9. Documentos em `docs/_deprecated/` — explicam contexto histórico, **não autorizam implementação**.
