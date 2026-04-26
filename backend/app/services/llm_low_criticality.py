"""LLM helpers provider-agnósticos pra operações de baixa criticidade (§6.2).

Centraliza a resolução de provider e dispatch de chamada pros serviços que
geram conteúdo auxiliar (detalhamento de módulos, test specs, LiveDoc por
módulo). Antes desta consolidação (sessão 30, DT-086), cada um dos 3
services tinha cópia própria de `_resolve_ollama_config` + `_call_ollama`
hardcodando provider "ollama" e violando §6.2 ("IA configurável por
cliente — não hardcodar provedor").

Regra do contrato §6.2 pra baixa criticidade:
  - Qualquer provider configurado serve.
  - Ollama preferido quando disponível (zero custo de tokens externos).
  - Fallback pro provider default do projeto (Anthropic/DeepSeek/
    OpenAI/Grok/Gemini) quando Ollama ausente.
  - Nunca exigir Ollama. Nunca falhar "Ollama não configurado" se
    qualquer outro provider está no vault.
"""
from __future__ import annotations

import time
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


#: Timeout generoso pra Ollama em CPU (qwen2.5-coder:7b leva 30-180s).
#: Modelos em GPU respondem ≤10s; timeout só protege contra hang.
OLLAMA_READ_TIMEOUT_SECONDS = 240

#: Timeout pros providers cloud: respostas típicas <30s, 60s dá margem.
CLOUD_READ_TIMEOUT_SECONDS = 60

#: Modelos default por provider pra baixa criticidade. Foco em velocidade
#: e custo — detalhamento/specs são insumo, não produção. Cliente pode
#: override via project_settings.
_LOW_CRITICALITY_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "grok": "grok-2",
    "gemini": "gemini-2.0-flash",
    "ollama": "qwen2.5-coder:7b",
}


#: Cap de max_tokens por modelo. Usado pra clamp em chamadas de scaffold/
#: alta criticidade que pedem 32000+ — DeepSeek-chat aceita 8192, GPT-4o
#: aceita 16384, Opus 4.6 aceita 32000 sem header beta. Modelo desconhecido
#: cai no fallback genérico (8192).
MAX_TOKENS_BY_MODEL: dict[str, int] = {
    # Anthropic
    "claude-opus-4-6": 32000,
    "claude-opus-4-7": 32000,
    "claude-sonnet-4-6": 64000,
    "claude-haiku-4-5-20251001": 8192,
    # OpenAI
    "gpt-5": 16384,
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    # DeepSeek
    "deepseek-chat": 8192,
    "deepseek-reasoner": 8192,
    # Grok
    "grok-2": 8192,
    # Gemini
    "gemini-2.0-flash": 8192,
    "gemini-2.5-pro": 8192,
    # Ollama (modelos locais — limite arbitrário pra não estourar VRAM)
    "qwen2.5-coder:7b": 8192,
}


def clamp_max_tokens(model: str, requested: int) -> int:
    """Limita `requested` ao cap conhecido do `model`. Usa 8192 se desconhecido."""
    cap = MAX_TOKENS_BY_MODEL.get(model, 8192)
    return min(requested, cap)


