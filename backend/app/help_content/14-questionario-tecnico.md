# Questionário Técnico Retroativo — dívida informacional zerada

O Arguidor pode acumular dezenas de perguntas em rounds de análise — GP abrir cada card e responder online não é realista. O **Questionário Técnico Retroativo** transforma a pilha de gaps pendentes em PDF editável navegável por seção canônica, baixado, respondido offline e reingerido pelo fluxo padrão da Ingestão.

Uma vez ingerido, o processo é **ativo/passivo**: o upload é o gatilho (passivo), mas a partir dele o sistema cascateia sozinho — resolve items no Gatekeeper, promove dívidas no backlog, regenera backlog/roadmap, marca scaffolds/testes stale.

## Seções canônicas

As 5 seções dividem o trabalho pelos papéis que respondem:

| Chave | Público | Cobre |
|---|---|---|
| `governance` | GP / Tech Lead | Decisões, stakeholders, priorização, casos de negócio |
| `architecture` | Arquitetura | Padrões, camadas, dependências, modelo de dados (P5/P6) |
| `capacity` | Capacity / SRE | Latência, throughput, disponibilidade, recuperação (P4) |
| `security` | Segurança | CWE, vault, auth, dados sensíveis (P7) |
| `legal` | Legal / Compliance | LGPD, GDPR, setorial, jurisdição (P2) |

Mapeamento canônico pilar → seção: P1/P3 → `governance`; P2 → `legal`; P4 → `capacity`; P5/P6 → `architecture`; P7 → `security`.

## Tipos de campo no PDF

O gerador escolhe o tipo de input pelo **shape do gap**, não pelo operador:

- **2 opções** → dropdown (escolha única)
- **3+ opções** → checkboxes (múltipla escolha) + campo "Outros (descreva abaixo)"
- **Sugestões abertas** → checkboxes + "Outros"
- **Sem opções** → textfield livre

Ao final de toda seção há sempre o campo **Complementos** (multi-linha) — qualquer informação adicional relevante entra como documento separado processado pelo Arguidor como texto livre.

## Fluxo canônico

1. **Gatekeeper** mostra pilares `blocker` ou `warning`. Cada pilar traz botão **"Baixar questionário"** — abre a seção canônica correta.
2. **Arguidor** traz o painel **Questionários Técnicos Retroativos** com as 5 seções e contadores: `N pendentes`, `N dívidas` (itens com ≥2 rounds ignorados).
3. GP clica "PDF" da seção → browser baixa `questionario_<section>_<project>.pdf`.
4. Abre em Adobe Reader / Foxit / Preview, preenche, salva.
5. Upload pelo fluxo normal da **Ingestão**. O detector reconhece o PDF por assinatura canônica (IDs de campo `Q_<uuid>`) e pula o pipeline LLM — aplica **síncrono** e **determinístico**.

## Onde o cascateamento acontece

Após o upload, se ao menos 1 item foi resolvido, dívida promovida ou complementos preenchidos:

1. Items respondidos → `GatekeeperItem.status=resolved` + `resolution_note` canônica.
2. Items oferecidos e ignorados → `skip_count++`. No `≥ 2` → `BacklogItem` `category="info_debt"`, `priority="critical"`.
3. Audit `RNF_QUESTIONNAIRE_APPLIED` emitido com `resolved_codes[]`, `info_debt_promoted[]`, `complements_document_id?`.
4. Celery `propagate_questionnaire_impact_task` encadeia: `PropagationService.propagate` → backlog regenera (audit `BACKLOG_REGENERATED`) → `reevaluate_gatekeeper`.
5. Complementos viram `IngestedDocument` `txt` com `arguider_status=pending` — processado pelo Arguidor pipeline padrão.

**Sem polling.** O gatilho é o upload; uma vez disparado, cadeia roda sem perguntar permissão entre etapas (regra `feedback_ativo_passivo_pipeline`).

## Dívida informacional persistente

Perguntas não respondidas não somem. Cada round guarda `offers_count` e, quando GP ignora, `skip_count` incrementa. Threshold canônico: **≥ 2 rounds ignorados = dívida informacional**.

- Item na lista volta ao topo do próximo PDF (ordenação por `skip_count DESC, offers_count DESC, code`).
- `BacklogItem` fica como rastro histórico (não removemos quando o GP finalmente responde — auditoria precisa do passado).
- Badge `N dívidas` no painel indica quantas perguntas da seção já atingiram o threshold.

## Compartimentalização §2.2

- PDF de projeto A não toca item de projeto B (parser valida `project_id` antes de aplicar).
- UUID inexistente, malformado ou resolved → silent skip (`skipped_not_found` / `skipped_blank` no report).
- Cross-project é registrado apenas em warning log, nunca aplica.

## Regras duras

- **PDF é contrato**: sem field `Q_<uuid>`, detector retorna False e o documento segue pro fluxo LLM normal.
- **Field oculto `Q__OFFERED_IDS`** carrega o CSV dos UUIDs oferecidos naquele round — sem isso, não há como calcular `skipped`.
- **Cascata é best-effort**: falha de enqueue Celery é logada, mas NÃO quebra o upload.
- **LLM zero no caminho crítico**: aplicação é determinística (grep estruturado de AcroForm).

## Ver também

- [OCG — Objeto de Contexto Global](?section=05-ocg) — onde os gaps vivem antes de virarem questionário.
- [Contratos RNF](?section=13-contratos-rnf) — outra forma de estruturar requisitos não-funcionais.
- [Pipeline canônico](?section=04-pipeline) — ordem das etapas, incluindo Arguidor.
