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


#: MVP-J fase 4 (2026-04-25): rate limit típico por provider em
#: requests por minuto (RPM). Usado pra limitar concorrência do scaffold
#: dinâmico — sem isso, paralelismo=5 fixo estoura DeepSeek (que tem
#: tier free de 30 RPM no chat) ou subutiliza Anthropic (50 RPM).
#:
#: Valores são tier free/baixo conservador. Operador com tier maior
#: pode subir SCAFFOLD_PARALLELISM via env var pra forçar concurrency
#: maior — get_provider_max_concurrency respeita o requested se for
#: menor que o cap derivado do RPM.
RPM_BY_PROVIDER: dict[str, int] = {
    "anthropic": 50,
    "openai": 60,
    "deepseek": 60,
    "grok": 30,
    "gemini": 60,
    "ollama": 999,  # local, sem rate limit prático
}


def get_provider_max_concurrency(provider: str, requested: int) -> int:
    """Concurrency segura pro provider, dado `requested` (cap do operador).

    Heurística: cada chamada LLM dura em média ~5s (varia 2-30s). Pra
    não estourar RPM, concurrency segura ≈ RPM / 12 (5s × 12 = 60s).
    Provider desconhecido cai em 30 RPM conservador.
    """
    rpm = RPM_BY_PROVIDER.get((provider or "").lower(), 30)
    safe = max(1, rpm // 12)
    return min(requested, safe)


#: Stop reasons normalizados pra MVP-J fase 2 (truncamento detection).
#: Anthropic: stop_reason ∈ {end_turn, max_tokens, stop_sequence, tool_use}.
#: OpenAI-compat: finish_reason ∈ {stop, length, tool_calls, content_filter}.
#: Mapeamos pra: 'stop' (terminou natural) | 'length' (truncado por cap).
STOP_REASON_TRUNCATED = {"length", "max_tokens"}


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


#: Configuração canônica de retry com backoff exponencial em erros
#: transitórios (rate limit, timeout, network, 5xx). MVP-J fase 1
#: (2026-04-25): cobre ~50%+ das falhas que antes marcavam item como
#: failed direto no scaffold/audit. Backoff em segundos: 1, 2, 4 entre
#: tentativas. Ordem geral: 1ª tenta → falha transitória → espera 1s
#: → tenta 2 → falha → espera 2s → tenta 3 → falha → propaga.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)  # tempo de espera ANTES da tentativa N+1


def _is_retriable_httpx_error(exc: Exception) -> bool:
    """True pra erros transitórios que justificam retry com backoff."""
    if isinstance(exc, httpx.HTTPStatusError):
        # 429 = rate limit; 5xx = server error
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.ReadTimeout, httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError))


def _is_retriable_anthropic_error(exc: Exception) -> bool:
    """True pra exceções do SDK Anthropic que justificam retry. Lazy import
    pra evitar dependência forte se Anthropic SDK não estiver disponível."""
    try:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )
    except ImportError:
        return False
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        # 5xx do upstream Anthropic — tenta de novo
        try:
            return exc.status_code >= 500 or exc.status_code == 429
        except Exception:  # noqa: BLE001
            return False
    return False


_MAX_CONTINUATIONS = 3       # MVP-J fase 2 — limite de continuations contra truncamento
_MAX_JSON_REPROMPTS = 2      # MVP-J fase 3 — limite de reprompts contra JSON malformado


