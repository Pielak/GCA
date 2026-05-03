---
name: gca-personas-engine
description: Use this skill when implementing or modifying the GCA persona-based validation system v2 — including the Auditor (8th persona), 7 specialists (GP/ARQ/DBA/DEV/QA/UX/UI), 4-layer architecture, human-in-the-loop questionnaires, ConflictDetector with deterministic + semantic rules, OCGConsolidator, prompt caching strategy, or KPI gates. Triggered by mentions of personas, persona_validator, Auditor, 4-layer pipeline, human-in-the-loop, HITL, ConflictDetector, OCGConsolidator, PERSONAS_V2_ENABLED feature flag, or DeepSeek prompt caching in the GCA context.
---

# Skill: GCA Personas Engine v2

> Sistema de validação assistida por personas com human-in-the-loop. Detalhe operacional. Regra resumida vive em `CLAUDE.md §3.5`. O TASK original (`docs/_deprecated/TASK_PERSONAS_V2_v1_3.md`) preserva instruções one-shot de execução; **esta skill consolida o que é DURADOURO** (especificação do sistema).

---

## 1. Filosofia operacional (não violar)

### 1.1. Princípio "Assistida"

O GCA é **Gestão de Codificação Assistida**. Não é um pipeline E2E (boi entra → churrasco sai). É um **protocolo de colaboração assíncrona** entre LLMs especialistas e humanos validadores.

Quando o LLM atinge o limite do que pode decidir com os insumos disponíveis, ele **para e pede socorro ao humano** — não improvisa, não alucina, não preenche para parecer competente.

Consequências arquiteturais:

1. **A LLM tem permissão explícita de não saber.** Cada persona pode declarar incerteza estruturada (categoria + severidade + ação sugerida) em vez de produzir resposta com baixa confiança.
2. **Cada especialista técnico tem par humano declarado.** Auditor é exceção (auditoria documental é trabalho interno do GCA, sem stakeholder humano natural).
3. **Pipeline tem pontos de pausa formais.** Sem aceite humano em perguntas `severity=blocker`, Gatekeeper bloqueia pilar afetado e Codegen não roda.
4. **Calibragem por tamanho de projeto.** Solo (GP responde tudo, com perguntas consolidadas), pequeno (equipe 2–4), grande (equipe 5+ com papéis específicos).

### 1.2. Princípios técnicos derivados

1. **Imutabilidade documental**: documento original em `documents` jamais é alterado; routing fica em `document_route_maps`.
2. **LLM-agnóstico**: nenhum provider hardcoded. Funciona com qualquer LLM configurado pelo cliente. Ver skill `gca-llm-resolver`.
3. **Provider-aware caching com graceful fallback**: ativa mecanismo nativo do provider quando disponível.
4. **Rastreabilidade total**: cada `persona_response` referencia chunks analisados; cada `question` referencia chunks que originaram a dúvida; cada conflito tem `rule_id` ou `detection_method=semantic`.
5. **Tratamento de erros estruturado**: padrão `GCAError` com `code`, `user_message`, `suggested_action`, `fallback_attempted`. Nenhum erro morre silenciosamente.
6. **Feature flag obrigatória**: `PERSONAS_V2_ENABLED` permite rollback de 1s. v1 preservado em `persona_validator_v1.py`.
7. **Testabilidade incremental**: cada fase tem critério de aceite isolado e pode ser deployada independentemente.

---

## 2. Diagnóstico do v1 (por que v2 existe)

Pipeline atual em `backend/app/services/persona_validator.py`:

- 5 personas (GP/ARQ/DBA/DEV/QA) leem o documento completo em paralelo.
- Documento de referência AJA: ~13.000 tokens (1.234 palavras em parágrafos + 7.116 em 47 tabelas).
- Input total por análise: 5 × 13.000 + 5 × 1.500 (prompts) ≈ 72.500 tokens.
- Latência: 45–60s (limitada pela persona mais lenta).
- Redundância: cada persona processa ~70% de conteúdo irrelevante.

### Problemas que v2 resolve

