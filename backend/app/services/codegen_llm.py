"""DT-079 — Porta única para chamadas LLM do CodeGen.

Antes (até 2026-05-02): `module_codegen_service.py` e `code_generation.py`
instanciavam `AsyncAnthropic` direto e liam `settings.ANTHROPIC_API_KEY` /
`settings.ANTHROPIC_MODEL` em 8 pontos. Violava §3.1 do contrato canônico
(porta única para resolução de provider de IA é `AIKeyResolver`).

Depois (2026-05-03): este módulo expõe `call_codegen_llm`, que delega a
`AIKeyResolver` + `llm_low_criticality.call_llm`. Provider, modelo, chave
e base_url vêm do projeto via `project_settings.setting_type='llm'`. Sem
hardcode de provider em CodeGen.

Contrato §6.2 (criticidade): CodeGen é tarefa **média/alta**. Por isso
`prefer_ollama=False` — respeita a escolha do owner. Ollama só é usado se
estiver configurado como default do projeto, não como fallback silencioso.
"""
from typing import Optional
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_low_criticality import (
    call_llm,
    clamp_max_tokens,
    resolve_llm_config,
)

logger = structlog.get_logger(__name__)


async def call_codegen_llm(
    *,
    db: AsyncSession,
    project_id: UUID,
    user_prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    log_context: str = "codegen.llm",
    expect_json: bool = False,
    auto_continue: bool = True,
) -> str:
    """Resolve provider via AIKeyResolver e chama LLM. Retorna texto cru.

    Levanta HTTPException 503 quando o projeto não tem provider configurado
    — mesmo contrato dos endpoints HTTP que usavam `app_settings.ANTHROPIC_API_KEY`.

    Args:
        db: AsyncSession ativa.
        project_id: UUID do projeto. AIKeyResolver lê `project_settings`.
        user_prompt: prompt principal.
        system_prompt: system message (opcional).
        max_tokens: budget de output. Será clampado pelo provider/model.
        temperature: default 0.3 (igual ao hardcode antigo).
        log_context: prefixo dos logs estruturados.
        expect_json: se True, valida JSON e re-prompta caller.
        auto_continue: se True, continuação automática em truncamento.

    Returns:
        Texto cru retornado pelo LLM (sem parse).

    Raises:
        HTTPException 503 se nenhum provider configurado para o projeto.
    """
    config = await resolve_llm_config(db, project_id, prefer_ollama=False)
    if config is None:
        logger.warning(
            f"{log_context}.no_provider_configured",
            project_id=str(project_id),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Projeto sem LLM configurado para CodeGen. "
                "GP deve configurar provedor em Settings → IA."
            ),
        )

    # Clamp ao cap conhecido do model (Opus=32k, DeepSeek=8k, etc).
    capped = clamp_max_tokens(config["model"], max_tokens)

    logger.info(
        f"{log_context}.dispatch",
        project_id=str(project_id),
        provider=config["provider"],
        model=config["model"],
        max_tokens=capped,
    )

    return await call_llm(
        config=config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=capped,
        temperature=temperature,
        log_context=log_context,
        auto_continue=auto_continue,
        expect_json=expect_json,
    )


async def resolve_codegen_provider_meta(
    db: AsyncSession, project_id: UUID
) -> Optional[dict]:
    """Retorna metadata do provider que será usado para CodeGen.

    Útil para gravar `GeneratedModule.llm_provider` / `llm_model` antes de
    disparar a chamada (para que o registro reflita o que de fato será usado,
    não o hardcode antigo de "anthropic"/"claude-opus-4-0-20250514").

    Retorna `{"provider": ..., "model": ...}` ou None se nenhum provider
    estiver configurado (caller decide entre criar registro com None/None ou
    abortar com erro).
    """
    config = await resolve_llm_config(db, project_id, prefer_ollama=False)
    if config is None:
        return None
    return {
        "provider": config["provider"],
        "model": config["model"],
    }