def _strip_md_fences(text: str) -> str:
    """Remove ```json ... ``` ou ``` ... ``` do início/fim. Tolerante."""
    import re as _re
    s = (text or "").strip()
    m = _re.match(r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", s, _re.DOTALL)
    return m.group(1).strip() if m else s


def _is_valid_json(text: str) -> bool:
    """True se text é JSON parseável (após strip de fences markdown)."""
    import json as _json
    try:
        _json.loads(_strip_md_fences(text))
        return True
    except (ValueError, TypeError):
        return False


async def _call_with_retry(
    *,
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    log_context: str,
    messages_override: list | None = None,
) -> tuple[str, str]:
    """Wrapper de retry (J1) ao redor de _invoke_llm_once. Retorna
    `(text, finish_reason)`. finish_reason ∈ {'stop', 'length',
    'tool_use', 'content_filter', 'unknown'}."""
    provider = config["provider"]
    model = config["model"]
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return await _invoke_llm_once(
                config=config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                log_context=log_context,
                messages_override=messages_override,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            retriable = (
                _is_retriable_anthropic_error(exc)
                if provider == "anthropic"
                else _is_retriable_httpx_error(exc)
            )
            if not retriable or attempt >= _RETRY_MAX_ATTEMPTS:
                raise
            backoff = _RETRY_BACKOFF_SECONDS[min(attempt - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
            logger.warning(
                f"{log_context}.llm_retry",
                provider=provider, model=model,
                attempt=attempt, max_attempts=_RETRY_MAX_ATTEMPTS,
                backoff_s=backoff,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            import asyncio as _asyncio
            await _asyncio.sleep(backoff)
    if last_exc:
        raise last_exc
    return ("", "unknown")


async def call_llm(
    *,
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
    temperature: float = 0.2,
    log_context: str = "llm_low_crit",
    auto_continue: bool = False,
    expect_json: bool = False,
) -> str:
    """Chama LLM fazendo dispatch por provider. Retorna texto cru.

    Anthropic via SDK nativo; Ollama/DeepSeek/OpenAI/Grok via httpx
    OpenAI-compat. Timeouts separados (Ollama 240s, cloud 60s).

    Adaptações ativas (MVP-J, 2026-04-25):
      - Fase 1 — Retry: 3 tentativas com backoff 1s/2s/4s em 429/5xx/
        ReadTimeout/ConnectError/Anthropic RateLimitError etc. NÃO
        retry em 4xx (exceto 429) — bugs determinísticos = falha rápida.
      - Fase 2 — Continuation se `auto_continue=True`: detecta finish_reason
        in {'length','max_tokens'} e re-chama com histórico + prompt
        "continue de onde parou", até `_MAX_CONTINUATIONS=3` iterações.
      - Fase 3 — Reprompt se `expect_json=True`: ao final, valida que
        output é JSON parseável; se não, re-chama pedindo correção,
        até `_MAX_JSON_REPROMPTS=2` tentativas. Caller continua
        responsável por parsear.

    Args:
        config: dict retornado por `resolve_llm_config`.
        system_prompt/user_prompt: conteúdo da chamada.
        max_tokens: budget de output (default 1500).
        temperature: default 0.2.
        log_context: prefixo dos logs estruturados.
        auto_continue: ativa continuation se output truncado (J2).
        expect_json: ativa reprompt se output não for JSON válido (J3).
    """
    provider = config["provider"]
    model = config["model"]

    # Fase 1+2 — primeira chamada + continuations contra truncamento
    accumulated, finish = await _call_with_retry(
        config=config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        log_context=log_context,
    )

    if auto_continue:
        for cont_iter in range(_MAX_CONTINUATIONS):
            if finish not in STOP_REASON_TRUNCATED:
                break
            logger.warning(
                f"{log_context}.truncated_continuing",
                provider=provider, model=model,
                iteration=cont_iter + 1,
                accumulated_chars=len(accumulated),
            )
            cont_messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": accumulated},
                {
                    "role": "user",
                    "content": (
                        "Sua resposta anterior foi truncada (atingiu o cap de "
                        "tokens de output). Continue EXATAMENTE de onde parou, "
                        "sem repetir nada do que já enviou e sem reabrir code "
                        "fences markdown. Se a resposta é JSON, complete a "
                        "sintaxe (fechar strings, chaves, colchetes). Não "
                        "adicione preâmbulo nem comentários."
                    ),
                },
            ]
            cont_text, finish = await _call_with_retry(
                config=config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,  # ignorado quando messages_override
                max_tokens=max_tokens,
                temperature=temperature,
                log_context=log_context,
                messages_override=cont_messages,
            )
            accumulated += cont_text
        else:
            logger.warning(
                f"{log_context}.truncated_after_max_continuations",
                provider=provider, model=model,
                max_iters=_MAX_CONTINUATIONS,
                accumulated_chars=len(accumulated),
            )

    # Fase 3 — reprompt em JSON malformado
    if expect_json and not _is_valid_json(accumulated):
        for reprompt_iter in range(_MAX_JSON_REPROMPTS):
            logger.warning(
                f"{log_context}.invalid_json_reprompting",
                provider=provider, model=model,
                iteration=reprompt_iter + 1,
                preview=accumulated[:200],
            )
            fix_messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": accumulated},
                {
                    "role": "user",
                    "content": (
                        "Sua resposta anterior NÃO é JSON válido — falhou ao "
                        "parsear. Devolva APENAS o JSON corrigido, sem "
                        "markdown fences (```), sem preâmbulo, sem comentários. "
                        "Garanta strings escapadas, chaves balanceadas e "
                        "colchetes fechados."
                    ),
                },
            ]
            accumulated, finish = await _call_with_retry(
                config=config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                log_context=log_context,
                messages_override=fix_messages,
            )
            if _is_valid_json(accumulated):
                logger.info(
                    f"{log_context}.invalid_json_recovered",
                    provider=provider, model=model,
                    iteration=reprompt_iter + 1,
                )
                break

    return accumulated


async def _invoke_llm_once(
    *,
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    log_context: str,
    messages_override: list | None = None,
) -> tuple[str, str]:
    """Implementação real da chamada LLM (1 tentativa, sem retry).
    Wrapper `call_llm` adiciona retry, continuation, reprompt JSON.

    Retorna `(text, finish_reason)`. finish_reason normalizado:
      - 'stop' = LLM terminou natural
      - 'length' = truncado por max_tokens
      - 'tool_use' / 'content_filter' / 'unknown' = outros casos

    Args:
        messages_override: se None, usa system+user padrão. Se passado,
            usa direto (pra continuation/reprompt).
    """
    provider = config["provider"]
    model = config["model"]

    # Anthropic: SDK nativo
    if provider == "anthropic":
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=config["api_key"])
        anthropic_messages = (
            messages_override
            if messages_override is not None
            else [{"role": "user", "content": user_prompt}]
        )
        started = time.monotonic()
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=anthropic_messages,
        )
        elapsed = time.monotonic() - started
        logger.info(
            f"{log_context}.llm_call_ok",
            provider=provider, model=model, elapsed_s=round(elapsed, 1),
        )
        # Normaliza stop_reason: end_turn → stop, max_tokens → length
        raw_stop = getattr(response, "stop_reason", "") or ""
        finish = "length" if raw_stop == "max_tokens" else (
            "stop" if raw_stop == "end_turn" else (raw_stop or "unknown")
        )
        if not response.content:
            return ("", finish)
        return (response.content[0].text, finish)

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

    # Mensagens: messages_override tem prioridade pra continuation/reprompt.
    # Quando override é passado, NÃO incluímos system de novo no payload —
    # caller já posicionou tudo. Caso contrário, system+user padrão.
    if messages_override is not None:
        payload_messages = (
            [{"role": "system", "content": system_prompt}] + messages_override
            if system_prompt
            else list(messages_override)
        )
    else:
        payload_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": payload_messages,
    }

    read_timeout = OLLAMA_READ_TIMEOUT_SECONDS if provider == "ollama" else CLOUD_READ_TIMEOUT_SECONDS
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=5.0)

    # Não converto httpx.ReadTimeout/HTTPStatusError em RuntimeError aqui:
    # `call_llm` (wrapper externo) precisa do tipo original pra decidir
    # retry vs propagar (MVP-J fase 1, 2026-04-25). Se acabarem as
    # tentativas, `call_llm` propaga e o caller wrappa em RuntimeError
    # se quiser mensagem PT-BR amigável.
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
        # ReadTimeout/HTTPStatusError propagam o tipo original pra
        # `call_llm` decidir retry. Só Ollama mantém RuntimeError explícito
        # (caso especial: modelo carregando, retry cego não ajuda).
        if provider == "ollama":
            raise RuntimeError(
                f"Ollama ({model}) não respondeu em {read_timeout}s. Modelo "
                "pode estar carregando do disco (primeira chamada) ou rodando "
                "em CPU lenta. Tente novamente — fica em memória após o primeiro uso."
            ) from exc
        raise  # propaga httpx.ReadTimeout original
    # httpx.HTTPStatusError NÃO é capturada aqui — propaga direto pra
    # call_llm verificar 429/5xx (retriable) vs 4xx (não retriable).

    elapsed = time.monotonic() - started
    logger.info(
        f"{log_context}.llm_call_ok",
        provider=provider, model=model, elapsed_s=round(elapsed, 1),
    )
    choices = body.get("choices") or []
    if not choices:
        return ("", "unknown")
    first = choices[0]
    text = (first.get("message", {}) or {}).get("content", "") or ""
    raw_finish = (first.get("finish_reason") or "").lower()
    # OpenAI-compat 'stop'/'length' já são canônicos. Outros viram 'unknown'.
    finish = raw_finish if raw_finish in ("stop", "length", "tool_calls", "content_filter") else "unknown"
    return (text, finish)
