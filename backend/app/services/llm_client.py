"""LLM Client abstraction for Phase A personas.

Provides unified interface for Auditor and specialist personas with caching support.
"""
from typing import Optional, Literal
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMUsage:
    """Token usage statistics from LLM call."""
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    usage: LLMUsage
    finish_reason: str


class LLMClient(ABC):
    """Abstract LLM client interface for personas."""
    provider_name: str
    model_name: str

    @abstractmethod
    async def complete(
        self,
        system: Optional[str],
        user: str,
        cacheable_system: Optional[str] = None,
        response_format: Optional[Literal["json", "text"]] = None,
        max_output_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Complete a prompt via LLM."""
        ...


class AnthropicLLMClient(LLMClient):
    """Anthropic Claude client for Phase A personas."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.provider_name = "anthropic"
        self.model_name = getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-7")

    async def complete(
        self,
        system: Optional[str],
        user: str,
        cacheable_system: Optional[str] = None,
        response_format: Optional[Literal["json", "text"]] = None,
        max_output_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Call Claude API with optional caching."""
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self.api_key)

            # Build system prompt with cache control
            system_content = []
            if cacheable_system:
                system_content.append({
                    "type": "text",
                    "text": cacheable_system,
                    "cache_control": {"type": "ephemeral"}
                })
            if system:
                system_content.append({
                    "type": "text",
                    "text": system,
                })

            kwargs = {
                "model": self.model_name,
                "max_tokens": max_output_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": user}],
            }
            if system_content:
                kwargs["system"] = system_content

            resp = await client.messages.create(**kwargs)

            usage = LLMUsage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                cached_input_tokens=getattr(resp.usage, 'cache_read_input_tokens', 0),
            )

            return LLMResponse(
                content=resp.content[0].text,
                usage=usage,
                finish_reason=resp.stop_reason,
            )
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise


def get_llm_client() -> LLMClient:
    """Get configured LLM client from settings."""
    provider = getattr(settings, "LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        return AnthropicLLMClient()
    else:
        # Default to Anthropic if provider not recognized
        return AnthropicLLMClient()


class DeepSeekLLMClient(LLMClient):
    """DeepSeek API client for Phase A personas."""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.provider_name = "deepseek"
        self.model_name = model

    async def complete(
        self,
        system: Optional[str],
        user: str,
        cacheable_system: Optional[str] = None,
        response_format: Optional[Literal["json", "text"]] = None,
        max_output_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Call DeepSeek API."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com",
            )

            # Construir sistema + user
            system_content = ""
            if cacheable_system:
                system_content += cacheable_system + "\n\n"
            if system:
                system_content += system

            messages = []
            if system_content:
                messages.append({"role": "system", "content": system_content})
            messages.append({"role": "user", "content": user})

            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_output_tokens,
            }
            # DeepSeek não suporta response_format=json_object da forma que OpenAI suporta.
            # O prompt já pede JSON explicitamente, então não precisamos forçar aqui.

            resp = await client.chat.completions.create(**kwargs)

            usage = LLMUsage(
                input_tokens=resp.usage.prompt_tokens,
                output_tokens=resp.usage.completion_tokens,
                cached_input_tokens=0,
            )

            return LLMResponse(
                content=resp.choices[0].message.content,
                usage=usage,
                finish_reason=resp.choices[0].finish_reason,
            )
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            raise


def create_llm_client(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """Factory to create LLM client from provider name and credentials.

    Args:
        provider: Provider name (anthropic, deepseek, openai, grok, ollama)
        api_key: API key for the provider
        model: Model name (optional, uses defaults if not provided)
        base_url: Base URL for local providers like Ollama

    Returns:
        Appropriate LLMClient concrete implementation.

    Raises:
        ValueError: If provider is not supported or key is missing.
    """
    provider_lower = (provider or "anthropic").lower()

    if provider_lower == "anthropic":
        return AnthropicLLMClient(api_key=api_key)
    elif provider_lower == "deepseek":
        return DeepSeekLLMClient(api_key=api_key, model=model or "deepseek-v4-flash")
    else:
        # Proibido contorno silencioso (§0 CLAUDE.md)
        raise ValueError(
            f"Provider '{provider}' não implementado. "
            f"Suportados: anthropic, deepseek"
        )
