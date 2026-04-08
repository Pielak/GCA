"""
Anthropic Claude API Client
Singleton para integração com Anthropic SDK
"""
from anthropic import Anthropic
from app.core.config import settings
import structlog

logger = structlog.get_logger(__name__)


# Singleton instance
_anthropic_client: Anthropic = None


def get_anthropic_client() -> Anthropic:
    """
    Get or create the Anthropic client singleton.

    Uses ANTHROPIC_API_KEY from settings.
    Falls back to environment variable if settings is empty.

    Returns:
        Anthropic: Initialized Anthropic client
    """
    global _anthropic_client

    if _anthropic_client is None:
        api_key = settings.ANTHROPIC_API_KEY

        if not api_key:
            logger.warning("anthropic.client_warning_no_api_key")
            # Anthropic SDK will try environment variable
            api_key = None

        try:
            _anthropic_client = Anthropic(api_key=api_key)
            logger.info("anthropic.client_initialized", model=settings.ANTHROPIC_MODEL)
        except Exception as e:
            logger.error("anthropic.client_initialization_failed", error=str(e))
            raise

    return _anthropic_client


def reset_client() -> None:
    """
    Reset the singleton client (useful for testing).
    """
    global _anthropic_client
    _anthropic_client = None
