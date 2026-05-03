---
name: gca-ocg-engine
description: Use this skill when working with the GCA Objeto de Contexto Global (OCG) — including pillar scores, Gatekeeper evaluation, document ingestion, Arguidor responses, backlog regeneration, propagation to dependent modules, or any OCG state machine event. Defines the canonical lifecycle, expansion rules, schema, and propagation behavior. Triggered by mentions of OCG, ingestion pipeline, pillar P1-P7, composite score, document quarantine, or backlog vivo.
---

# Skill: GCA OCG Engine

> Detalhe operacional do **Objeto de Contexto Global** no GCA. Regras invariantes resumidas vivem em `CLAUDE.md §2.4` e no `GCA_CANONICAL_CONTRACT.md §5`. Esta skill é fonte detalhada para qualquer trabalho que toque o OCG.

---

## 1. Definição central

O **OCG** é a fonte única de verdade do projeto no GCA.

- Nasce do **questionário externo aprovado** (score ≥ 90 após 8 fases de Technology Verification).
- É **evolutivo e auditável**: toda mudança gera versionamento e trilha de auditoria via hash chain.
- É **derivado, não autônomo**: não é IA. É inteligência calculada a partir do estado do projeto.
- É **compartimentalizado por projeto**: documento de um projeto **nunca afeta outro**.

---

## 2. Regra fundamental (REGRA ATUAL — substitui versão anterior)

> **O OCG só expande quando recebe informação de valor. Nunca contrai.**

Esta é a regra atual e revoga o comportamento anterior de "contrair confiança".

### 2.1. Comportamento por evento

| Situação | Ação sobre o OCG | Estado pós-evento |
|---|---|---|
| Boa ingestão (documento válido + relevante) | **Expande** contexto | Mais dados, maior confiança |
| Ingestão parcial (relevante + lacunas) | **Atualiza** com lacunas marcadas | Confiança mantida |
| Dados conflitantes com OCG existente | **Quarentena** do documento; OCG **não é tocado** | OCG inalterado; conflito sinalizado para resolução humana |
| Documento reprovado pelo Arguidor | **Bloqueia** propagação; OCG **não é tocado** | OCG inalterado |
| Gatekeeper aprova módulo | **Expande** score e status | Habilita CodeGen |
| QA falhou | **Sinaliza** falha em `audit_findings`; OCG **não contrai** confiança automaticamente | OCG inalterado em estrutura; status QA sinalizado |
| Pilar com score < 70 (P2 ou P7) | **Expande** com finding crítico; status muda para BLOCKED | OCG cresce em metadado de bloqueio, não contrai dado |

**Princípio:** quando o input é ruim, o caminho é **rejeição/quarentena**, não degradação do OCG. O OCG é um repositório de informações de valor, não um termômetro de confiança que sobe e desce.

### 2.2. Por que essa mudança

A versão anterior tratava "contração de confiança" como behavior do motor. Isso gerava ambiguidade: documento ruim podia "rebaixar" OCG real, criando estado intermediário difícil de auditar e propenso a regressão silenciosa. Com a regra atual:

- O OCG é **monotonicamente crescente em informação**.
- Toda exclusão é **explícita** (versionamento), nunca implícita por degradação.
- Quarentena vira o caminho único para input problemático — auditável, reversível.
- Backlog vivo recalcula sobre dado bom apenas.

---

## 3. Ciclo de vida

```
Questionário Externo (49Q)
    ↓
Technology Verification (8 fases, 50+ validações)
    ↓
Aprovação Admin (score ≥ 90)
    ↓
Pipeline OCG (8 agentes IA — pré-existente, não confundir com "8 personas")
    ├── Agent 0: Analyzer — classifica respostas por pilar
    ├── Agents 1-7: Pillar Specialists (paralelo) — analisa cada pilar
    └── Agent 8: Consolidator — consolida OCG final em PT-BR
    ↓
OCG Persistido (versionado, auditado)
    ↓
Eventos de expansão (ingestão de documentos válidos, Arguidor, Gatekeeper aprovações)
    ↓
Propagação (backlog vivo, módulos dependentes, documentação)
```

---

## 4. Máquina de estado (regra atual)

