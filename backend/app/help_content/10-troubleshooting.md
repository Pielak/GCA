# Solução de problemas

FAQs frequentes + diagnósticos canônicos.

## Backend / infra

### Backend não sobe

**Sintoma**: `docker compose up -d` termina mas `gca-backend` fica reiniciando.

**Diagnóstico**:

```bash
docker logs gca-backend --tail 50
```

**Causas comuns**:

- `DATABASE_URL` ausente ou inválido → `.env` não montado / não exportado.
- Alembic migration pendente → `docker exec gca-backend alembic upgrade head`.
- `JWT_SECRET` ou `VAULT_MASTER_KEY` não definido → gerar e adicionar ao `.env`.
- Porta 8000 em uso por outro processo → `lsof -i :8000` ou ajustar port mapping.

### Celery worker reporta `unhealthy`

Antes do MVP 17: healthcheck usava `celery@gca-celery-worker` literal, mas o hostname real do container é o ID curto. Mitigação em `docker-compose.yml`: healthcheck usa `CMD-SHELL` com `celery@$$HOSTNAME`.

Se persistir após MVP 17:

```bash
docker exec gca-celery-worker celery -A app.celery_app inspect ping -d celery@$HOSTNAME
```

Se responder `pong` mas healthcheck falhar, confirme que o `docker-compose.yml` foi sincronizado (regra dura CLAUDE.md §12):

```bash
docker compose up -d
```

Sem argumentos. Sincroniza a stack com o compose.

### Flower não responde em `:5555`

DT-077 herdada de MVP 14.10: serviço declarado mas não subiu na primeira tentativa.

```bash
docker compose up -d celery-flower
```

Valida:

```bash
curl -fsS http://localhost:5555/ | head -5
```

### Backup não executa no horário configurado

Conferir timezone (MVP 12.2 — env `BACKUP_TIMEZONE`). Fallback para UTC se valor inválido.

```bash
docker exec gca-backend python -c "
from app.core.config import settings
print('BACKUP_TIMEZONE:', settings.BACKUP_TIMEZONE)
"
```

## Ingestão

### Documento preso em `processing` para sempre

Antes do MVP 13 Fase 13.3 + DT-073: ingestão disparava `asyncio.create_task` sem watchdog — se o backend reiniciava (`uvicorn --reload`), task morria e doc ficava preso.

Mitigação:

- **MVP 13**: pipeline migrado pra Celery com ACK late + retry bounded + DLQ.
- **DT-073 watchdog**: `recover_zombie_documents(threshold=30min)` roda no startup, recupera docs em `processing` > 30min e marca como `error` com mensagem clara.

Se persistir com Celery, confira:

```bash
# Worker ativo?
docker exec gca-backend python -c "from app.celery_app import celery_app; print(celery_app.control.inspect(timeout=1).ping())"

# Task está na fila?
docker exec gca-redis redis-cli -n 1 KEYS "celery*"

# DLQ?
curl -H "Authorization: Bearer <admin-token>" http://localhost:8000/api/v1/admin/celery/dlq
```

Delete do doc com `status=processing`: endpoint `/reanalyze` (MVP 14.6) reseta o status antes de re-enfileirar — usa isso em vez de delete direto se quiser reprocessar.

### Documento quarentenado por PII que não tem

**Antes do MVP 8 DT-028** (pré-2026-04-17): regex promíscuo `\b\(?\d{2}\)?\s?\d{4,5}-?\d{4}\b` pegava qualquer sequência numérica (coordenadas, IDs, timestamps, scores) e disparava quarentena.

Mitigação em DT-028: telefone BR agora valida contexto. CPF/CNPJ/cartão validam mod-11/Luhn desde DT-015.

Se ainda quarentenar falso-positivo, o GP pode liberar manualmente em `/projects/:id/ingestion` → detalhe do doc → "Liberar quarentena".

### PDF com AcroForm não extrai campos

**Antes do MVP 8 DT-018**: `flatten` do PDF removia a AcroForm silenciosamente; extração entregava análise incompleta.

Mitigação: pré-flight agora rejeita com 422 + mensagem orientando a abrir em **Adobe Reader / Foxit / Okular** e salvar com **Ctrl+S** (não "Salvar como…" nem "Imprimir → PDF"). O salvar preserva AcroForm.

## OCG

### OCG preso em `pending_analysis` após questionário aprovado

Pipeline de geração (8 agentes) rodou mas algo falhou antes do save. Causas e fixes já mitigados:

- **DT-023** — parse JSON do LLM robusto (code fences + balanced braces).
- **DT-024** — `exec_model` → `exec_models` (multi-select).
- **DT-025** — strings hardcoded alinhadas com options do schema.
- **DT-032/033** — Arguidor/OCG Updater usavam provider hardcoded.
- **DT-036** — criticidade do provider validada (não aceita modelo médio pra alta criticidade).
- **DT-039** — retry via `/reanalyze` disponível no UI.

