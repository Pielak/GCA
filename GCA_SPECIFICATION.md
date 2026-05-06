# GCA_SPECIFICATION.md — Produto + Arquitetura

**Versão:** 2.0  
**Data:** 2026-05-05  
**Status:** Canônico / soberano para implementação

> **Workflow do Claude Code:** `CLAUDE.md`  
> **Detalhes técnicos:** `GCA_TECHNICAL_REFERENCE.md`  
> **MVPs:** `GCA_MVP_ROADMAP.md`

---

## §1. Definição canônica do produto

**GCA (Gestão de Codificação Assistida)** é uma **meta-plataforma** para construir sistemas, aplicativos e código com:
- Ingestão estruturada de requisitos
- Validação assistida por 12 personas LLM
- OCG (Objeto de Contexto Global) cumulativo como fonte única de verdade
- CodeGen liberado **somente quando OCG ≥ 95%**
- **Supervisão humana obrigatória** em toda liberação, revisão e deploy

### §1.1. Princípio fundamental: GCA NÃO é ponto final

GCA gera, mas **não decide sozinho**. Toda saída crítica (módulos, código, testes, deploy) requer:
- Aprovação humana (GP, Dev, QA conforme RBAC §3)
- Gate OCG ≥ 95% (sem exceção, configurável apenas por Admin)
- Auditoria rastreável de cada decisão

### §1.2. Modelo de deployment

- ✅ GCA é **instalável por cliente** (on-premises). Uma instância por cliente.
- ❌ Não é SaaS multi-tenant compartilhado.
- ✅ `gca.code-auditor.com.br` é **dogfood**, não prova de SaaS.
- ✅ Isolamento principal **por projeto** dentro da instância.
- ❌ Sem compartilhamento de OCG, artefatos, credenciais ou contexto entre projetos.
- ✅ Toda query de dado de projeto inclui `project_id` no WHERE. Sem exceção.

---

## §2. Provider de IA — escolha do cliente

- ✅ Cliente final usa suas próprias chaves, provedores e modelos.
- ✅ Sistema oferece análise de adequação antes de fixar default.
- ❌ Nenhum provedor é "melhor universal".
- ✅ Modo híbrido por tipo de tarefa permitido (configurável e auditável).

**Porta única de resolução:** `AIKeyResolver.resolve_project_provider_chain(db, project_id)`. Detalhe: `GCA_TECHNICAL_REFERENCE.md §4`.

### §2.1. Política de criticidade (3 níveis)

- **Baixa** — local/barato (Ollama ou modelo econômico): classificação simples, extração de campos, sumarização curta, normalização.
- **Média** — qualquer provider configurado: perguntas dirigidas, propostas iniciais, pré-análise.
- **Alta** — premium obrigatório: consolidação OCG, arbitragem, compliance crítico, codegen crítico, decisões de arquitetura.

❌ Sem rota de criticidade alta passando por modelo barato. Sem fallback automático para modelo inferior.

### §2.2. Separação dev vs operação cliente

- **Construir GCA**: equipe escolhe modelo premium (custo de desenvolvimento).
- **Operar instância cliente**: cliente escolhe (custo operacional do cliente).
- **Não acoplamento**: IA do desenvolvimento não vira dependência do cliente.

---

## §3. RBAC canônico — Conjunto A (5 papéis humanos)

> **Conjunto A** do glossário (CLAUDE.md §0.5). Não confundir com 12 personas LLM (§4).

**Admin · GP · Dev · Tester · QA**. Imutável. Não inventar outros.

### Admin
- Opera a instância. Configura provedores, políticas, SMTP, thresholds.
- Aprova/libera projetos.
- **Não atua dentro de projetos. Não escreve código.**

### GP (Gerente de Projeto)
- **Soberano do projeto** (emenda 2026-04-19): acima de Dev/Tester/QA dentro do projeto.
- Acesso a TODAS as funcionalidades do projeto.
- Pode operar CodeGen, pipeline e testes.
- Análogo: GP está para o projeto assim como Admin está para a instância.

### Dev
- Implementa código. Opera ingestão, Arguidor, CodeGen, commits.
- **Não aprova módulo no Gatekeeper.**

### Tester
- Cria/edita/executa testes. Registra evidências.

### QA
- Revisa/aprova resultados. Valida qualidade final.
- **Não edita conteúdo de teste.**

### Não canônicos (NÃO implementar como roles)
Tech Lead, Compliance, Stakeholder, Viewer, Dev Sênior/Pleno como papéis distintos. Podem aparecer em docs históricos como ator narrativo, **não no RBAC**.

**Helper canônico:** `is_active_integrated_member()` em `backend/app/services/project_team_service.py`.

---

## §4. Personas LLM — Conjunto B (12 agentes IA)

> **Conjunto B** do glossário. **NÃO** são os 5 papéis humanos. Orquestrados via **n8n** (fan-out paralelo + Redis accumulator), **NÃO** dentro do FastAPI.

