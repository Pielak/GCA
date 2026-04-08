"""
LLM Service
Abstração para integração com múltiplos LLM providers
"""
import asyncio
import structlog
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from enum import Enum

logger = structlog.get_logger(__name__)


class LLMProvider(str, Enum):
    """Available LLM providers"""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GROK = "grok"
    DEEPSEEK = "deepseek"


class BaseLLMClient(ABC):
    """Base class for LLM clients"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Generate text from prompt"""
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate API credentials"""
        pass


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "claude-opus-4-1"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Generate code using Claude"""
        try:
            # Import here to avoid dependency if not used
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)

            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            logger.info("llm.generation_success",
                       provider="anthropic",
                       model=self.model,
                       tokens_used=message.usage.output_tokens)

            return message.content[0].text

        except Exception as e:
            logger.error("llm.generation_error",
                        provider="anthropic",
                        error=str(e))
            raise ValueError(f"Claude generation failed: {str(e)}")

    async def validate_credentials(self) -> bool:
        """Validate Anthropic API credentials"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            # Try to call a simple API to validate
            response = client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}]
            )
            return response.content[0].text is not None
        except Exception:
            return False


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gpt-4-turbo-preview"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Generate code using GPT-4"""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            logger.info("llm.generation_success",
                       provider="openai",
                       model=self.model,
                       tokens_used=response.usage.completion_tokens)

            return response.choices[0].message.content

        except Exception as e:
            logger.error("llm.generation_error",
                        provider="openai",
                        error=str(e))
            raise ValueError(f"GPT-4 generation failed: {str(e)}")

    async def validate_credentials(self) -> bool:
        """Validate OpenAI API credentials"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            # Try to list models to validate
            models = client.models.list()
            return len(models.data) > 0
        except Exception:
            return False


class GrokClient(BaseLLMClient):
    """Grok (xAI) client"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "grok-1"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Generate code using Grok"""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature
            }

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.x.ai/v1/completions",
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    raise ValueError(f"Grok API error: {response.status_code}")

                data = response.json()

                logger.info("llm.generation_success",
                           provider="grok",
                           model=self.model)

                return data["choices"][0]["text"]

        except Exception as e:
            logger.error("llm.generation_error",
                        provider="grok",
                        error=str(e))
            raise ValueError(f"Grok generation failed: {str(e)}")

    async def validate_credentials(self) -> bool:
        """Validate Grok API credentials"""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.x.ai/v1/models",
                    headers=headers
                )
                return response.status_code == 200
        except Exception:
            return False


class DeepSeekClient(BaseLLMClient):
    """DeepSeek client"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "deepseek-coder"

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """Generate code using DeepSeek"""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            }

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    raise ValueError(f"DeepSeek API error: {response.status_code}")

                data = response.json()

                logger.info("llm.generation_success",
                           provider="deepseek",
                           model=self.model)

                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error("llm.generation_error",
                        provider="deepseek",
                        error=str(e))
            raise ValueError(f"DeepSeek generation failed: {str(e)}")

    async def validate_credentials(self) -> bool:
        """Validate DeepSeek API credentials"""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.deepseek.com/v1/models",
                    headers=headers
                )
                return response.status_code == 200
        except Exception:
            return False


class LLMServiceFactory:
    """Factory for creating LLM clients"""

    @staticmethod
    def create_client(
        provider: LLMProvider,
        api_key: str
    ) -> BaseLLMClient:
        """Create an LLM client"""

        if provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(api_key)
        elif provider == LLMProvider.OPENAI:
            return OpenAIClient(api_key)
        elif provider == LLMProvider.GROK:
            return GrokClient(api_key)
        elif provider == LLMProvider.DEEPSEEK:
            return DeepSeekClient(api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @staticmethod
    async def validate_all_providers(
        credentials: Dict[str, str]
    ) -> Dict[str, bool]:
        """Validate all LLM provider credentials"""

        results = {}

        for provider_name, api_key in credentials.items():
            if not api_key:
                results[provider_name] = False
                continue

            try:
                provider = LLMProvider(provider_name.lower())
                client = LLMServiceFactory.create_client(provider, api_key)
                results[provider_name] = await client.validate_credentials()
            except Exception as e:
                logger.warning("llm.validation_failed",
                              provider=provider_name,
                              error=str(e))
                results[provider_name] = False

        return results
