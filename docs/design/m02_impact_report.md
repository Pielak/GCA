# M02 — Relatório de Impacto (Domain Defaults Resolver)

**Data:** 2026-04-24
**Status:** MVP M02 entregue (Tasks 1-9 + relatório)
**Execução:** subagent-driven-development com modelo Haiku por task.

## Problema resolvido

M01 entrava em loop com perguntas sobre domínio público (prazos prescricionais, campos RIPD, rate-limit DataJud, defaults de segurança). O user gastava tempo respondendo o óbvio; o Arguidor nunca dava o gap como resolvido. Sintoma recorrente em dogfood: gaps com "7ª ingestão sem avanço".

## Arquitetura aplicada

- **Tabela `applied_defaults`** — histórico com `gap_id`, `decision_key`, `source_citation`, `contested_at/value`.
- **KB canônica** em Python (12 defaults validados contra fonte pública) por categoria (legal/compliance/security/technical/architecture).
- **Resolver determinístico** via substring match + filtro por `applies_when` (tags do projeto inferidas do OCG).
- **Hook no Arguidor** filtra gaps resolvíveis ANTES de persistir. Resolvidos saem do `result_json["gaps"]` → não viram `module_candidates`, não viram pergunta M01, não punem pilar.
- **M01 defesa em profundidade**: `generate_iteration` consulta `applied_defaults` e filtra gaps com decision_key já aplicada.
- **Router** `/applied-defaults` (GET list + POST contest).
- **Aba "Decisões Automáticas"** no sidebar do projeto: lista agrupada por categoria, contest inline.

## KB inicial (12 defaults canônicos)

| Categoria | Key | Fonte |
|---|---|---|
| legal | `retention.civil_cases` | CC art. 206 §5º I |
| legal | `retention.labor_cases` | CLT art. 11 |
| security | `retention.access_logs` | ISO 27001 A.8.15 + Marco Civil art. 15 |
| legal | `retention.deactivated_user_data` | LGPD Art. 16 + OAB |
| compliance | `compliance.ripd_structure` | LGPD Art. 38 |
| compliance | `compliance.pii_masking` | CGU 01/2021 + CNJ 121/2010 |
| security | `security.password_hashing` | OWASP + NIST SP 800-63B |
| security | `security.jwt_secret` | RFC 7519 + OWASP JWT |
| security | `security.icp_brasil_signing` | ITI + MP 2.200-2/2001 |
| technical | `technical.datajud_rate_limit` | CNJ TdU item 3.13 |
| technical | `technical.datajud_endpoint_base` | Portal DataJud CNJ |
| architecture | `architecture.sqlite_encryption` | SQLCipher + NIST SP 800-132 |

## Commits (10)

| Task | Commit | Descrição |
|---|---|---|
| 1 | `77418ff` | Migration 039 `applied_defaults` |
| 2 | `e9fa7e2` | Model `AppliedDefault` |
| 3 | `0483da8` | KB canônica (12 defaults) |
| 4 | `853242f` | Resolver (resolve_gap + list + contest + infer_tags) |
| 5 | `0ebbfc0` | Hook no Arguidor |
| 6 | `618bf94` | Router (list + contest) + main.py |
| 7 | `2109d4b` | M01 filtra gaps resolvidos |
| 8 | `a74006c` | 12 testes standalone (12/12 passing) |
| 9 | `b33a37b` | Aba frontend "Decisões Automáticas" |
| 10 | (este) | Relatório de impacto |

## Dogfood AJA (projeto 65cab180) — a medir após primeira ingestão pós-M02

| Métrica | Valor |
|---|---|
| Defaults aplicados na 1ª ingestão pós-M02 | _preencher_ |
| Gaps evitados no M01 (vs ciclo anterior sem M02) | _preencher_ |
| Delta OCG após aplicação | _preencher_ |
| Decisões contestadas pelo user em 1ª semana | _preencher_ |

Pra coletar as métricas:
```sql
-- Defaults aplicados no AJA
SELECT category, COUNT(*) FROM applied_defaults
WHERE project_id='65cab180-e00d-4eec-aaf2-fb4b5d0f4057'
GROUP BY category;

-- Decisões contestadas
SELECT decision_key, contested_at, contested_value FROM applied_defaults
WHERE project_id='65cab180-e00d-4eec-aaf2-fb4b5d0f4057'
  AND contested_at IS NOT NULL;
```

## Critérios de aceite atingidos

- ✓ Plan task-a-task entregue via subagent-driven com Haiku (10 tasks, 10 commits).
- ✓ Zero hardcode de provider IA (§6.2) — resolver é determinístico, não usa LLM.
- ✓ Pilares canônicos P1..P7 + categorias legal/security/technical/compliance/architecture consistentes end-to-end.
- ✓ PT-BR em código, commits, UI, logs, fontes citadas.
- ✓ Falha na resolução NUNCA bloqueia Arguidor ou M01 — try/except + fallback.
- ✓ Contestação preserva rastreabilidade (decision_value original mantido; contested_value adicionado).
- ✓ 12/12 testes standalone passing (respeita DT-034).
- ✓ Backend + frontend builds verdes.

## Pendências (DT-095 candidatas)

- KB com LLM-assisted matching (fuzzy, não só substring) — defaults que o user descreve com palavras não catalogadas não são detectados hoje.
- Expansão da KB: direito tributário, criminal, administrativo (hoje só cível+trabalhista).
- Propagar contestação pro Arguidor imediatamente (hoje só na próxima ingestão).
- Notificação push quando defaults novos aplicam (hoje só aparece na aba).
- Admin global: edição da KB via UI (sem deploy) pra o time do GCA manter.
- Integração com OCG Updater pra refletir ganho de compliance no score quando default é aplicado (hoje efeito é indireto via Arguidor sem o gap).