```yaml
OCG_ENGINE:
  type: event_driven_state_machine
  invariant: monotonic_information_growth   # ← regra nova

  events:
    - QUESTIONNAIRE_APPROVED         # Cria OCG inicial
    - DOCUMENT_INGESTED              # Expande se válido; senão → quarentena
    - DOCUMENT_QUARANTINED           # Bloqueia propagação. OCG NÃO é tocado.
    - GATEKEEPER_EVALUATED           # Atualiza scores e findings (expansão de metadado)
    - ARGUIDER_RESPONSE_REGISTERED   # Enriquece OCG com análise (expande)
    - CODEGEN_COMPLETED              # Registra artefato gerado
    - QA_EXECUTION_COMPLETED         # Atualiza estado de qualidade (expande findings)
    - BACKLOG_REGENERATED            # Recalcula backlog do OCG

  behaviors:
    expand_context:    # Boa ingestão → mais dados
    update_context:    # Atualização parcial (ex: score de pilar)
    block_propagation: # Documento em quarentena → não afeta OCG
    # contract_context: REMOVIDO — não existe mais como behavior do motor.
```

---

## 5. Schema do OCG (v1.0.0)

### 5.1. Seções obrigatórias

| Seção | Descrição | Origem |
|---|---|---|
| `PROJECT_PROFILE` | Perfil: nome, tipo, criticidade, arquitetura, modelo execução | Questionário + Analyzer |
| `PILLAR_SCORES` | Scores P1-P7 com nível de aderência e contagem de findings | Pillar Specialists |
| `COMPOSITE_SCORE` | Score composto ponderado + status de aprovação | Consolidator |
| `STACK_RECOMMENDATION` | Stack: frontend, backend, banco, cache, infra, observabilidade, segurança | Consolidator + Questionário |
| `CRITICAL_FINDINGS` | Achados críticos que impedem ou arriscam o projeto | Pillar Specialists |
| `TESTING_REQUIREMENTS` | Testes: tipos, cobertura, ferramentas, cenários | Consolidator + Questionário |
| `COMPLIANCE_CHECKLIST` | Conformidade: LGPD, GDPR, auditoria, PCI-DSS | P2 Compliance + Consolidator |
| `DELIVERABLES` | Entregáveis esperados do projeto | Consolidator |
| `ARCHITECTURE_OVERVIEW` | Visão arquitetural: estilo, componentes, fluxo de dados | P5 Architecture + Consolidator |
| `RISK_ANALYSIS` | Riscos alto/médio/baixo com mitigações e responsáveis | Consolidator |
| `APPROVAL_STATUS` | Status: READY, NEEDS_REVIEW, AT_RISK, BLOCKED | Consolidator |

### 5.2. Saúde do contexto

```json
{
  "context_health": {
    "depth": "initial | expanded",
    "confidence": 0.0,
    "ingestion_quality": "good | partial | rejected",
    "last_event": "DOCUMENT_INGESTED",
    "version": 3,
    "delta_count": 2
  }
}
```

> Note que `depth` não inclui mais `"contracted"`. O valor `confidence` é monotonicamente não-decrescente — cresce com expansão; permanece estável quando há quarentena.

---

## 6. Pesos e regras de aprovação dos pilares

| Pilar | Nome | Peso | Bloqueante se < 70 |
|---|---|---|---|
| P1 | Caso de Negócio | 10% | Não |
| P2 | Regras e Compliance | 15% | **Sim** (LGPD/GDPR) |
| P3 | Funcionalidades e Escopo | 20% | Não |
| P4 | Requisitos Não-Funcionais | 20% | Não |
| P5 | Arquitetura e Design | 15% | Não |
| P6 | Dados e Persistência | 10% | Não |
| P7 | Segurança e Proteção | 10% | **Sim** |

**Fórmula**: `composite = P1×10% + P2×15% + P3×20% + P4×20% + P5×15% + P6×10% + P7×10%`

### 6.1. Regras de status

1. P7 < 70 → **BLOCKED** (falhas de segurança impedem prosseguimento).
2. P2 < 70 e LGPD/GDPR se aplica → **BLOCKED**.
3. composite ≥ 90 → **READY** (aprovado para CodeGen).
4. composite ≥ 75 → **NEEDS_REVIEW** (lacunas menores, prosseguir com cautela).
5. composite < 75 → **AT_RISK** (lacunas significativas, recomenda correções).

