"""Tabela de capacidades por modelo LLM.

Usada pelo pipeline para ajustar chunk size, max_tokens e estratégia
de prompt conforme a IA configurada pelo usuário. Provider-agnóstico.

A tabela é estática (dict Python) — sem migrations necessárias.
Para adicionar novo modelo, basta inserir uma entrada no dict.
"""
from __future__ import annotations
from typing import TypedDict


class ModelCapability(TypedDict):
    context_window: int       # tokens total (input + output)
    max_output: int           # max tokens de saída
    recommended_chunk_size: int  # chars por chunk
    json_reliability: str     # "high" | "medium" | "low"
    supports_long_prompts: bool  # se consegue processar prompts > 30 chunks


# Tabela canônica. Providers/modelos conhecidos.
# Para modelos não listados, usa-se FALLBACK (conservador).
KNOWN_MODELS: dict[str, ModelCapability] = {
    # ── Anthropic Claude ──
    "claude-opus-4-7": {
        "context_window": 200000,
        "max_output": 8192,
        "recommended_chunk_size": 3000,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "claude-opus-4-6": {
        "context_window": 200000,
        "max_output": 8192,
        "recommended_chunk_size": 3000,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "claude-sonnet-4-6": {
        "context_window": 200000,
        "max_output": 8192,
        "recommended_chunk_size": 3000,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "claude-sonnet-4-5": {
        "context_window": 200000,
        "max_output": 8192,
        "recommended_chunk_size": 3000,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "claude-haiku-4-5": {
        "context_window": 200000,
        "max_output": 4096,
        "recommended_chunk_size": 2000,
        "json_reliability": "medium",
        "supports_long_prompts": True,
    },
    "claude-3-haiku": {
        "context_window": 200000,
        "max_output": 4096,
        "recommended_chunk_size": 2000,
        "json_reliability": "medium",
        "supports_long_prompts": True,
    },

    # ── OpenAI ──
    "gpt-4o": {
        "context_window": 128000,
        "max_output": 4096,
        "recommended_chunk_size": 2500,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "gpt-4o-mini": {
        "context_window": 128000,
        "max_output": 4096,
        "recommended_chunk_size": 2000,
        "json_reliability": "medium",
        "supports_long_prompts": True,
    },

    # ── DeepSeek ──
    "deepseek-v4-pro": {
        "context_window": 64000,
        "max_output": 6000,
        "recommended_chunk_size": 1500,
        "json_reliability": "low",
        "supports_long_prompts": False,
    },

    # ── Google Gemini ──
    "gemini-2.5-pro": {
        "context_window": 1048576,
        "max_output": 8192,
        "recommended_chunk_size": 4000,
        "json_reliability": "high",
        "supports_long_prompts": True,
    },
    "gemini-2.5-flash": {
        "context_window": 1048576,
        "max_output": 4096,
        "recommended_chunk_size": 3000,
        "json_reliability": "medium",
        "supports_long_prompts": True,
    },
}

FALLBACK: ModelCapability = {
    "context_window": 32000,
    "max_output": 4000,
    "recommended_chunk_size": 1000,
    "json_reliability": "low",
    "supports_long_prompts": False,
}


def get_model_capability(model_name: str) -> ModelCapability:
    """Retorna capacidade do modelo ou FALLBACK se desconhecido.

    Faz match flexível: 'deepseek-v4-pro' busca exato,
    'deepseek' busca por substring nas chaves conhecidas.
    """
    if not model_name:
        return FALLBACK

    # Match exato primeiro
    if model_name in KNOWN_MODELS:
        return KNOWN_MODELS[model_name]

    # Match flexível por substring
    for key, cap in KNOWN_MODELS.items():
        if key in model_name or model_name in key:
            return cap

    return FALLBACK
