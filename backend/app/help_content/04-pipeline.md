# Pipeline canônico do GCA

Sequência de etapas pela qual um projeto passa do questionário inicial até a entrega. É **orientado a eventos**: cada etapa lê o OCG, opera, atualiza o OCG, emite evento na auditoria e dispara a próxima (ou aguarda ação humana).

```
[Externo]                           [Admin]               [GP]                   [GP/Dev/Tester/QA]
┌───────────────┐   aprovação    ┌──────────┐   OCG    ┌──────────────┐   ingestão/dev  ┌───────────────┐
│ Questionário  │ ─────────────▶ │ Projeto  │ ────────▶│ OCG /         │ ────────────────▶│ CodeGen / QA /│
│ externo (49Q) │                │ criado   │          │ Gatekeeper /  │                  │ Docs / Release│
└───────────────┘                └──────────┘          │ Arguidor      │                  └───────────────┘
                                                        └──────────────┘
```

## 1. Questionário externo

- Link público com prazo de 5 dias.
- Wizard em 2 passos com 49 perguntas técnicas em 7 blocos:
  - A.1 Identidade, A.2 Escopo, A.3 Frontend, A.4 Backend, A.5 Dados, A.6 IA/Segurança, A.7 Testes.
- Cada pergunta tem tooltip explicativo e opção "N/A" quando aplicável.
- Alternativa: PDF editável para preenchimento offline + upload.
- Validação antes de submeter (campos obrigatórios + formato).
- Ao submeter, o Admin é notificado por email.

## 2. Aprovação pelo Admin

- Admin acessa `/admin/projects` → lista de pendentes.
- Revisa as respostas submetidas.
- Escolhe **Aprovar** ou **Rejeitar**.
- Rejeitar exige motivo obrigatório (fica no histórico).
- Aprovar provisiona: organização + projeto + convite ao GP (email com link).

## 3. Geração do OCG — 8 agentes de IA

Disparada automaticamente após a aprovação, em segundo plano. O pipeline tem 8 agentes:

```
                     Agente 0
                     Analyzer
                     (classifica as 49 respostas por pilar)
                     ↓
    ┌──────┬───────┬──────────┬────────┬────────┬────────┬────────┐
    ↓      ↓       ↓          ↓        ↓        ↓        ↓        ↓
   P1     P2      P3         P4       P5       P6       P7
   Caso   Compl.  Escopo     NFRs     Arq.     Dados    Seg.
   Neg.   Reg.                                                    (paralelo)
    ↓      ↓       ↓          ↓        ↓        ↓        ↓
    └──────┴───────┴──────────┴────────┴────────┴────────┴────────┘
                     ↓
                     Agente 8
                     Consolidator
                     (OCG final + composite score + status)
```

Cada agente de pilar devolve: score de 0 a 100, nível de aderência, se é bloqueante e achados (severidade + descrição + recomendação).

Fallback determinístico: se o LLM falhar em algum campo, o Consolidator preenche com heurísticas baseadas no questionário. Nenhuma seção do OCG fica vazia por falha de IA.

## 4. Gatekeeper

Avalia o OCG recém-gerado:

- **Regras de bloqueio**:
  - `P2 < 70` (compliance insuficiente) → **BLOCKED**.
  - `P7 < 70` (segurança insuficiente) → **BLOCKED**.
- **Regras de aprovação**:
  - Score composto `≥ 90` → **READY**.
  - Score composto `≥ 75` → **NEEDS_REVIEW**.
  - Score composto `< 75` → **AT_RISK**.
- Thresholds e pesos dos pilares são configuráveis pelo Admin no dashboard.
- Rastreia items: gaps, show_stoppers, poor_definitions, improvement_suggestions, módulos candidatos.
- Reavalia automaticamente quando o OCG muda por ingestão, resposta do Arguidor ou consolidação manual.

GP acessa tudo em `/projects/:id/gatekeeper`.

## 5. Ingestão de documentos complementares

GP pode ingerir documentos adicionais para enriquecer o contexto:

- **Formatos aceitos**: PDF, DOCX, XLSX, PNG, JPG, MD.
- **Tamanho máximo**: 50 MB por arquivo.
- **Drop zone** em `/projects/:id/ingestion`.
- Pipeline assíncrono com barra de progresso: `queued → extracting_text → analyzing → updating_ocg → regenerating_backlog → completed`.

### Extração rica por tipo

- **DOCX**: tabelas estruturadas + parágrafos + cabeçalhos/rodapés.
- **PDF**: campos de formulário AcroForm + texto pesquisável + OCR via LLM Vision para PDFs scan-only.
- **XLSX**: tabelas preservando estrutura + fórmulas → texto.
- **Imagens (PNG/JPG)**: OCR via LLM Vision.

### Quarentena automática de PII

Se o documento contém CPF, CNPJ, cartão de crédito ou telefone BR, é **automaticamente retido** antes de tocar o OCG. GP decide:

- **Liberar** — reconhece que o contexto precisa dessa informação.
- **Descartar** — documento não entra no sistema.