---

## 7. Propagação automática

| Mudança no OCG | Módulos impactados | Comportamento |
|---|---|---|
| AI profile | Ingestão, Arguidor, CodeGen, LiveDocs | Revalidar provedor, mascaramento, budget |
| Stack / repositório | CodeGen, QA, LiveDocs, Legado | Trocar templates, imagem base, testes |
| Compliance | Ingestão, quarentena, auditoria, QA | Aplicar bloqueios, mascaramento, retenção |
| QA profile | QA Readiness, dashboards | Regerar plano de testes, executor, indicadores |

---

## 8. Backlog vivo

O backlog é **derivado do OCG**. Sempre que o OCG expande:

- Backlog é recalculado (itens auto-gerados substituídos, manuais preservados).
- Módulos dependentes são reavaliados.
- Documentação viva é regenerada.

### 8.1. Categorias

| Categoria | Itens esperados |
|---|---|
| `modules` | Módulos a construir, especificações técnicas, design |
| `tests` | Unitários, integração, E2E, segurança, performance |
| `compliance` | Normas regulatórias, auditorias, LGPD/GDPR |
| `security` | Requisitos de segurança, vulnerabilidades, certificações |
| `agile` | Histórias de usuário, épicos, bugs, dívida técnica |
| `other` | Requisitos não-funcionais, documentos de design |

---

## 9. Endpoints canônicos (referência)

### 9.1. OCG — Geração e consulta

| Método | Endpoint | Descrição | Permissão |
|---|---|---|---|
| `POST` | `/api/v1/agents/ocg/generate` | Pipeline completo 8 agentes → gera OCG | Admin/GP autenticado |
| `GET` | `/api/v1/projects/{id}/ocg` | OCG mais recente do projeto | Membro do projeto |
| `GET` | `/api/v1/ocg/{ocg_id}` | OCG por ID específico | Membro do projeto |

### 9.2. Ingestão — Expansão do OCG

| Método | Endpoint | Descrição | Permissão |
|---|---|---|---|
| `POST` | `/api/v1/projects/{id}/ingestion` | Upload de documento | GP/Dev |
| `GET` | `/api/v1/projects/{id}/ingestion` | Listar documentos ingeridos | Membro |
| `GET` | `/api/v1/projects/{id}/ingestion/{doc_id}/status` | Status de análise (Arguidor) | Membro |

### 9.3. Endpoints planejados

| Método | Endpoint | Descrição |
|---|---|---|
| `PUT` | `/api/v1/projects/{id}/ocg` | Atualizar OCG manualmente (apenas expansão; rejeição registrada como quarentena) |
| `GET` | `/api/v1/projects/{id}/ocg/history` | Histórico de versões do OCG |
| `GET` | `/api/v1/projects/{id}/ocg/delta-log` | Log de mudanças (quem, quando, o quê) |
| `POST` | `/api/v1/projects/{id}/ingestion/{doc_id}/release` | Liberar documento da quarentena (com justificativa) |

---

## 10. Compartimentalização

- Cada projeto tem seu próprio OCG — documentos de um projeto **não afetam outro**.
- Chaves de IA do **pipeline OCG** (camada Admin) são **separadas** das chaves do **projeto** (camada GP).
- Admin configura chaves globais usadas **apenas** para avaliação do questionário externo.
- GP configura suas próprias chaves de IA nas Settings do projeto (vault criptografado via `VaultService`).
- Toda query de dado de OCG inclui `project_id` no WHERE. Sem exceção.

---

## 11. Proibições explícitas no manuseio do OCG

- ❌ Implementar behavior `contract_context` — foi removido pela regra atual.
- ❌ Reduzir `confidence` automaticamente em resposta a evento. Confiança só sobe ou se mantém.
- ❌ Sobrescrever versão anterior do OCG sem versionamento. Toda mudança cria nova versão.
- ❌ Propagar mudança de OCG sem registrar evento na trilha de auditoria.
- ❌ Permitir que documento em quarentena influencie cálculo de score ou backlog.
- ❌ Misturar OCG entre projetos por engano. Toda função que recebe `ocg` recebe também `project_id` para validação.

---

*Skill atualizada: 2026-04-30. Substitui o documento histórico `OCG_DEFINICAO.md` (movido para `docs/_deprecated/`).*
