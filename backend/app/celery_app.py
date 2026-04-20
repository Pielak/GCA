"""MVP 13 Fase 13.1 — Celery app canônico do GCA.

Configuração do broker (Redis DB 1) + result backend (Redis DB 2).
Workers rodam em processo separado via `docker compose up gca-celery-worker`
(container dedicado usando a mesma imagem do backend, com comando
`celery -A app.celery_app worker`).

Convenções:
- Uma task trivial `ping` exposta para healthcheck/smoke
  (`celery inspect ping` ou `app.celery_app.ping.delay().get()`).
- Timezone alinhado à env `BACKUP_TIMEZONE` da Fase 12.2 (default
  America/Sao_Paulo). Evita ambiguidade em logs e retries agendados.
- Fases 13.2-13.4 do MVP 13 adicionarão tasks específicas do pipeline
  (Arguider, OCG Updater, auto-CodeGen). Por ora, só o scaffold.

Broker URLs:
- `CELERY_BROKER_URL` tem prioridade se setado explicitamente.
- Senão, deriva de `REDIS_URL` adicionando `/1` (DB 1 = broker).
- Fallback final: `redis://redis:6379/1`.
"""
from __future__ import annotations

import os

from celery import Celery


def _resolve_broker_url() -> str:
    """Retorna a URL do broker Celery.

    Ordem de precedência:
    1. `CELERY_BROKER_URL` explícita.
    2. Deriva de `REDIS_URL` trocando o DB pela `/1`.
    3. Default `redis://redis:6379/1`.
    """
    explicit = os.environ.get("CELERY_BROKER_URL")
    if explicit:
        return explicit
    base = os.environ.get("REDIS_URL")
    if base:
        # Troca o último path component (DB index) por /1.
        if "/" in base.rsplit("//", 1)[-1]:
            prefix, _db = base.rsplit("/", 1)
            return f"{prefix}/1"
        return f"{base}/1"
    return "redis://redis:6379/1"


def _resolve_result_backend_url() -> str:
    """Result backend: mesma Redis, DB 2 — isolado do broker."""
    explicit = os.environ.get("CELERY_RESULT_BACKEND")
    if explicit:
        return explicit
    base = os.environ.get("REDIS_URL")
    if base:
        if "/" in base.rsplit("//", 1)[-1]:
            prefix, _db = base.rsplit("/", 1)
            return f"{prefix}/2"
        return f"{base}/2"
    return "redis://redis:6379/2"


def _resolve_timezone() -> str:
    """Usa mesma lógica da Fase 12.2 sem circular import."""
    tz = (os.environ.get("BACKUP_TIMEZONE") or "").strip()
    if not tz:
        return "America/Sao_Paulo"
    try:
        import pytz
        pytz.timezone(tz)
        return tz
    except Exception:
        return "America/Sao_Paulo"


celery_app = Celery(
    "gca",
    broker=_resolve_broker_url(),
    backend=_resolve_result_backend_url(),
    include=[
        # MVP 13 Fase 13.1 — pacote raiz.
        "app.tasks",
        # MVP 13 Fase 13.3a — task de ingestão (primeiro ponto migrado).
        "app.tasks.pipeline",
    ],
)

# Configuração canônica (documentada inline para não precisar abrir docs).
celery_app.conf.update(
    # Timezone alinhado à instância (BACKUP_TIMEZONE).
    timezone=_resolve_timezone(),
    enable_utc=False,
    # Serialização: JSON. Evita pickle (risco de segurança).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Result expiration: 1 hora (suficiente pra poll; não encher Redis).
    result_expires=3600,
    # Retry policy default (Fase 13.4 ajusta por task).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_default_max_retries=3,
    # DLQ: tasks que esgotam retries vão para `celery_dlq`.
    task_routes={
        "app.tasks.*": {"queue": "celery"},
    },
    # Eager mode: configurável via env para testes.
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "").lower() in ("1", "true", "yes"),
    task_eager_propagates=True,
)


# ─── Task canônica de smoke / healthcheck ─────────────────────────────


@celery_app.task(name="app.celery_app.ping")
def ping() -> str:
    """Smoke test de conectividade broker↔worker.

    Uso manual:
        python -c "from app.celery_app import ping; print(ping.delay().get(timeout=5))"
    Retorna "pong" quando o worker está funcionando. Falha com timeout
    se o broker estiver inalcançável ou o worker offline.
    """
    return "pong"


# ─── Helpers de health check (MVP 13 Fase 13.2) ───────────────────────


def check_broker_connection(timeout: float = 2.0) -> dict:
    """Verifica conectividade com o broker Redis.

    Retorna dict com status + detalhes. Não levanta exceção — designed
    para ser chamado do endpoint /health sem derrubar a resposta quando
    o broker está fora.

    {
      "broker": "redis://redis:6379/1",
      "reachable": bool,
      "error": str | None,
    }
    """
    broker_url = celery_app.conf.broker_url
    result = {"broker": broker_url, "reachable": False, "error": None}
    try:
        # Usa a conexão do Celery diretamente (mesmo client do worker).
        with celery_app.connection_for_read() as conn:
            conn.ensure_connection(max_retries=0, timeout=timeout)
            result["reachable"] = True
    except Exception as e:  # noqa: BLE001 — queremos capturar tudo
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def check_workers_alive(timeout: float = 1.0) -> dict:
    """Verifica se há worker(s) Celery online respondendo a `inspect ping`.

    Retorna dict com status + contagem. Quando o broker está fora, pula
    o ping e reporta `reachable=False`. Quando não há worker, reporta
    `workers=0`.

    {
      "workers": int,
      "nodes": list[str],
      "error": str | None,
    }
    """
    result: dict = {"workers": 0, "nodes": [], "error": None}
    try:
        insp = celery_app.control.inspect(timeout=timeout)
        pong = insp.ping() or {}
        result["nodes"] = sorted(pong.keys())
        result["workers"] = len(pong)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
    return result
