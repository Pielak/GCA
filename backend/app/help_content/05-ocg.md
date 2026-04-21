# OCG — Objeto de Contexto Global

O **OCG** é a fonte única de verdade de um projeto no GCA. Não é um documento estático; é um objeto de estado que evolui com cada ingestão, resposta do Arguidor, reconsolidação ou rollback. Cada mudança fica registrada no histórico de deltas.

Princípio que governa o uso: **nenhum módulo do pipeline opera ignorando o OCG atual**. Se o OCG está incompleto, o módulo ou pede ao GP (via Arguidor), ou bloqueia.

## As 12 seções do OCG

| Seção | Para que serve |
|---|---|
| `PROJECT_PROFILE` | Metadados do projeto (nome, slug, tipo, criticidade, classificação), derivados do questionário. |
| `PILLAR_SCORES` | Os 7 pilares (P1–P7) com score de 0 a 100, nível de aderência, se é bloqueante e contagem de achados. |
| `COMPOSITE_SCORE` | Score composto: `{ overall, is_blocking, status }`. Status possível: READY, NEEDS_REVIEW, AT_RISK, BLOCKED. |
| `STACK_RECOMMENDATION` | Stack recomendada por camada: backend (linguagem + framework + tipo), frontend (stack + linguagem), database (engine + perfil), cache, messaging, deployment. **É a seção mais consumida pelo CodeGen.** |
| `CRITICAL_FINDINGS` | Achados críticos extraídos dos agentes dos pilares (severidade `critical`). |
| `TESTING_REQUIREMENTS` | Tipos de teste exigidos, cobertura alvo, ferramentas. Alimenta os specs do Tester Review. |
| `COMPLIANCE_CHECKLIST` | Itens de LGPD, GDPR, compliance setorial. Alimenta módulos e Gatekeeper. |
| `DELIVERABLES` | Entregáveis esperados por categoria (doc, code, test, process, config, other). Base do Definition of Done. |
| `ARCHITECTURE_OVERVIEW` | Estilo arquitetural, componentes, fluxo de dados, modelo de execução (Cloud, On-premises, Híbrido). |
| `RISK_ANALYSIS` | Riscos classificados como alto, médio ou baixo, com mitigação sugerida. |
| `APPROVAL_STATUS` | Status consolidado: APPROVED / NEEDS_REVIEW / AT_RISK / BLOCKED. |
| `DATA_MODEL` | Modelo de dados derivado: engine, tabelas, FKs, dados de seed, warnings. Alimenta o DDL generator. |

Junto vai o `context_health` — `{ depth, confidence, quality }` — que flui com as operações de expand e contract.

## Versionamento e histórico

- Cada projeto tem **um OCG atual** em banco (linha única).
- Cada mudança relevante gera entrada em `ocg_delta_log` com:
  - versão de origem e destino
  - campos que mudaram (diff)
  - resumo da mudança
  - autor (usuário que disparou)
  - fonte da mudança (`document_ingestion`, `arguider_response`, `consolidation`, `rollback`, `manual_edit`, `pillar_agent`)
  - snapshot completo da versão (base para rollback)
  - timestamp

A versão atual é incrementada a cada mudança; o histórico inteiro vive no delta log.

## Regras de expand / contract

Uma entrada boa **expande** o OCG (confidence sobe, seções ficam mais ricas). Entrada ruim **contrai** (confidence desce, conflito fica marcado). É assim:

| Qualidade da entrada | Efeito |
|---|---|
| Documento válido e complementar | **EXPAND** — enriquece seção, sobe confidence |
| Documento parcial | **UPDATE** — atualiza com lacunas marcadas em `CRITICAL_FINDINGS` |
| Documento conflitante | **CONTRACT** — reduz confidence, marca conflito |
| Documento com PII | **BLOCK** — quarentena; OCG não é tocado até o GP decidir |
| Documento que invalida stack | **CONTRACT** — P5 (arquitetura) e P6 (dados) caem + achado crítico novo |
| Segurança insuficiente (P7 < 70) | **BLOCK** — status BLOCKED; pipeline para |
| Compliance ausente (P2 < 70) | **BLOCK** — idem |

