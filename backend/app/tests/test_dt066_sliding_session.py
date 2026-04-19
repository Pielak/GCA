"""DT-066 — Sliding session middleware.

Durante ingestões longas (2-10 min com fallback entre providers IA), o
usuário fica olhando a barra de progresso. Se o JWT expirar nesse
intervalo, o próximo poll falha em 401 e o frontend redireciona pra
/login — perda de contexto. A solução renova o token silenciosamente
em cada resposta autenticada de sucesso quando está perto de expirar.

Testes em dois níveis:
  - Unitário puro do middleware ASGI (scope/send fake) — não depende do
    conftest nem de DB.
  - Integração via sync_client em endpoints que não tocam DB, pra
    validar que o middleware está plugado no pipeline real.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.security import create_access_token, verify_token
from app.middleware.sliding_session import (
    RENEWED_HEADER,
    SlidingSessionMiddleware,
)


def _make_token(*, exp_delta_seconds: int, iat_delta_seconds: int | None = None, token_type: str | None = None) -> str:
    """Gera token com exp customizado."""
    payload: dict = {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "is_admin": False,
    }
    if token_type:
        payload["type"] = token_type
    if iat_delta_seconds is not None:
        payload["iat"] = int((datetime.now(timezone.utc) + timedelta(seconds=iat_delta_seconds)).timestamp())
    return create_access_token(payload, expires_delta=timedelta(seconds=exp_delta_seconds))


async def _run_middleware(token: str | None, status_code: int = 200) -> dict:
    """Roda o middleware contra um app fake ASGI e retorna headers da
    resposta capturados. Não abre HTTP real — pura simulação ASGI."""
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode("latin-1")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/fake",
        "headers": headers,
    }

    async def fake_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": b"{}",
        })

    captured = {"headers": None, "status": None}

    async def send_capture(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = message.get("headers", [])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    mw = SlidingSessionMiddleware(fake_app)
    await mw(scope, receive, send_capture)
    return captured


def _get_header(headers_list, name: str) -> str | None:
    name_bytes = name.lower().encode("latin-1")
    for k, v in headers_list or []:
        if k.lower() == name_bytes:
            return v.decode("latin-1")
    return None


# ============================================================================
# UNITÁRIOS — middleware ASGI puro
# ============================================================================

def test_token_with_plenty_of_time_is_not_renewed():
    """Token válido por 29 min — ainda longe do threshold de 10 min."""
    token = _make_token(exp_delta_seconds=29 * 60, iat_delta_seconds=-60)
    result = asyncio.run(_run_middleware(token))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_token_near_expiry_gets_renewed():
    """Token com 5 min restantes — dentro do threshold de 10 min."""
    token = _make_token(exp_delta_seconds=5 * 60, iat_delta_seconds=-120)
    result = asyncio.run(_run_middleware(token))
    new_token = _get_header(result["headers"], RENEWED_HEADER)
    assert new_token is not None, "middleware não renovou token perto de expirar"
    assert new_token != token

    new_payload = verify_token(new_token)
    assert new_payload is not None
    # Novo exp deve estar no futuro e depois do exp antigo
    assert new_payload["exp"] > int(datetime.now(timezone.utc).timestamp())

    # Header de expose-headers tem que listar o nome pro frontend conseguir ler
    expose = _get_header(result["headers"], "access-control-expose-headers") or ""
    assert "x-access-token-renewed" in expose.lower()


def test_4xx_response_does_not_renew():
    """Só 2xx/3xx renova. 4xx mantém o comportamento de erro do endpoint."""
    token = _make_token(exp_delta_seconds=2 * 60, iat_delta_seconds=-120)
    result = asyncio.run(_run_middleware(token, status_code=404))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_5xx_response_does_not_renew():
    """Erro interno também não estende sessão."""
    token = _make_token(exp_delta_seconds=2 * 60, iat_delta_seconds=-120)
    result = asyncio.run(_run_middleware(token, status_code=500))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_no_authorization_header_no_renew():
    """Request sem token — não há o que renovar."""
    result = asyncio.run(_run_middleware(token=None))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_expired_token_not_renewed():
    """Token já vencido não deve ser renovado — caso contrário sliding
    vira ressurreição infinita de sessão morta."""
    token = _make_token(exp_delta_seconds=-60, iat_delta_seconds=-600)
    result = asyncio.run(_run_middleware(token))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_refresh_token_not_renewed_as_access():
    """Se alguém mandar um refresh_token como Bearer, o middleware NÃO
    deve emitir access token renovado — seria escalação silenciosa."""
    token = _make_token(
        exp_delta_seconds=3 * 60,
        iat_delta_seconds=-120,
        token_type="refresh",
    )
    result = asyncio.run(_run_middleware(token))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_very_young_token_is_not_renewed():
    """Token emitido há menos de SLIDING_MIN_AGE_SECONDS não é renovado —
    evita spam de renovação em bursts de polling muito próximos."""
    token = _make_token(exp_delta_seconds=3 * 60, iat_delta_seconds=-5)
    result = asyncio.run(_run_middleware(token))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_invalid_token_not_renewed():
    """Token inválido (assinatura errada) — middleware deixa passar sem
    tocar, endpoint responde conforme sua própria lógica."""
    result = asyncio.run(_run_middleware("not-a-real-jwt"))
    assert _get_header(result["headers"], RENEWED_HEADER) is None


def test_renewed_token_preserves_payload_fields():
    """Novo token deve manter sub, email, is_admin, projects do original."""
    payload = {
        "sub": str(uuid4()),
        "email": "gp@example.com",
        "is_admin": False,
        "projects": {"abc": ["gp"]},
        "project_id": "abc",
        "iat": int(datetime.now(timezone.utc).timestamp()) - 120,
    }
    token = create_access_token(payload, expires_delta=timedelta(minutes=5))

    result = asyncio.run(_run_middleware(token))
    new_token = _get_header(result["headers"], RENEWED_HEADER)
    assert new_token is not None

    new_payload = verify_token(new_token)
    assert new_payload["sub"] == payload["sub"]
    assert new_payload["email"] == payload["email"]
    assert new_payload["is_admin"] == payload["is_admin"]
    assert new_payload["projects"] == payload["projects"]
    assert new_payload["project_id"] == payload["project_id"]


# ============================================================================
# INTEGRAÇÃO — middleware plugado no FastAPI real
# ============================================================================

def test_middleware_wired_in_main_app():
    """Confirma que o middleware está registrado no app.main global —
    senão tudo acima vira teste de biblioteca sem efeito em produção."""
    from app.main import app

    mw_names = []
    for m in app.user_middleware:
        cls = getattr(m, "cls", None)
        name = cls.__name__ if cls else str(m)
        mw_names.append(name)

    assert any("SlidingSession" in n for n in mw_names), (
        f"SlidingSessionMiddleware não está registrado no app. "
        f"Middlewares atuais: {mw_names}"
    )


def test_cors_exposes_renewed_header():
    """CORSMiddleware deve listar X-Access-Token-Renewed em
    expose_headers — senão navegador bloqueia JS de ler o header mesmo
    quando o backend o envia."""
    from app.main import app
    from fastapi.middleware.cors import CORSMiddleware

    cors_found = None
    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            cors_found = m
            break
    assert cors_found is not None, "CORS middleware ausente"

    expose = (cors_found.options or {}).get("expose_headers") or []
    normalized = [h.lower() for h in expose]
    assert "x-access-token-renewed" in normalized, (
        f"expose_headers não contém X-Access-Token-Renewed: {expose!r}"
    )