Se persistir: `/projects/:id/ingestion` → botão "Reanalisar" dispara regeneração. Ou Admin pode regenerar OCG completo em `/projects/:id/ocg` → "Regenerar OCG" (com confirmação).

### OCG em `BLOCKED` sem motivo óbvio

Regra canônica §5: `P2 < 70` (compliance) OU `P7 < 70` (segurança) → BLOCKED. Veja `/projects/:id/ocg` → PILLAR_SCORES.

Fix: ingerir documento que responda os gaps de compliance/segurança, OU responder Arguidor com evidência.

### Rollback falhou com "Snapshot não disponível"

Delta log antigo sem `ocg_snapshot` preenchido. Rollback só funciona para versões em que o delta log persistiu snapshot completo (MVP 14.7 introduziu).

Alternativa: regenerar OCG do questionário (perde delta history, mas recria do zero).

## Providers IA

### 401 / 403 do provider

Token inválido ou expirado. `/projects/:id/settings` → aba IA do projeto → botão "Validar" em cada provedor. Se 401, atualizar a chave.

Regra dura §6.3: se o projeto tem DeepSeek configurado e você faz consolidação de OCG (alta criticidade), o sistema **não aceita** silenciosamente — DT-036 exige validação. Configure um provider premium (Anthropic, OpenAI) no projeto, OU o Admin da instância configura no `/admin` e o pipeline cai no global para alta criticidade.

### 429 rate limit

Fallback automático entre providers está ativo desde MVP 4 DT-064:

- Cadeia ordenada: default primeiro, depois validados por data, inválidos por último.
- Fallback em rate limit, quota, 5xx, timeout, conn refused, DNS, SSL, EOF, 401/403.
- Notificação `UserNotification` (severity=warning) para GPs + Admins quando idx > 0.

## CodeGen

### Scaffolder retorna None / linguagem não suportada

`dispatch_scaffold` retorna `None` quando a linguagem não tem template determinístico (Python, Rust, Ruby, Swift, Zig, etc). Caller cai no fluxo LLM-only — o scaffold vem do LLM, sem garantia de estrutura.

Se for linguagem esperada mas com `language` escrito diferente (ex: "Python3", "node"), o dispatch não normaliza 100% — aliases atuais são: `c++/cpp/cplusplus` (MVP 16), `csharp/c#/cs/.net/dotnet`, `node.js/nodejs/node/typescript/javascript`. Demais devem usar a grafia do enum canônico.

Futura extensão de linguagens depende de abrir MVP específico (C++ foi MVP 16; Rust, Swift, Python-scaffold ficariam parked até autorização).

### `cmake` falha no scaffold C++

CMake 3.14+ é obrigatório (FetchContent estabilizado). Container `gcc:13-bookworm` já traz via `apt-get install cmake ninja-build` no Dockerfile gerado. Se rodar local sem container, instalar `cmake >= 3.14`.

Erro comum: `-G Ninja` sem ninja instalado → `apt install ninja-build` ou remover `-G Ninja` (cai em Makefile).

## Help / documentação

### Aba Ajuda mostra "Conteúdo em construção"

Versão pós-MVP 18 Onda 1 (Fases 18.1+18.2) tinha esse placeholder. Na Onda 2 (Fases 18.3+18.4+18.5) o conteúdo real foi carregado em `backend/app/help_content/*.md`. Se ainda aparecer placeholder:

- Confirmar que MVP 18 Onda 2 foi deployado: `ls backend/app/help_content/*.md | wc -l` deve retornar **10**.
- Conferir que o router `/api/v1/help/section/{id}` retorna 200:
  ```bash
  curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/help/section/01-visao-geral
  ```

### Busca do help retorna lista vazia

**Antes da Fase 18.4**: endpoint `/search` retornava `{backend: "stub", results: []}`.

**Após 18.4**: FTS5 indexou os 10 capítulos; busca por termo retorna snippets. Se ainda vazio, o termo pode não existir no corpus — tente busca por termo canônico (OCG, RBAC, CodeGen, Gatekeeper).

## Contato / suporte

Para problemas não cobertos:

1. **Incidente técnico** → `/projects/:id/incidents` → novo ticket com severidade + descrição + anexos.
2. **Equipe Sustentação** da instância → `/admin/support` (se for Admin).
3. **Audit log** → `/admin/audit` filtrando por tipo de evento (ex: `DOCUMENT_QUARANTINED` pra achar quarentenas recentes).

## Ver também

- [Observabilidade](?section=09-observabilidade) — endpoints de diagnóstico.
- [Instalação & setup](?section=02-instalacao) — pós-install validation.
- [Área Administrativa](?section=06-admin) — ferramentas de admin para diagnóstico.