A contração existe para o sistema ser **honesto**: se a base tem conflito, o pipeline para e exige correção em vez de seguir gerando código sobre premissa errada.

## Operações que você vai usar no dia-a-dia

### Ver o OCG atual

`/projects/:id/ocg` — página com as 12 seções renderizadas, a versão corrente e o `context_health`.

### Ver uma versão antiga (snapshot)

Na mesma página, linha do tempo de versões. Clicar em uma versão mostra o snapshot daquele momento, somente leitura.

### Rollback — voltar para uma versão anterior

Se uma ingestão ou resposta causou uma piora inesperada, é possível reverter:

- Botão **"Rollback para esta versão"** no item da timeline.
- Cria uma **nova versão** com o conteúdo da versão alvo (não apaga histórico).
- Registra na auditoria como `OCG_ROLLED_BACK` com `version_from`, `version_to` e `restored_from`.
- Só funciona para versões que tenham snapshot persistido.

### Consolidate — recalcular o score composto

Às vezes você edita pilares manualmente ou importa scores externos. Para que o `COMPOSITE_SCORE` e o `status` acompanhem:

- Botão **"Consolidar OCG"** na página do OCG.
- Recalcula `overall_score`, `is_blocking` e `status` a partir dos `PILLAR_SCORES` aplicando as regras de bloqueio (P2/P7 < 70) e as faixas de aprovação (≥90 READY, ≥75 NEEDS_REVIEW, resto AT_RISK).
- Idempotente: se nada mudou, o sistema informa "sem alteração".
- Registra na auditoria como `OCG_CONSOLIDATED`.

### Regenerar OCG do zero

Em caso extremo (questionário corrigido, mudança grande de escopo), é possível descartar todo o histórico e refazer:

- Botão **"Regenerar OCG"** na página do OCG.
- Pede confirmação dupla — a operação é destrutiva (perde o delta history).
- Dispara o pipeline dos 8 agentes novamente a partir do questionário atual.

## Propagação automática

Quando o OCG muda relevantemente, o sistema propaga:

- **Stack mudou** → backlog de módulos regenera, CodeGen marca arquivos como desatualizados.
- **Compliance mudou** → itens de compliance recalculados.
- **Testes mudaram** → specs marcados como stale.
- **Qualquer mudança** → backlog regenera, doc viva incrementa, evento entra na auditoria.

Tudo isso roda em segundo plano (fila Celery). A request que disparou a mudança não bloqueia.

## Billing por operação

Cada chamada de IA durante operações do OCG registra em `ai_usage_log`: provedor, modelo, operação, tokens de entrada, tokens de saída, custo em USD, projeto.

- GP vê o consumo do próprio projeto em `/projects/:id/metrics`.
- Admin vê agregado de todos os projetos em `/admin/metrics`.

## Regras importantes para o usuário

- **Compartimentalização**: cada projeto tem seu OCG próprio. Dados de um projeto não entram no OCG de outro.
- **Separação de chaves de IA**: chaves globais (Admin) são separadas das chaves do projeto (GP). Operações do pipeline administrativo usam as globais; operações do dia-a-dia do projeto usam as do projeto.
- **Alta criticidade exige modelo premium**: consolidação de OCG, arbitragem de conflitos e decisões arquiteturais não rodam com modelo local sozinho.
- **OCG nunca fica corrompido**: se a IA falhar no meio do pipeline, o documento fica pendente, o OCG não é tocado.

## Ver também

- [Pipeline canônico](?section=04-pipeline) — onde o OCG nasce.
- [Codegen](?section=08-codegen) — principal consumidor do `STACK_RECOMMENDATION` e `DATA_MODEL`.
- [Solução de problemas](?section=10-troubleshooting) — OCG travado, rollback sem snapshot, etc.
