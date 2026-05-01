# TASK_EH_04 — Refatoração retroativa: `backend/app/integrations/`

## Pré-condição

TASK_EH_03 concluída e commitada.

## Objetivo

Aplicar a convenção em integrações externas: provedores LLM (Anthropic, OpenAI, Gemini), Git (PATs), webhooks, n8n, Cloudflare, SMTP, qualquer cliente HTTP. **Característica especial**: retry, timeout e rate limit são exceções esperadas — devem virar contexto rico em `LLMError`/`ExternalServiceError`, não silêncio.

## Escopo

- `backend/app/integrations/`
- `backend/app/llm/` (se existir como diretório separado)
- Qualquer cliente externo (`*_client.py`, `*_adapter.py`)

## Procedimento

### 1. Inventário

```bash
cd backend
find app/integrations app/llm -name "*.py" 2>/dev/null | xargs grep -ln "anthropic\|openai\|google.generativeai\|httpx\|requests" > /tmp/eh_integrations_files.txt
cat /tmp/eh_integrations_files.txt | xargs grep -n "except" 2>/dev/null > /tmp/eh_integrations_inventory.md
```

### 2. Padrão para chamada LLM

```python
import anthropic
from app.core.exceptions import LLMError, ConfigurationError

class AnthropicClient:
    def __init__(self, api_key: str | None):
        if not api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY ausente",
                context={"provider": "anthropic"},
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, prompt: str, *, model: str, max_tokens: int = 4096) -> str:
        try:
            resp = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError as e:
            logger.exception(
                "anthropic_rate_limit",
                extra={"model": model, "retry_after": getattr(e, "retry_after", None)},
            )
            raise LLMError(
                "rate limit Anthropic",
                context={"provider": "anthropic", "model": model, "retry_after": getattr(e, "retry_after", None)},
                cause=e,
            ) from e
        except anthropic.APITimeoutError as e:
            logger.exception("anthropic_timeout", extra={"model": model})
            raise LLMError(
                "timeout Anthropic",
                context={"provider": "anthropic", "model": model},
                cause=e,
            ) from e
        except anthropic.APIStatusError as e:
            logger.exception(
                "anthropic_api_status",
                extra={"model": model, "status": e.status_code},
            )
            raise LLMError(
                f"erro Anthropic {e.status_code}",
                context={"provider": "anthropic", "model": model, "status": e.status_code},
                cause=e,
            ) from e
        except anthropic.APIError as e:
            logger.exception("anthropic_api_error", extra={"model": model})
            raise LLMError(
                "falha Anthropic",
                context={"provider": "anthropic", "model": model},
                cause=e,
            ) from e

        return resp.content[0].text
```

Replicar o mesmo padrão para OpenAI (`openai.RateLimitError`, `openai.APITimeoutError`, `openai.APIError`) e Gemini (`google.api_core.exceptions.ResourceExhausted`, `google.api_core.exceptions.DeadlineExceeded`, `google.api_core.exceptions.GoogleAPIError`).

### 3. Padrão para clientes HTTP genéricos (httpx)

```python
import httpx
from app.core.exceptions import ExternalServiceError

async def call_n8n_webhook(url: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException as e:
        logger.exception("n8n_webhook_timeout", extra={"url": url})
        raise ExternalServiceError(
            "timeout no webhook n8n",
            context={"url": url},
            cause=e,
        ) from e
    except httpx.HTTPStatusError as e:
        logger.exception(
            "n8n_webhook_http_error",
            extra={"url": url, "status": e.response.status_code},
        )
        raise ExternalServiceError(
            f"webhook n8n retornou {e.response.status_code}",
            context={"url": url, "status": e.response.status_code, "body": e.response.text[:500]},
            cause=e,
        ) from e
    except httpx.RequestError as e:
        logger.exception("n8n_webhook_request_error", extra={"url": url})
        raise ExternalServiceError(
            "falha de rede no webhook n8n",
            context={"url": url},
            cause=e,
        ) from e
    except ValueError as e:  # JSONDecodeError herda de ValueError
        logger.exception("n8n_webhook_invalid_json", extra={"url": url})
        raise ExternalServiceError(
            "resposta n8n não é JSON válido",
            context={"url": url},
            cause=e,
        ) from e
```

