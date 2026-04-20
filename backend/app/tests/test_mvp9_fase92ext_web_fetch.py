"""MVP 9 Fase 9.2.ext — WebFetch curado por external_reference.

Cobre:
  - validate_url: bloqueia loopback/RFC1918, scheme, tamanho, malformed.
  - fetch_and_extract: HTML real (com mock httpx), text/plain, status 4xx,
    timeout, body grande truncado, encoding fallback.
  - Extrator de texto: remove script/style/nav/footer; preserva ordem;
    normaliza whitespace.
  - Integração com module_details: prompt inclui doc externa quando há.
  - external_reference_payload no contrato da API.
  - Compartimentalização preservada (URL/cache por módulo).

Sem hit em URLs reais — tudo mockado ou via stdlib.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models.base import (
    ArguiderAnalysis, IngestedDocument, ModuleCandidate, OCG, Questionnaire,
)
from app.services.web_fetch_service import (
    BLOCKED_HOST_PREFIXES, WebFetchError, _extract_main_text,
    _normalize_whitespace, fetch_and_extract, validate_url,
)
from app.services.module_details_service import (
    _build_external_reference_payload, _build_user_prompt,
)
from app.tests.factories import (
    create_test_organization, create_test_project, create_test_user,
)


# ============================================================================
# validate_url
# ============================================================================

def test_validate_url_https_ok():
    assert validate_url("https://example.com/docs") == "https://example.com/docs"


def test_validate_url_http_ok():
    assert validate_url("http://example.com").startswith("http://")


def test_validate_url_strip_whitespace():
    assert validate_url("  https://x.com  ") == "https://x.com"


def test_validate_url_vazia_levanta():
    with pytest.raises(WebFetchError):
        validate_url("")
    with pytest.raises(WebFetchError):
        validate_url(None)


def test_validate_url_muito_longa_levanta():
    with pytest.raises(WebFetchError, match="muito longa"):
        validate_url("https://x.com/" + "a" * 600)


def test_validate_url_scheme_invalido():
    with pytest.raises(WebFetchError):
        validate_url("ftp://x.com")
    with pytest.raises(WebFetchError):
        validate_url("file:///etc/passwd")
    with pytest.raises(WebFetchError):
        validate_url("javascript:alert(1)")


def test_validate_url_loopback_bloqueado():
    with pytest.raises(WebFetchError, match="privado/loopback"):
        validate_url("http://localhost/x")
    with pytest.raises(WebFetchError):
        validate_url("http://127.0.0.1:8080/")


def test_validate_url_rfc1918_bloqueado():
    """Defesa contra SSRF acidental."""
    for host in ("10.0.0.1", "192.168.1.1", "172.16.0.1"):
        with pytest.raises(WebFetchError):
            validate_url(f"http://{host}/")


def test_validate_url_link_local_bloqueado():
    """169.254.169.254 = AWS/GCE metadata endpoint, é o pior alvo SSRF."""
    with pytest.raises(WebFetchError):
        validate_url("http://169.254.169.254/")


def test_validate_url_sem_host():
    with pytest.raises(WebFetchError):
        validate_url("https:///")


# ============================================================================
# Extrator de texto
# ============================================================================

def test_extract_remove_script_e_style():
    html = """
    <html><body>
    <script>alert('x')</script>
    <style>body { color: red; }</style>
    <p>Conteúdo legítimo</p>
    </body></html>
    """
    text = _extract_main_text(html)
    assert "Conteúdo legítimo" in text
    assert "alert" not in text
    assert "color: red" not in text


def test_extract_remove_nav_header_footer():
    html = """
    <html><body>
    <nav>menu top</nav>
    <header>cabeçalho</header>
    <main>texto principal aqui</main>
    <aside>banner lateral</aside>
    <footer>rodapé direitos</footer>
    </body></html>
    """
    text = _extract_main_text(html)
    assert "texto principal aqui" in text
    for chrome in ("menu top", "cabeçalho", "banner lateral", "rodapé direitos"):
        assert chrome not in text


def test_extract_preserva_ordem():
    html = "<html><body><p>primeiro</p><p>segundo</p><p>terceiro</p></body></html>"
    text = _extract_main_text(html)
    assert text.find("primeiro") < text.find("segundo") < text.find("terceiro")


def test_extract_html_malformado_nao_quebra():
    html = "<html><body><p>texto<script>x</body>"
    text = _extract_main_text(html)
    assert "texto" in text


def test_normalize_whitespace_remove_espacos_extras():
    assert _normalize_whitespace("  a   b\t\tc  ") == "a b c"


def test_normalize_whitespace_compacta_newlines():
    """Linhas vazias entre conteúdo são removidas (compactação agressiva
    pra reduzir tokens do prompt LLM)."""
    out = _normalize_whitespace("a\n\n\n\n\nb")
    assert "a" in out and "b" in out
    # Sem 3+ newlines em sequência (foram colapsados)
    assert "\n\n\n" not in out


def test_normalize_whitespace_vazio():
    assert _normalize_whitespace("") == ""
    assert _normalize_whitespace("   \n\n  ") == ""


# ============================================================================
# fetch_and_extract — mocked httpx
# ============================================================================

@pytest.mark.asyncio
async def test_fetch_html_extrai_texto_principal():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html; charset=utf-8"}
    fake_response.encoding = "utf-8"
    fake_response.content = b"""
    <html><body>
    <nav>ignora</nav>
    <h1>API DataJud</h1>
    <p>Endpoint: /api/v1/processos</p>
    <script>window.x=1</script>
    </body></html>
    """

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("app.services.web_fetch_service.httpx.AsyncClient", return_value=fake_client):
        text, meta = await fetch_and_extract("https://datajud.cnj.jus.br/docs")

    assert "API DataJud" in text
    assert "/api/v1/processos" in text
    assert "ignora" not in text
    assert "window.x" not in text
    assert meta["status"] == "200"
    assert meta["host"] == "datajud.cnj.jus.br"


@pytest.mark.asyncio
async def test_fetch_status_4xx_levanta():
    fake_response = MagicMock()
    fake_response.status_code = 404
    fake_response.headers = {"content-type": "text/html"}
    fake_response.encoding = "utf-8"
    fake_response.content = b"<html>not found</html>"

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("app.services.web_fetch_service.httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(WebFetchError, match="404"):
            await fetch_and_extract("https://example.com/missing")


@pytest.mark.asyncio
async def test_fetch_timeout_levanta():
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("app.services.web_fetch_service.httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(WebFetchError, match="Timeout"):
            await fetch_and_extract("https://example.com/slow")


@pytest.mark.asyncio
async def test_fetch_body_grande_truncado():
    big_body = b"<html><body><p>" + (b"x" * 100_000) + b"</p></body></html>"
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html"}
    fake_response.encoding = "utf-8"
    fake_response.content = big_body

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("app.services.web_fetch_service.httpx.AsyncClient", return_value=fake_client):
        text, meta = await fetch_and_extract("https://example.com/big")
    assert len(text) <= 50_000 + 100  # truncado a 50KB + sufixo
    assert meta["truncated"] == "yes"


@pytest.mark.asyncio
async def test_fetch_text_plain_passa_direto():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/plain; charset=utf-8"}
    fake_response.encoding = "utf-8"
    fake_response.content = b"linha 1\n\n\n\n\nlinha 2"

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("app.services.web_fetch_service.httpx.AsyncClient", return_value=fake_client):
        text, meta = await fetch_and_extract("https://example.com/txt")
    assert "linha 1" in text and "linha 2" in text
    assert "\n\n\n" not in text  # normalizado


@pytest.mark.asyncio
async def test_fetch_url_invalida_levanta_antes_de_request():
    """validate_url roda primeiro — sem hit no httpx."""
    with pytest.raises(WebFetchError, match="loopback"):
        await fetch_and_extract("http://localhost:8080/")


# ============================================================================
# Payload do API (módulo)
# ============================================================================

def test_external_reference_payload_sem_url_retorna_none():
    mc = MagicMock()
    mc.external_reference = None
    assert _build_external_reference_payload(mc) is None


def test_external_reference_payload_com_url_sem_fetch():
    mc = MagicMock()
    mc.external_reference = "https://x.com/docs"
    mc.external_reference_content = None
    mc.external_reference_fetched_at = None
    mc.external_reference_fetch_error = None
    out = _build_external_reference_payload(mc)
    assert out["url"] == "https://x.com/docs"
    assert out["fetched"] is False
    assert "chars" not in out


def test_external_reference_payload_com_fetch_ok():
    mc = MagicMock()
    mc.external_reference = "https://x.com/docs"
    mc.external_reference_content = "abc" * 100
    mc.external_reference_fetched_at = datetime.now(timezone.utc)
    mc.external_reference_fetch_error = None
    out = _build_external_reference_payload(mc)
    assert out["fetched"] is True
    assert out["chars"] == 300
    assert "fetched_at" in out


def test_external_reference_payload_com_erro():
    mc = MagicMock()
    mc.external_reference = "https://x.com/docs"
    mc.external_reference_content = None
    mc.external_reference_fetched_at = datetime.now(timezone.utc)
    mc.external_reference_fetch_error = "HTTP 500"
    out = _build_external_reference_payload(mc)
    assert out["error"] == "HTTP 500"
    assert out["fetched"] is False


# ============================================================================
# Integração com prompt do Ollama
# ============================================================================

def test_prompt_inclui_doc_externa_quando_fetched():
    mc = MagicMock(spec=ModuleCandidate)
    mc.name = "Conector DataJud"
    mc.module_type = "backend_service"
    mc.description = "Cliente"
    mc.external_reference = "https://datajud.cnj.jus.br/docs"
    mc.external_reference_content = "DOC OFICIAL DataJud: endpoint /api/v1/processos requer auth..."

    prompt = _build_user_prompt(mc, {"STACK_RECOMMENDATION": {}})
    assert "Documentação oficial declarada" in prompt
    assert "https://datajud.cnj.jus.br/docs" in prompt
    assert "DOC OFICIAL DataJud" in prompt


def test_prompt_nao_inclui_doc_quando_url_sem_content():
    """URL declarada mas sem fetch ainda — não polui prompt com nada."""
    mc = MagicMock(spec=ModuleCandidate)
    mc.name = "X"
    mc.module_type = "feature"
    mc.description = ""
    mc.external_reference = "https://x.com"
    mc.external_reference_content = None

    prompt = _build_user_prompt(mc, {"STACK_RECOMMENDATION": {}})
    assert "Documentação oficial declarada" not in prompt


def test_prompt_trunca_doc_grande():
    mc = MagicMock(spec=ModuleCandidate)
    mc.name = "X"
    mc.module_type = "feature"
    mc.description = ""
    mc.external_reference = "https://x.com"
    mc.external_reference_content = "x" * 50_000  # bem maior que 8KB

    prompt = _build_user_prompt(mc, {"STACK_RECOMMENDATION": {}})
    assert "doc externa truncada em 8KB" in prompt
    # Total prompt < 30KB (8KB doc + base ~5KB)
    assert len(prompt) < 30_000


# ============================================================================
# Defensive: contrato de não-navegação autônoma
# ============================================================================

def test_blocked_host_prefixes_inclui_loopback_e_rfc1918():
    """Contrato de segurança: lista coberta."""
    must_block = ("localhost", "127.", "10.", "192.168.", "172.16.", "169.254.")
    for h in must_block:
        assert any(b.startswith(h) or b == h for b in BLOCKED_HOST_PREFIXES), (
            f"prefix {h} não está em BLOCKED_HOST_PREFIXES"
        )