| Persona | Tag | Tipo | Pilar OCG | Par humano |
|---|---|---|---|---|
| **Auditor** | AUD | Router | (sem score) | (interno ao GCA) |
| **Gerente de Projetos** | GP | **Orquestrador** | p1_business_score | Gerente do cliente |
| Negócio | NEG | Especialista | p1_business_score | Product Owner |
| **Conformidade** | CONF | **BLOQUEANTE <60** | p2_rules_score | Compliance Officer |
| Proteção de Dados | LGPD | Especialista | p2_rules_score | DPO |
| UX | UX | Especialista | p3_features_score | UX Designer |
| UI | UI | Especialista | p3_features_score | UI Designer |
| QA | QA | Especialista | p4_nfr_score | QA Lead |
| Arquiteto | ARQ | Especialista | p5_architecture_score | Tech Lead |
| Dev Sr. | DEV | Especialista | p5_architecture_score | Líder técnico |
| DBA | DBA | Especialista | p6_data_score | DBA do cliente |
| Segurança | SEG | Especialista | p7_security_score | Security Engineer |

**Mapping persona → pilar canônico:** `backend/app/services/ocg_consolidator_service.py:34-46`.

### §4.1. Regras das personas

- ✅ **CONF é bloqueante** — score <60 bloqueia ingestão (§6.2).
- ✅ **GP é orquestrador** — supervisiona resultado da equipe.
- ✅ Filosofia "Assistida": LLM tem permissão de **não saber**. Atinge limite → gera questionário estruturado para humano e pausa pilar afetado.
- ✅ Detalhe da arquitetura em 4 camadas, HITL, ConflictDetector, KPIs: skill `gca-personas-engine`.

---

## §5. OCG — fonte única de verdade

### §5.1. Regras invariantes

- ✅ OCG nasce do questionário aprovado.
- ✅ OCG é evolutivo e auditável.
- ✅ **OCG só expande quando recebe informação de valor. Nunca contrai por análise.**
- ✅ Ingestão ruim ou conflitante → **quarentena**, **não afeta OCG**.
- ✅ Módulos não podem assumir defaults invisíveis quando OCG incompleto: bloquear ou exigir complementação.
- ✅ Toda mudança gera versionamento e trilha de auditoria.

### §5.2. Reversão por deleção legítima (MVP 34, 2026-05-03)

Complementa — **não viola** — a regra "OCG não contrai por ingestão". Quando GP soft-deleta `ingested_documents` (smoke fixture, erro de upload, PII em LGPD, doc obsoleto):

- ✅ Endpoint `DELETE /api/v1/projects/{pid}/ingestion/{did}?reason=manual|lgpd|smoke_cleanup`
- ✅ Retorna **202 Accepted** + `revert_job_id`
- ✅ Soft-delete imediato (`deleted_at IS NOT NULL`)
- ✅ Celery job recompute OCG ignorando o doc
- ✅ Versão OCG incrementa com `change_type='REVERT_DOCUMENT_DELETE'`
- ✅ Audit event `DOCUMENT_REVERTED` em `audit_log_global` (hash chain íntegro)
- ⚠ LGPD parcial: `pii_fields`, `parecer` JSONB permanecem (DT-086)

### §5.3. Cascata para `file_type='questionnaire'` (MVP 35, 2026-05-03)

Quando doc deletado é o IngestedDocument sintético do questionário técnico:
- `TechnicalQuestionnaire.status` → `archived`
- `Questionnaire.approved` → False
- `setup_status.questionnaire_approved` → False
- Pipeline n8n bloqueado até novo questionário
- Frontend redireciona para `/settings?tab=questionario`

### §5.4. Pipeline canônico de setup (NESTA ORDEM)

1. **Repositório Git** configurado
2. **Chave LLM** válida e validada
3. **Questionário técnico** APROVADO E SUBMETIDO

### §5.5. Validação canônica do Questionário (2 camadas)

- **Camada 1 — RulesEvaluator** (`backend/app/services/questionnaire_validation/`): 30 regras DSL JSON em 5 temas. Stateless, determinístico, <50ms.
- **Camada 2 — LLM sanity check** (apenas no submit): detecta incoerências semânticas. Falha → bloqueia submit (sem fallback silencioso).

### §5.6. Gate de maturidade do CodeGen

CodeGen ganha gate em 3 níveis (entry points HTTP + start_scaffold_run async):
- `is_blocking=true` → 409 `block_level=hard_block`
- `overall_score < 60` → 409 `block_level=insufficient`
- `overall_score < 95` → 409 `block_level=immature`

✅ Liberado quando `overall_score >= 95` AND `is_blocking=false`.

> **Princípios canônicos** (GP, 2026-05-02):
> - "OCG não sobrescreve, não contrai. Só cresce com informação útil. Informação inútil é descartada."
> - "CodeGen só é liberado quando OCG está maduro, com >=95% de contexto."

---

## §6. Gatekeeper — 7 pilares + CONF bloqueante

| Pilar | Score | Persona principal |
|---|---|---|
| P1 | Business | GP, NEG |
| P2 | Rules/Compliance | CONF (**BLOQUEANTE <60**), LGPD |
| P3 | Features | UX, UI |
| P4 | NFRs (Non-Functional) | QA |
| P5 | Architecture | ARQ, DEV |
| P6 | Data | DBA |
| P7 | Security | SEG |