Validações de PII:
- CPF / CNPJ / cartão: validados por mod-11 ou Luhn (não disparam em números aleatórios).
- Telefone BR: regex + contexto (não dispara em sequências numéricas como IDs, timestamps, coordenadas).

### Efeito da ingestão no OCG

| Qualidade do documento | Efeito |
|---|---|
| Válido e complementar | **EXPAND** — enriquece seção, aumenta confidence |
| Parcial | **UPDATE** — atualiza marcando lacunas |
| Conflitante com estado atual | **CONTRACT** — reduz confidence, marca conflito |
| Contém PII | **BLOCK** — quarentena; OCG não é tocado |
| Invalida stack declarada | **CONTRACT** — P5/P6 caem + achado crítico |
| Segurança ausente (P7 < 70) | **BLOCK** — status BLOCKED, pipeline para |
| Compliance ausente (P2 < 70) | **BLOCK** — idem |

## 6. Arguidor

Após ingestão ou quando o Gatekeeper detecta lacunas, o Arguidor emite **perguntas dirigidas** ao GP:

- Cada pergunta vira um item pendente no Gatekeeper.
- GP em `/projects/:id/arguider` responde com texto (evidência opcional).
- Pode **ignorar com motivo** se a pergunta não se aplica.
- A resposta alimenta o OCG de volta: expand, update ou contract dependendo do que foi dito.

## 7. Backlog e Roadmap automáticos

Qualquer mudança relevante no OCG dispara:

- Recálculo do **backlog** — lista de itens de trabalho derivada do `STACK_RECOMMENDATION`, `DELIVERABLES` e `DATA_MODEL`.
- **Roadmap** com módulos em 8 categorias: Foundation, Auth, Data, Business, Infra, UI, Integration, Compliance.
- Detalhamento sob demanda de cada módulo (geração via modelo local).
- Curadoria para módulos críticos (geração via modelo premium).
- Plano de deploy exportável em Markdown.

## 8. CodeGen

Nove linguagens com scaffold determinístico a partir do OCG:

- Java com Spring Boot ou Quarkus
- Kotlin com Spring Boot
- Go (chi + pgx)
- C# com ASP.NET Core
- PHP com Laravel
- Node.js com NestJS ou Express
- **C++ com CMake + GoogleTest**

Python fica em modo LLM-only (sem scaffold determinístico; o LLM compõe).

- **DDL** (schema + seed + migration) é injetado automaticamente a partir do modelo de dados do OCG — cobre PostgreSQL, MySQL, SQLite, SQL Server, Oracle e MongoDB.
- **Preview** do scaffold antes do commit — diff completo por arquivo.
- **Apply** cria commit no repositório Git do projeto com mensagem padrão.
- **Regeneração por arquivo** quando um módulo específico muda.
- **Docstrings obrigatórias** em todo código gerado.
- **Validação pós-geração**: pyflakes (Python), esprima (JS/TS), ast.parse (Python), cmake+gcc (C++).

Detalhes em [cap. 8 — Codegen](?section=08-codegen).

## 9. QA Readiness + Tester Review

- **Specs** de teste gerados automaticamente por módulo (unit, integration, E2E).
- Specs críticos (security, compliance) usam modelo premium.
- Tester aprova, rejeita ou edita o spec.
- Execução com timeout configurável; logs ficam gravados em JSONL por run.
- QA revisa a execução no gate `qa:approve` que libera o Release Bundle.
- Banner "Stale" aparece quando o OCG mudou depois da última geração do spec.

## 10. Documentação Viva + Release Bundle

- **Doc Viva** regenera a cada commit relevante do pipeline.
- Consolidação geral por modelo premium; por módulo via modelo local.
- Seção "Modelo de dados" embute o DDL gerado.
- **Release Bundle** é um pacote markdown com:
  - Versão do OCG no momento do release.
  - Commits incluídos.
  - Artefatos: schema.sql, seed.sql, migrations.
  - Evidência de testes executados.

## Propagação de eventos

Cada etapa do pipeline emite evento na auditoria encadeada. Admin filtra em `/admin/audit`; GP vê o pipeline do próprio projeto em `/projects/:id/audit`.

Eventos principais:

- Projeto: aprovado, rejeitado, status alterado.
- Questionário: submetido, aprovado, rejeitado.
- Ingestão: documento ingerido, documento quarentenado.
- Pipeline: Gatekeeper avaliou, Arguidor pergunta aberta, Arguidor resposta registrada.
- OCG: atualizado, revertido (rollback), consolidado.
- Backlog: regenerado.
- CodeGen: scaffold gerado, scaffold aplicado, arquivo regenerado, validação concluída.
- QA: execução requisitada, execução concluída.
- Doc Viva: atualizada.

## Ver também

- [OCG — Objeto de Contexto Global](?section=05-ocg) — fonte central do pipeline.
- [Codegen](?section=08-codegen) — detalhes das 9 linguagens e DDL.
- [Observabilidade](?section=09-observabilidade) — auditoria, saúde e métricas.