1. **Input redundante**: §16 (LGPD) só interessa GP/ARQ/DBA; §19 (Mapa de Telas) não interessa DBA.
2. **Sem cobertura UX/UI**: documentos com mockups e jornadas ficam sem revisor especializado.
3. **Cache de prompt não utilizado**: prompt da persona (~1.500 tokens, imutável) re-enviado integralmente toda análise.
4. **Sem detecção de conflitos cross-persona**: ARQ recomenda REST, DEV assume GraphQL — conflito só aparece tardiamente.
5. **Sem auditoria documental**: nenhuma persona valida a qualidade da especificação como entrega contratual.
6. **Sem human-in-the-loop**: LLM tenta responder tudo mesmo quando não tem insumo (alucina ou produz resposta vaga).
7. **Erros silenciosos**: falhas no pipeline não geram mensagem amigável nem fallback explícito.

---

## 3. Arquitetura em 4 camadas

```
┌─────────────────────────────────────────────────────────────────────┐
│  Camada 0 — Parser estrutural (Python puro, ~1-2s)                   │
│  python-docx / markdown-it-py / pypdf                                │
│  Output: lista de RawChunks (texto íntegro, ordenado, atômico)       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Camada 1 — Auditor (1 chamada LLM, ~10-15s)                         │
│  Persona "Auditor Documental Sênior" — 8ª persona do GCA             │
│  Recebe: lista completa de chunks                                    │
│  Produz 6 outputs:                                                   │
│    1. summary                  — visão executiva (~500 tokens)        │
│    2. chunk_tags               — multi-label por chunk                │
│    3. highlights               — atenção dirigida por persona         │
│    4. audit_findings           — OCG próprio (auditoria documental)   │
│    5. backlog_to_specialists   — incertezas resolvíveis por LLM       │
│    6. questionnaire_to_human   — perguntas para validador humano      │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────────┐ ┌────────────┐ ┌──────────────────────────┐
│  Camada 2 (Passada1)│ │ Audit OCG  │ │  Painel Perguntas        │
│  7 especialistas    │ │ vai 1ª     │ │  Pendentes               │
│  paralelos          │ │ seção do   │ │                          │
│  → tentative=true   │ │ OCG global │ │  Humanos respondem        │
│  + perguntas extras │ │            │ │  assincronamente          │
└─────────────────────┘ └────────────┘ └──────────────────────────┘
                              │
                              ▼ (após respostas humanas)
┌─────────────────────────────────────────────────────────────────────┐
│  Camada 2 (Passada 2) — Especialistas re-analisam                    │
│  Recebem mesmos chunks + respostas humanas integradas                │
│  → tentative=false (conclusões finais)                               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Camada 3 — ConflictDetector (Python) + OCGConsolidator (LLM)        │
│  Só executa após Passada 2 finalizada                                │
│  • 8 regras determinísticas auditáveis                               │
│  • LLM busca apenas conflitos sutis                                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Gatekeeper (existente) — bloqueia pilar se há blocker pendente     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Cobertura de personas (8 no total)

| Persona LLM | Tag | Responsabilidade | Par humano |
|---|---|---|---|
| **Auditor** | AUD | Auditoria documental + roteamento + briefing | (sem par — interno ao GCA) |
| Gerente de Projetos | GP | Escopo, viabilidade, ROI, stakeholders | Gerente do cliente |
| Arquiteto | ARQ | Stack, padrões, integrações, NFRs | Tech Lead |
| DBA | DBA | Modelo de dados, retenção, LGPD | DBA do cliente |
| Dev Sr. | DEV | Implementabilidade, dependências | Líder técnico |
| QA | QA | Testes, cobertura, BDD | QA Lead |
| UX | UX | Jornada, acessibilidade, microcopy | UX Designer |
| UI | UI | Design system, estados, responsividade | UI Designer |

**Modo solo** (1 humano declarado): todos os papéis humanos resolvem para GP automaticamente, com consolidação semântica de perguntas.

---

## 5. Pré-requisitos bloqueadores antes da Fase A

Antes de iniciar a primeira fase de implementação (Fase A — Parser + Auditor), os 5 pré-requisitos abaixo precisam estar validados. Falha em qualquer **BLOQUEADOR** registra `GCAError(SYS-002-FEATURE-DISABLED)` e impede execução.

| Tipo | ID | Item | Falha implica |
|---|---|---|---|
| 🔴 BLOQUEADOR | **P1** | Provider configurado suporta prompt caching de fato | Não prosseguir; trocar provider OU desativar KPI 4 |
| 🔴 BLOQUEADOR | **P2** | Critério operacional de paridade vs v1 definido e instrumentado | Não prosseguir; Fase E sem dente |
| 🔴 BLOQUEADOR | **P3** | Fluxo de resposta de questionário especificado (schema, API, UI, email) | Não prosseguir; Fase F sem destino |
| 🟡 RECOMENDADO | **P4** | Fallback heurístico do Auditor implementado | Prosseguir com débito técnico explícito |
| 🟡 RECOMENDADO | **P5** | `conflict_rules/` em submódulos isolados confirmado | Prosseguir; refatoração obrigatória na Fase D |

A decisão de prosseguir após falha em P4/P5 (recomendados, não bloqueadores) é do GP, registrada como dívida técnica em `GCA_MVP_PROGRESS.md`.

### 5.1. Sobre P1 — prompt caching

A v2 prevê redução de custo de até −81% via prompt caching automático do provider. Se a premissa de cache quebrar, a economia cai para −62% (cenário sem cache). Ainda positivo, mas muda matemática do KPI 4 (cache hit rate ≥ 25% como gate de rollback).

Validação obrigatória **empírica** antes de prosseguir: medir custo real de duas chamadas idênticas consecutivas com prompt grande (~4k tokens estável byte-a-byte). Cache hit deve cobrar ≤ 15% do custo de cache miss.

### 5.2. Sobre P2 — paridade com v1

"Não regredir" é critério vago. Definição operacional: **≥ 85% das respostas finais (pós-Passada 2) devem ter alinhamento semântico com a saída v1** em casos de teste com OCG conhecido. Métrica: similaridade de embedding ≥ 0.80 + revisão manual de 10% amostral.

### 5.3. Sobre P3 — fluxo de questionário

Decisão consolidada: pergunta gerada por persona vira `pending_question` em tabela própria → email para humano declarado → painel UI mostra perguntas pendentes → resposta integrada ao contexto da Passada 2. Detalhe completo do schema, API e templates: ver Fase F do TASK arquivado.

---

## 6. Visão das fases (referência)

| Fase | Escopo | Estimativa | Critério de aceite |
|---|---|---|---|
| **A** | Parser estrutural (3 chunkers) + Auditor com 6 outputs | 4–5 dias | Documento → 30–45 chunks + 6 outputs do Auditor; latência total < 18s |
| **B** | 7 especialistas em 2 passadas (tentative → final); processam backlog do Auditor; geram perguntas adicionais | 4–5 dias | Passada 1 produz `tentative=true` + perguntas; Passada 2 produz `tentative=false` |
| **C** | Personas UX e UI (novas) | 2 dias | OCG-parciais UX e UI específicos |
| **D** | ConflictDetector (8 regras determinísticas) + OCGConsolidator (semântico); só executa após Passada 2 | 3–4 dias | ≥1 conflito detectado com `rule_id` rastreável |
| **E** | Feature flag, KPIs com gates de rollback automático, métricas Prometheus | 2–3 dias | 5 KPIs verdes em staging por 7 dias |
| **F** | Sistema de questionários humanos (schema + API + lógica) | 4–5 dias | Modo solo, fallback em cascata, notificações email, timeout, deduplicação semântica funcionais |
| **G** | Padrão `GCAError` aplicado às fases anteriores (códigos AUD-*, QST-*, AUTH-*, etc.) | 2–3 dias | Nenhuma falha silenciosa; toda exceção tem mensagem amigável + ação sugerida |

**Total**: 20–24 dias úteis. Buffer adicional pode ser necessário se integração com Gatekeeper de 7 pilares exigir adaptações no `pillar_scores`.

Cada fase exige aceite formal do GP entre uma e outra (checkpoint humano).

---

## 7. KPIs com gates de rollback automático

Após deploy em staging, os 5 KPIs abaixo são monitorados continuamente. Falha sustentada de qualquer um por > 24h dispara rollback automático via feature flag `PERSONAS_V2_ENABLED=false`.

| KPI | Meta | Gate de rollback |
|---|---|---|
| 1. Latência total (p95) | < 18s | > 25s sustentado por 24h |
| 2. Taxa de sucesso (sem GCAError) | ≥ 98% | < 95% por 24h |
| 3. Paridade semântica vs v1 | ≥ 85% | < 75% por 24h |
| 4. Cache hit rate (P1 dependent) | ≥ 25% | < 15% por 48h |
| 5. Perguntas pendentes resolvidas | mediana < 24h | > 72h por 7 dias |

---

## 8. Conflict detection

### 8.1. Camada determinística (Python, 8 regras)

Regras vivem em `backend/app/services/personas/conflict_rules/`, **uma por arquivo**, isoladas para auditoria. Exemplos:

- `R001_arch_vs_dev_protocol.py` — ARQ recomenda REST + DEV assume GraphQL.
- `R002_dba_retention_vs_compliance.py` — DBA define retenção < requisito LGPD.
- `R003_qa_coverage_vs_complexity.py` — QA define cobertura inferior à complexidade do módulo.

Cada regra retorna `ConflictMatch(rule_id, severity, parties, evidence_chunks)` ou `None`.

### 8.2. Camada semântica (LLM)

Após camada determinística, OCGConsolidator (1 chamada LLM) busca conflitos sutis não capturados por regras. Output: `ConflictMatch(rule_id=None, detection_method='semantic', ...)`.

### 8.3. Circuit breaker do detector

Se taxa de erro do ConflictDetector > 20% em janela de 50 execuções, detector é desabilitado automaticamente e fallback é "sem detecção de conflito" — pipeline continua, conflitos ficam para revisão humana.

---

## 9. Tratamento de erros — códigos GCAError

Toda exceção no pipeline de Personas deve ser convertida em `GCAError` antes de subir. Nenhuma falha pode ser silenciosa.

Famílias de códigos:

| Família | Significado | Exemplos |
|---|---|---|
| `AUD-*` | Falhas no Auditor | AUD-001-PARSE-FAILED, AUD-002-LLM-TIMEOUT |
| `PER-*` | Falhas em especialistas | PER-001-CONTEXT-OVERFLOW, PER-002-INVALID-OUTPUT |
| `QST-*` | Falhas no sistema de perguntas | QST-001-NO-RESPONDER, QST-002-TIMEOUT-EXCEEDED |
| `CON-*` | Falhas no ConflictDetector | CON-001-RULE-LOAD-FAILED, CON-002-CIRCUIT-OPEN |
| `OCG-*` | Falhas no OCGConsolidator | OCG-001-MERGE-CONFLICT |
| `AUTH-*` | Falhas de autorização | AUTH-001-INVALID-RESPONDER |
| `LLM-*` | Falhas no provider | (ver skill `gca-llm-resolver`) |
| `SYS-*` | Falhas sistêmicas | SYS-002-FEATURE-DISABLED |

Toda `GCAError` tem: `code`, `user_message` (PT-BR), `suggested_action` (PT-BR), `fallback_attempted` (bool).

---

## 10. Rollback do v2 para v1

```bash
# Feature flag em settings
PERSONAS_V2_ENABLED=false

