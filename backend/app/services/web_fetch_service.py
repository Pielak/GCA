"""MVP 9 Fase 9.2.ext — WebFetch curado de documentação externa.

Contrato §7 MVP 9 (regra dura): WebFetch acontece **apenas** quando
`module_candidates.external_reference` declarado por curadoria do GP
ou pelo Foundation generator. **GCA não navega autonomamente.**

Pipeline:
  1. Caller passa URL (presumida válida — vem do `external_reference`).
  2. Validação: scheme http/https, host não-loopback, max 500 chars.
  3. httpx GET com timeout curto, max 1 MB body.
  4. Extração de texto principal:
     - Remove tags `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`,
       `<aside>` (e seus filhos).
     - Strip tags HTML restantes.
     - Normaliza whitespace.
  5. Trunca a 50 KB de texto pra não inflar prompt do Ollama.
  6. Retorna `(text, metadata)`. Caller persiste em
     `external_reference_content`.

Sem cache global — caller persiste por módulo. Não-allow-list de
domínios nesta versão (curadoria já é controle); logs registram host
pra audit posterior.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)


MAX_TEXT_CHARS = 50_000
MAX_BODY_BYTES = 1_000_000  # 1 MB
FETCH_TIMEOUT_SECONDS = 30
USER_AGENT = "GCA-WebFetch/1.0 (+https://github.com/anthropics/claude-code)"

# Hosts proibidos (loopback + ranges privados óbvios). Não substitui
# firewall — defesa em profundidade contra SSRF acidental.
BLOCKED_HOST_PREFIXES = (
    "localhost", "127.", "0.0.0.0", "10.", "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "169.254.",  # link-local
)


class WebFetchError(Exception):
    """Erro recuperável (URL inválida, host bloqueado, timeout, 4xx/5xx)."""


def validate_url(url: str) -> str:
    """Valida URL. Retorna a URL canonicalizada ou levanta WebFetchError."""
    if not url or not isinstance(url, str):
        raise WebFetchError("URL vazia")
    url = url.strip()
    if len(url) > 500:
        raise WebFetchError(f"URL muito longa ({len(url)} chars, max 500)")
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise WebFetchError(f"URL malformada: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise WebFetchError(f"Apenas http/https aceito (recebido: {parsed.scheme!r})")
    host = (parsed.hostname or "").lower()
    if not host:
        raise WebFetchError("URL sem host")
    for blocked in BLOCKED_HOST_PREFIXES:
        if host == blocked.rstrip(".") or host.startswith(blocked):
            raise WebFetchError(
                f"Host {host!r} é privado/loopback — bloqueado por segurança."
            )
    return url


async def fetch_and_extract(url: str) -> tuple[str, dict[str, str]]:
    """Faz fetch da URL, extrai texto principal, retorna (text, meta).

    Levanta `WebFetchError` em qualquer falha. Caller decide se persiste
    como cache ou como erro (`external_reference_fetch_error`).
    """
    canonical_url = validate_url(url)
    parsed = urlparse(canonical_url)
    host = parsed.hostname or "?"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=FETCH_TIMEOUT_SECONDS, write=10.0, pool=5.0),
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        ) as client:
            resp = await client.get(canonical_url)
    except httpx.TimeoutException as exc:
        logger.warning("web_fetch.timeout", host=host, url=canonical_url[:100])
        raise WebFetchError(f"Timeout após {FETCH_TIMEOUT_SECONDS}s") from exc
    except httpx.HTTPError as exc:
        logger.warning("web_fetch.http_error", host=host, error=str(exc)[:200])
        raise WebFetchError(f"Falha de rede: {exc}") from exc

    if resp.status_code >= 400:
        logger.warning("web_fetch.bad_status", host=host, status=resp.status_code)
        raise WebFetchError(f"HTTP {resp.status_code} retornado por {host}")

    body = resp.content[:MAX_BODY_BYTES]
    content_type = resp.headers.get("content-type", "").lower()
    encoding = resp.encoding or "utf-8"
    try:
        html_text = body.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html_text = body.decode("utf-8", errors="replace")

    if "html" not in content_type and not _looks_like_html(html_text):
        # Texto puro / markdown / json — usa direto, só normaliza whitespace
        cleaned = _normalize_whitespace(html_text)
    else:
        cleaned = _extract_main_text(html_text)

    truncated = False
    if len(cleaned) > MAX_TEXT_CHARS:
        cleaned = cleaned[:MAX_TEXT_CHARS] + "\n\n[... conteúdo truncado em 50KB]"
        truncated = True

    meta = {
        "host": host,
        "status": str(resp.status_code),
        "content_type": content_type[:100],
        "chars": str(len(cleaned)),
        "truncated": "yes" if truncated else "no",
    }
    logger.info("web_fetch.success", host=host, chars=len(cleaned), truncated=truncated)
    return cleaned, meta


# ---------------------------------------------------------------------------
# HTML → texto principal
# ---------------------------------------------------------------------------

# Tags cujo conteúdo é descartado (chrome do site, não doc)
_BLOCK_TAGS = {"script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"}


class _MainTextExtractor(HTMLParser):
    """Extrai texto preservando ordem; descarta tags de chrome."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data:
            self._parts.append(data)

    def text(self) -> str:
        return _normalize_whitespace("".join(self._parts))


def _extract_main_text(html: str) -> str:
    parser = _MainTextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass  # html.parser pode levantar em HTML muito malformado
    return parser.text()


_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def _normalize_whitespace(text: str) -> str:
    """Normaliza spaces/newlines pra reduzir tamanho sem perder leitura."""
    if not text:
        return ""
    text = _MULTI_SPACE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def _looks_like_html(text: str) -> bool:
    """Heurística rápida — tem menos overhead que parser completo."""
    head = text[:500].lower()
    return "<html" in head or "<!doctype html" in head or ("<body" in head)
