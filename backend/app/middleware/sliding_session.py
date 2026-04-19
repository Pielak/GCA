"""DT-066 — Sliding session middleware (ASGI puro).

Durante atividades longas (ex: ingestão de documento com fallback entre
providers IA, que pode levar 2-10 min), o usuário fica parado na UI
olhando a barra de progresso. Se o JWT expirar nesse intervalo, o próximo
poll cai em 401 e o axios redireciona pra /login — a tela fica em branco
e o usuário perde o contexto do que estava acompanhando.

Solução: a cada resposta autenticada de sucesso, se o token está perto
de expirar (< SLIDING_RENEW_THRESHOLD_SECONDS restantes), emite um token
novo com mesma payload e `exp` renovado. O novo token viaja no header
`X-Access-Token-Renewed`; o axios do frontend pega e sobrescreve o
localStorage. Enquanto o usuário estiver ativo (mesmo que passivamente,
via polling de progresso), a sessão nunca cai.

Implementação em ASGI puro (não `BaseHTTPMiddleware`) porque o wrapper
de Starlette quebra o event loop do asyncpg em testes e em handlers que
abrem `async with AsyncSessionLocal()` dentro do request.

Limites:
  - Só renova em respostas 2xx/3xx — 4xx/5xx não estendem sessão.
  - Só renova se o token é válido (payload decodificável).
  - Só renova tokens de acesso (type != "refresh").
  - Não renova se o token foi emitido há < SLIDING_MIN_AGE_SECONDS.
"""
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.core.security import create_access_token, verify_token

logger = structlog.get_logger(__name__)

SLIDING_RENEW_THRESHOLD_SECONDS = 10 * 60
SLIDING_MIN_AGE_SECONDS = 30
RENEWED_HEADER = "X-Access-Token-Renewed"


def _extract_bearer_token(headers_raw):
    """Extrai token Bearer de headers ASGI (lista de tuplas de bytes)."""
    for name, value in headers_raw:
        if name.lower() == b"authorization":
            try:
                text = value.decode("latin-1")
            except Exception:
                return None
            parts = text.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
            return None
    return None


def _build_renewed_token(token: str) -> str | None:
    """Decide se renova e, se sim, retorna novo token."""
    payload = verify_token(token)
    if not payload:
        return None
    if payload.get("type") == "refresh":
        return None

    exp_ts = payload.get("exp")
    if not exp_ts:
        return None

    now_ts = datetime.now(timezone.utc).timestamp()
    seconds_remaining = exp_ts - now_ts
    if seconds_remaining <= 0 or seconds_remaining > SLIDING_RENEW_THRESHOLD_SECONDS:
        return None

    iat_ts = payload.get("iat")
    if iat_ts is not None:
        if (now_ts - iat_ts) < SLIDING_MIN_AGE_SECONDS:
            return None

    new_payload = {k: v for k, v in payload.items() if k not in ("exp", "iat")}
    new_payload["iat"] = int(now_ts)
    try:
        return create_access_token(new_payload)
    except Exception as exc:
        logger.warning("sliding_session.renew_failed", error=str(exc))
        return None


class SlidingSessionMiddleware:
    """Middleware ASGI que intercepta send para injetar header de
    renovação quando aplicável."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        token = _extract_bearer_token(scope.get("headers", []))
        if not token:
            await self.app(scope, receive, send)
            return

        new_token_holder = {"token": None, "status": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                new_token_holder["status"] = status_code
                if 200 <= status_code < 400:
                    new_token = _build_renewed_token(token)
                    if new_token:
                        new_token_holder["token"] = new_token
                        headers = list(message.get("headers", []))
                        headers.append((RENEWED_HEADER.encode("latin-1"), new_token.encode("latin-1")))
                        # Adiciona expose-headers pra navegador liberar leitura
                        # se o CORS global estiver off ou não cobrir esse header.
                        found_expose = False
                        for idx, (k, v) in enumerate(headers):
                            if k.lower() == b"access-control-expose-headers":
                                existing = v.decode("latin-1")
                                if RENEWED_HEADER.lower() not in existing.lower():
                                    headers[idx] = (
                                        k,
                                        f"{existing}, {RENEWED_HEADER}".encode("latin-1"),
                                    )
                                found_expose = True
                                break
                        if not found_expose:
                            headers.append((
                                b"access-control-expose-headers",
                                RENEWED_HEADER.encode("latin-1"),
                            ))
                        message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if new_token_holder["token"]:
            logger.info(
                "sliding_session.renewed",
                status=new_token_holder["status"],
                new_ttl_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            )