# Em runtime, o roteador escolhe:
if settings.PERSONAS_V2_ENABLED:
    return PersonaValidatorV2(...)
else:
    return PersonaValidatorV1(...)  # preservado em persona_validator_v1.py
```

Tempo de rollback: ≤ 1s (mudar variável de ambiente + restart dos workers Celery).

`persona_validator_v1.py` **não é deletado** mesmo após v2 estável em produção. Preserva caminho de regressão.

---

## 11. Proibições explícitas

- ❌ Implementar nova persona sem revisar a definição de filosofia "Assistida". Personas que "improvisam quando não sabem" violam o princípio.
- ❌ Hardcodar provider de LLM em qualquer persona ou no Auditor. Use `AIKeyResolver` (skill `gca-llm-resolver`).
- ❌ Pular o ConflictDetector "porque é rápido". Conflitos não detectados viram retrabalho de Codegen.
- ❌ Implementar Camada 3 (consolidação) antes de Passada 2 das especialistas estar finalizada.
- ❌ Permitir resposta humana parcial integrar Passada 2 sem flag explícita. Resposta incompleta = pilar permanece bloqueado.
- ❌ Deletar `persona_validator_v1.py` antes de v2 estar estável em produção por ≥ 30 dias.

---

*Skill criada: 2026-04-30. Origem: TASK_PERSONAS_V2 v1.3 + Pré-Fase A (movido para `docs/_deprecated/TASK_PERSONAS_V2_v1_3.md` como referência histórica de execução).*
