"""
AI Service — Multi-provider support
Supports: Anthropic (Claude), OpenAI, Google Gemini, DeepSeek, Xai Grok
"""
from typing import Optional, Dict, Any
from enum import Enum
import structlog
import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)


class AIProvider(str, Enum):
    """Supported AI providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    GROK = "grok"
    OPENROUTER = "openrouter"


class AIModel:
    """AI Model definition"""
    def __init__(self, name: str, provider: AIProvider, max_tokens: int = 4096):
        self.name = name
        self.provider = provider
        self.max_tokens = max_tokens


# Available models per provider
AVAILABLE_MODELS = {
    AIProvider.ANTHROPIC: [
        AIModel("claude-opus-4-6", AIProvider.ANTHROPIC, 200000),
        AIModel("claude-sonnet-4-6", AIProvider.ANTHROPIC, 200000),
        AIModel("claude-haiku-4-5", AIProvider.ANTHROPIC, 200000),
    ],
    AIProvider.OPENAI: [
        AIModel("gpt-4-turbo", AIProvider.OPENAI, 128000),
        AIModel("gpt-4o", AIProvider.OPENAI, 128000),
        AIModel("gpt-3.5-turbo", AIProvider.OPENAI, 16385),
    ],
    AIProvider.GEMINI: [
        AIModel("gemini-2.0-pro", AIProvider.GEMINI, 1000000),
        AIModel("gemini-1.5-pro", AIProvider.GEMINI, 1000000),
        AIModel("gemini-1.5-flash", AIProvider.GEMINI, 1000000),
    ],
    AIProvider.DEEPSEEK: [
        AIModel("deepseek-chat", AIProvider.DEEPSEEK, 128000),
        AIModel("deepseek-coder", AIProvider.DEEPSEEK, 128000),
    ],
    AIProvider.GROK: [
        AIModel("grok-3-mini", AIProvider.GROK, 32000),
        AIModel("grok-3", AIProvider.GROK, 128000),
    ],
    AIProvider.OPENROUTER: [
        AIModel("claude-3.5-sonnet", AIProvider.OPENROUTER, 200000),
        AIModel("gpt-4-turbo", AIProvider.OPENROUTER, 128000),
        AIModel("gpt-4o", AIProvider.OPENROUTER, 128000),
        AIModel("gemini-2.0-pro", AIProvider.OPENROUTER, 1000000),
        AIModel("deepseek-chat", AIProvider.OPENROUTER, 128000),
    ],
}


class AIService:
    """Service for interacting with multiple AI providers"""

    @staticmethod
    def get_default_provider() -> AIProvider:
        """Get default AI provider from config"""
        try:
            return AIProvider(settings.DEFAULT_AI_PROVIDER.lower())
        except ValueError:
            logger.warning("ai.invalid_default_provider", provider=settings.DEFAULT_AI_PROVIDER)
            return AIProvider.GROK

    @staticmethod
    def get_default_model() -> str:
        """Get default AI model from config"""
        return settings.DEFAULT_AI_MODEL

    @staticmethod
    def get_api_key(provider: AIProvider) -> Optional[str]:
        """Get API key for provider"""
        keys = {
            AIProvider.ANTHROPIC: settings.ANTHROPIC_API_KEY,
            AIProvider.OPENAI: settings.OPENAI_API_KEY,
            AIProvider.GEMINI: settings.GEMINI_API_KEY,
            AIProvider.DEEPSEEK: settings.DEEPSEEK_API_KEY,
            AIProvider.GROK: settings.GROK_API_KEY,
            AIProvider.OPENROUTER: settings.OPENROUTER_API_KEY,
        }
        return keys.get(provider)

    @staticmethod
    def get_available_models(provider: AIProvider) -> list[AIModel]:
        """Get available models for provider"""
        return AVAILABLE_MODELS.get(provider, [])

    @staticmethod
    async def query(
        prompt: str,
        provider: Optional[AIProvider] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Query an AI provider.

        Args:
            prompt: User prompt
            provider: AI provider (default from config)
            model: Model name (default from config)
            system_prompt: System prompt for context
            temperature: Temperature (0-2, default 0.7)
            max_tokens: Max tokens in response
            api_key: Optional API key override (bypasses config lookup)

        Returns:
            (success, response_text, error_message)
        """
        if provider is None:
            provider = AIService.get_default_provider()

        if model is None:
            model = AIService.get_default_model()

        if api_key is None:
            api_key = AIService.get_api_key(provider)
        if not api_key:
            error_msg = f"No API key configured for {provider.value}"
            logger.warning("ai.missing_api_key", provider=provider.value)
            return False, None, error_msg

        try:
            if provider == AIProvider.ANTHROPIC:
                return await AIService._query_anthropic(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            elif provider == AIProvider.OPENAI:
                return await AIService._query_openai(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            elif provider == AIProvider.GEMINI:
                return await AIService._query_gemini(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            elif provider == AIProvider.DEEPSEEK:
                return await AIService._query_deepseek(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            elif provider == AIProvider.GROK:
                return await AIService._query_grok(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            elif provider == AIProvider.OPENROUTER:
                return await AIService._query_openrouter(
                    api_key, prompt, model, system_prompt, temperature, max_tokens
                )
            else:
                return False, None, f"Unknown provider: {provider.value}"

        except Exception as e:
            logger.error("ai.query_failed", provider=provider.value, error=str(e))
            return False, None, f"Query failed: {str(e)}"

    @staticmethod
    async def _query_anthropic(
        api_key: str,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Query Anthropic Claude (AsyncAnthropic — não bloqueia event loop)."""
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key)

            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens or 2048,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )

            return True, response.content[0].text, None
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    async def _query_openai(
        api_key: str,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Query OpenAI GPT (AsyncOpenAI — não bloqueia event loop)."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or 2048,
            )

            return True, response.choices[0].message.content, None
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    async def _query_gemini(
        api_key: str,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Query Google Gemini.

        google-generativeai SDK é síncrono — envolvemos em asyncio.to_thread
        para que a chamada (que bloqueia ~30s) rode em pool de threads e não
        congele o event loop.
        """
        try:
            import asyncio
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

            model_obj = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens or 2048,
                }
            )

            response = await asyncio.to_thread(model_obj.generate_content, full_prompt)
            return True, response.text, None
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    async def _query_deepseek(
        api_key: str,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Query DeepSeek (AsyncOpenAI — não bloqueia event loop)."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or 2048,
            )

            return True, response.choices[0].message.content, None
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    async def _query_grok(
        api_key: str,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Query Xai Grok (AsyncOpenAI — não bloqueia event loop)."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.x.ai",
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or 2048,
            )

            return True, response.choices[0].message.content, None
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    def list_available_providers() -> list[str]:
        """List all available AI providers"""
        return [provider.value for provider in AIProvider]

    @staticmethod
    def get_provider_info(provider: AIProvider) -> Dict[str, Any]:
        """Get information about a provider"""
        models = AVAILABLE_MODELS.get(provider, [])
        return {
            "name": provider.value,
            "models": [
                {
                    "name": model.name,
                    "max_tokens": model.max_tokens,
                }
                for model in models
            ],
            "api_configured": bool(AIService.get_api_key(provider)),
        }