### §6.1. CONF é blocker
Score CONF <60 bloqueia ingestão e libera quarentena. Não aceita override automático. Apenas humano (GP+Admin dupla assinatura) pode aceitar risco.

### §6.2. Política de RNF_CONTRACTS (MVP 23)
Cada módulo no `RNF_CONTRACTS` do OCG declara: latency_p95, rate_limit, CWEs obrigatórios, regulações (LGPD/GDPR), disponibilidade. Validação estática (grep por middleware/decorator) pós-CodeGen.

---

## §7. Pontos arquiteturais — portas únicas

> Detalhes técnicos (assinaturas, paths) em `GCA_TECHNICAL_REFERENCE.md §4`.

### §7.1. Resolução de provider de IA
**Porta:** `AIKeyResolver.resolve_project_provider_chain(db, project_id)`  
**Config:** `project_settings`, `setting_type='llm'`. UI: Settings > IA.

❌ Proibido instanciar `AnthropicLLMClient`, `OpenAIClient`, `DeepSeekClient`, `GrokClient`, `OllamaClient` diretamente em rotas, services ou personas.  
❌ Proibido `provider = "anthropic"` chumbado em código.  
❌ Proibido fallback automático entre providers em falha de auth.  
✅ Resolver retorna vazio → `raise HTTPException(400, "Projeto sem LLM configurado. Abra Settings > IA")`.

### §7.2. Secrets e tokens
**Portas:** `VaultService.store_secret` / `get_secret`.  
**Cipher:** Fernet. Master key em `/var/lib/gca/secrets/fernet.key`. Prefixo: `fernet:v1:`.  
**Senhas temporárias:** `generate_temporary_password()` (10 chars, 1 maiúscula, 1 dígito, 1 especial).

⚠ `store_secret` commita internamente — testes que o chamam dentro de `session.begin()` quebram. Use sessões separadas.  
❌ Proibido logar secret em DEBUG, comentário, mensagem de erro ou response body.

### §7.3. RBAC — listagem de membros
✅ Filtra `is_active AND joined_at IS NOT NULL`. Use `is_active_integrated_member()`.  
❌ Filtrar só por `is_active` inclui convite pendente como membro ativo (vaza dado).

### §7.4. OCG operacional
✅ Toda decisão arquitetural/funcional/código **lê o OCG antes** e **atualiza depois**.  
❌ Pular leitura porque "a mudança é pequena" — proibido.

---

## §8. Pipeline Personas (n8n)

### §8.1. Fluxo canônico
1. **Ingestão** (FastAPI) → cria `ingested_documents` row
2. **Trigger n8n** via webhook `/webhooks/ingestion-complete`
3. **Auditor (AUD)** classifica documento + roteia
4. **Fan-out paralelo** para 11 especialistas (workflows n8n independentes)
5. **Redis accumulator** agrega scores
6. **Webhook callback** `/webhooks/ocg-result` retorna ao FastAPI
7. **OCGUpdaterService.update_ocg_from_arguider** atualiza OCG (delegação obrigatória, MVP 31)

### §8.2. Regras n8n
- Cada nó precisa `alwaysOutputData=true` (regra dura).
- If/Switch typeVersion=2.2; cada condição precisa UUID `id` e operator `filter.operator.equals`.
- INSERT sem RETURNING esvazia item — adicionar Code node após para restaurar payload.

### §8.3. Lixo descartado
PersonaOutput inválido (G4 reprovou) **não entra** no merge cumulativo, mas fica em `ocg_individual` com `status='failed'` para auditoria.

---

## §9. Regras duras de implementação

- Não antecipar feature de MVP futuro.
- Não expandir RBAC além de 5 papéis.
- Não promover documento histórico a contrato de implementação.
- Não reescrever arquitetura quando correção cirúrgica resolver.
- Não hardcodar provedor de IA.
- Não assumir que todo fluxo precisa usar mesma IA.
- Não permitir modelo barato/local tomar decisão crítica sozinho.
- Não avançar para próximo MVP enquanto gate da fase atual estiver fechado.

---

## §10. Constraint de escopo

### §10.1. Faça EXATAMENTE o solicitado
- Oportunidade de melhoria não-solicitada → comentário TODO, não implementar.
- Antes de criar arquivo >150 linhas: peça confirmação de escopo.
- Pergunte se precisa de X, Y, Z antes de assumir.

### §10.2. Alucinação = bloqueado
- Não adicionar logs estruturados sem solicitação explícita.
- Não criar fixtures não pedidas.
- Não refatorar código vizinho.
- Não assumir "melhorias óbvias" — diga que viu a oportunidade.

### §10.3. Aplicação
§10 aplica a TODO ciclo, dentro ou fora de MVP ativo. Violação = implementação silenciosa (proibida por §0). Em dúvida entre "faz" e "pergunta": **pergunta**.

---

**Fim do GCA_SPECIFICATION.md**