async def resolve_llm_config(
    db: AsyncSession, project_id: UUID,
    *,
    prefer_ollama: bool = True,
) -> Optional[dict[str, Any]]:
    """Resolve provider pra operação LLM no contexto do projeto.

    Ordem de preferência:
      1. Ollama (se configurado com base_url) — zero custo externo.
         **Pulado quando `prefer_ollama=False`** (scaffold/alta criticidade
         devem respeitar o provider default escolhido pelo owner, não cair
         em local barato sem ele saber).
      2. Provider default do projeto (qualquer).

    Retorna `{provider, base_url, api_key, model}` ou None se nenhum
    provider está disponível/válido.
    """
    from app.services.ai_key_resolver import AIKeyResolver

    chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)

    # 1. Prefere Ollama quando configurado E o caller permitir
    for entry in chain:
        if not prefer_ollama:
            break
        if (entry.get("provider") or "").lower() != "ollama":
            continue
        base_url = entry.get("base_url")
        if not base_url:
            logger.warning(
                "llm_low_crit.ollama_without_base_url",
                project_id=str(project_id),
            )
            continue
        return {
            "provider": "ollama",
            "base_url": base_url.rstrip("/"),
            "api_key": None,
            "model": entry.get("model") or _LOW_CRITICALITY_DEFAULT_MODELS["ollama"],
        }

    # 2. Fallback: provider default do projeto
    default_provider = await AIKeyResolver._resolve_project_provider(db, project_id)
    if not default_provider:
        return None
    api_key = await AIKeyResolver.get_project_key(db, project_id, provider=default_provider)
    if not api_key:
        return None

    model_from_chain = None
    for entry in chain:
        if (entry.get("provider") or "").lower() == default_provider.lower():
            model_from_chain = entry.get("model")
            break

    return {
        "provider": default_provider,
        "base_url": None,
        "api_key": api_key,
        "model": model_from_chain or _LOW_CRITICALITY_DEFAULT_MODELS.get(default_provider, "deepseek-chat"),
    }


async def call_llm(
    *,
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
    temperature: float = 0.2,
    log_context: str = "llm_low_crit",
) -> str:
    """Chama LLM fazendo dispatch por provider. Retorna texto cru.

    Anthropic via SDK nativo; Ollama/DeepSeek/OpenAI/Grok via httpx
    OpenAI-compat. Timeouts separados (Ollama 240s, cloud 60s).
    Erros de rede/timeout/HTTP são re-levantados como RuntimeError
    com mensagem em PT-BR (caller mostra pro usuário).

    Args:
        config: dict retornado por `resolve_llm_config`.
        system_prompt/user_prompt: conteúdo da chamada.
        max_tokens: budget de output (default 1500).
        temperature: default 0.2.
        log_context: prefixo dos logs estruturados pro caller identificar
            qual service chamou (ex: "module_details", "test_spec").
    """
    provider = config["provider"]
    model = config["model"]

    # Anthropic: SDK nativo
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=config["api_key"])
        started = time.monotonic()
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        elapsed = time.monotonic() - started
        logger.info(
            f"{log_context}.llm_call_ok",
            provider=provider, model=model, elapsed_s=round(elapsed, 1),
        )
        if not response.content:
            return ""
        return response.content[0].text

    # Ollama / OpenAI-compat
    provider_urls = {
        "ollama": f"{config['base_url']}/v1/chat/completions" if config.get("base_url") else None,
        "deepseek": "https://api.deepseek.com/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "grok": "https://api.x.ai/v1/chat/completions",
    }
    url = provider_urls.get(provider)
    if not url:
        raise RuntimeError(
            f"Provider '{provider}' não suportado em operações de baixa criticidade. "
            "Configure Anthropic, Ollama, DeepSeek, OpenAI ou Grok em Settings → IA."
        )

    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    read_timeout = OLLAMA_READ_TIMEOUT_SECONDS if provider == "ollama" else CLOUD_READ_TIMEOUT_SECONDS
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=5.0)

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.ReadTimeout as exc:
        elapsed = time.monotonic() - started
        logger.warning(
            f"{log_context}.llm_timeout",
            provider=provider, model=model,
            elapsed_s=round(elapsed, 1), limit_s=read_timeout,
        )
        if provider == "ollama":
            raise RuntimeError(
                f"Ollama ({model}) não respondeu em {read_timeout}s. Modelo "
                "pode estar carregando do disco (primeira chamada) ou rodando "
                "em CPU lenta. Tente novamente — fica em memória após o primeiro uso."
            ) from exc
        raise RuntimeError(
            f"{provider} ({model}) não respondeu em {read_timeout}s."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"{provider} API retornou erro {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc

    elapsed = time.monotonic() - started
    logger.info(
        f"{log_context}.llm_call_ok",
        provider=provider, model=model, elapsed_s=round(elapsed, 1),
    )
    choices = body.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""
