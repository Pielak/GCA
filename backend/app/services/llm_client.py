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