### 4. Operações criptográficas (Fernet PAT)

Lembre que a TASK_M03 (Fernet PAT encryption) está pronta para execução. Garantir que o `crypto_service.py` siga o padrão:

```python
from cryptography.fernet import Fernet, InvalidToken
from app.core.exceptions import CryptoError, ConfigurationError

def decrypt_pat(token: str, key: bytes) -> str:
    if not token.startswith("fernet:v1:"):
        raise CryptoError(
            "token sem prefixo fernet:v1:",
            context={"token_prefix": token[:20]},
        )
    payload = token.removeprefix("fernet:v1:").encode()
    try:
        return Fernet(key).decrypt(payload).decode()
    except InvalidToken as e:
        logger.exception("fernet_invalid_token")
        raise CryptoError(
            "token Fernet inválido ou chave incorreta",
            cause=e,
        ) from e
```

### 5. Retry com tenacity (se usado no projeto)

Combinar retry com mapeamento canônico:

```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

@retry(
    retry=retry_if_exception_type(LLMError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,  # IMPORTANTE — re-lança a exceção original após esgotar tentativas
)
async def complete_with_retry(prompt: str) -> str:
    return await anthropic_client.complete(prompt, model="claude-opus-4-7")
```

`reraise=True` é obrigatório para que a `LLMError` chegue até o handler global em vez de virar `RetryError`.

### 6. Não fazer

- Não capturar `LLMError` dentro da própria integração para "tratar e retornar default" — isso volta a mascarar.
- Não suprimir timeout — ele precisa virar `ExternalServiceError` com contexto.
- Não logar API keys, PATs, payload completo de mensagens LLM em `extra` (usar truncamento ou hash).

### 7. Validação

```bash
cd backend
ruff check app/integrations/ app/llm/ 2>/dev/null
pytest tests/integrations/ tests/llm/ -v 2>/dev/null
```

### 8. Teste obrigatório de mapeamento

Adicionar em `backend/tests/integrations/test_exception_mapping.py`:

```python
import pytest
import anthropic
from unittest.mock import AsyncMock, patch
from app.core.exceptions import LLMError
from app.integrations.anthropic_client import AnthropicClient


@pytest.mark.asyncio
async def test_rate_limit_maps_to_llm_error():
    client = AnthropicClient(api_key="sk-test")
    with patch.object(client._client.messages, "create", new=AsyncMock(side_effect=anthropic.RateLimitError(
        message="rate limit", response=None, body=None
    ))):
        with pytest.raises(LLMError) as exc:
            await client.complete("test", model="claude-opus-4-7")
        assert exc.value.context["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_timeout_maps_to_llm_error():
    client = AnthropicClient(api_key="sk-test")
    with patch.object(client._client.messages, "create", new=AsyncMock(side_effect=anthropic.APITimeoutError(request=None))):
        with pytest.raises(LLMError):
            await client.complete("test", model="claude-opus-4-7")
```

## Relatório final

1. Arquivos alterados
2. Tabela de mapeamentos aplicados (provider → exceção original → exceção GCA)
3. Antes/depois de contagens
4. Saída de ruff e pytest
5. Lista de pontos onde `tenacity.retry` foi usado, com confirmação de `reraise=True`
6. Confirmação de que nenhum `extra={...}` em `logger.exception` carrega API key ou PAT em texto plano

## Critério de conclusão

- [ ] Todo provider LLM tem mapeamento de RateLimitError, TimeoutError, APIError
- [ ] Todo cliente HTTP mapeia TimeoutException, HTTPStatusError, RequestError
- [ ] CryptoError aplicada em operações Fernet/RSA
- [ ] `reraise=True` confirmado em todos os `@retry`
- [ ] Nenhum dado sensível vazando em `extra`
- [ ] Testes de mapeamento criados e passando
- [ ] Pare. Não commite.
