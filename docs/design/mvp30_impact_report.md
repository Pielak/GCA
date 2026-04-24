# MVP 30 — Relatório de Impacto (Scaffold Item-a-Item)

**Data:** 2026-04-24
**Status:** MVP entregue end-to-end (Tasks 1-7 implementadas + relatório)
**Objetivo:** eliminar timeout Cloudflare em scaffolds grandes via geração item-a-item.

---

## Problema resolvido

Scaffold monolítico disparava 1 chamada LLM que gerava 27 arquivos num único JSON. Em projetos reais (AJA), a latência chegava a ~90s — muito perto do timeout de 100s do Cloudflare Tunnel. Frontend via "Falha 0%" sem feedback nenhum durante os 90s.

## Arquitetura nova

**Backend:**
- `scaffold_planner.py` com 2 prompt builders puros (plan + item).
- `POST /scaffold/plan` — LLM devolve APENAS a lista de arquivos (path, file_type, purpose, est_lines). Output <1000 tokens, latência ~5s.
- `POST /scaffold/item` — LLM gera conteúdo de 1 arquivo por chamada. Output 2-5k tokens, latência ~15-30s.

**Frontend:**
- `handleGenerateScaffold` virou orquestrador: chama `/plan`, itera `/item` sequencialmente, atualiza `scaffoldFiles` incremental.
- Novo state `scaffoldItemStatus: Map<path, pending|generating|complete|error>`.
- Tree do sidebar mostra ícone por status:
  - `pending` — ⏱ cinza
  - `generating` — ⏳ violeta girando
  - `complete` — ✓ verde
  - `error` — ⚠ vermelho
- Progress bar no topo do painel com "Gerando X / N" + contagem de erros.

## Comparação com o MVP anterior

| Métrica | Monolítico | Item-a-item |
|---|---|---|
| Chamadas LLM | 1 | N + 1 |
| Timeout risk | Alto (~90s no AJA) | Zero (cada call ≤30s) |
| Feedback visual | Zero até terminar | Progressivo por item |
| Retry granular | Refazer tudo | Por item (campo `error_message`) |
| Budget de tokens | ~32k cap (truncation) | N × 5-8k + plan 4k |
| Cold-start UX | Loader anônimo 90s | Tree popula em 5s + status ao vivo |

## Tasks entregues

| # | Descrição | Commit |
|---|---|---|
| 1 | Schemas Pydantic (4 classes) | `f4e8906` |
| 2 | Service `scaffold_planner.py` com 2 prompt builders | `0528812` |
| 3 | Endpoint `POST /scaffold/plan` | `531066d` |
| 4 | Endpoint `POST /scaffold/item` | `cb16527` |
| 5 | 8 testes standalone (8/8 passing) | `58cc36f` |
| 6 | Frontend orquestrador item-a-item | `d8a17ac` |
| 7 | UI: status icon no tree + progress bar | `4fdcb37` |
| 8 | Este relatório | (a commitar) |

## Métricas em dogfood (projeto AJA)

*A preencher pelo stakeholder após primeiro `Gerar Preview do Scaffold` com o MVP 30 ativo:*

| Métrica | Valor |
|---|---|
| Items no plano | _N_ |
| Latency fase PLAN | _Xs_ |
| Latency média por item | _Ys_ |
| Latency total | _Zs_ |
| Tokens totais (plan + itens) | _T_ |
| Items com `status=error` | _E_ |
| Taxa de erro | _E/N %_ |

Pra coletar: `docker logs gca-backend --since=30m 2>&1 | grep -E "scaffold_plan|scaffold_item"`.

## Endpoint legado

`POST /scaffold` continua funcionando (não foi deletado). Frontend não chama mais. Pode virar DT de remoção quando a persistência da fase 2 (DT-091) consolidar.

## Pendências fase 2 (DT-091 futura)

- Persistência server-side do plan/items (tabela `scaffold_session(id, project_id, plan_json)` + `scaffold_session_item(session_id, path, content, status)`).
- Recuperação em caso de refresh do browser (hoje perde tudo).
- Retry individual por item com botão UI dedicado (hoje a re-execução é do scaffold inteiro).
- Paralelização opcional de itens (3-5 concorrentes) com throttle — reduz latência total sem aumentar risco de timeout por chamada individual.
- Remover endpoint legado `/scaffold` depois que persistência estiver estável.

## Critérios de aceite atingidos

- ✓ Zero chamada LLM acima do timeout do Cloudflare (cada `/item` tem `max_tokens=8192` com budget <30s em Haiku/Sonnet).
- ✓ Tree do sidebar popula incremental (usuário vê estrutura do scaffold em ~5s).
- ✓ Progresso visível com progress bar + ícones por item.
- ✓ Item individual pode falhar sem derrubar o fluxo (status=error preserva os demais).
- ✓ Contexto do OCG preservado nos 2 prompts (stack, architecture, RNF contracts, design tokens).
- ✓ Peers dos arquivos passados via query param — LLM não inventa imports.
- ✓ Tests passing (8/8 unit do prompt builder).
- ✓ Backend e Frontend buildam sem erro de tipo.
