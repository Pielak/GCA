"""Auto-generators de entregáveis (Fase C).

Cada generator produz um artefato concreto a partir do OCG e o commita
no repositório Git do projeto. Espelha o pattern dos verifiers:

    @register_generator("compliance_doc")
    async def _gen_compliance_doc(project_id, db, ocg_data) -> GeneratorResult:
        ...

Após gerar e commitar, o generator NÃO atualiza diretamente
project_deliverables. Em vez disso, o caller (auto-trigger ou endpoint
manual) deve re-rodar o verifier do mesmo kind — que detectará o arquivo
no Git e marcará status='verified'. Isso mantém UMA fonte de verdade:
o verifier.

Generators são tipicamente determinísticos (templates Markdown, CycloneDX,
mermaid). Onde LLM ajuda (DDL inferido), envolvemos via AIService com
fallback para deterministic-best-effort.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GeneratorResult:
    """Resultado de uma execução de generator.

    - committed=True + path: arquivo gerado e commitado em Git no path indicado.
    - committed=False + skipped_reason: generator decidiu não gerar (ex: dados
      insuficientes no OCG, arquivo já existe e seria sobrescrito).
    - Em erro: levanta exception (caller wrappa).
    """
    kind: str
    committed: bool
    path: Optional[str] = None
    bytes_written: int = 0
    skipped_reason: Optional[str] = None
    notes: Optional[str] = None


# Type alias do callable: (project_id, db, ocg_data) -> GeneratorResult
GeneratorFn = Callable[[UUID, AsyncSession, Dict[str, Any]], Awaitable[GeneratorResult]]


_GENERATORS: Dict[str, GeneratorFn] = {}


def register_generator(kind: str) -> Callable[[GeneratorFn], GeneratorFn]:
    """Decorator: registra ``fn`` como generator para o ``kind`` informado.

    Uso:
        @register_generator("compliance_doc")
        async def _gen_compliance_doc(project_id, db, ocg_data):
            ...

    Permite plugin pattern para Fase D+ (novos kinds sem editar dispatch).
    """
    def decorator(fn: GeneratorFn) -> GeneratorFn:
        _GENERATORS[kind] = fn
        return fn
    return decorator


def list_generator_kinds() -> list[str]:
    """Lista kinds que têm generator registrado (útil para auto-trigger
    decidir quais entregáveis tentar gerar)."""
    return sorted(_GENERATORS.keys())


def has_generator(kind: str) -> bool:
    return kind in _GENERATORS


async def generate_kind(
    kind: str,
    project_id: UUID,
    db: AsyncSession,
    ocg_data: Dict[str, Any],
) -> GeneratorResult:
    """Dispatcher: roteia kind para o generator registrado.

    Kinds sem generator devolvem committed=False com motivo. Exceptions
    do generator são propagadas ao caller (que decide log + skip).
    """
    fn = _GENERATORS.get(kind)
    if fn is None:
        return GeneratorResult(
            kind=kind,
            committed=False,
            skipped_reason=f"sem generator registrado para '{kind}'",
        )
    return await fn(project_id, db, ocg_data)


# ──────────────────────────── Helper de commit Git ───────────────────

async def _commit_via_git(
    project_id: UUID,
    db: AsyncSession,
    path: str,
    content: str,
    commit_message: str,
) -> bool:
    """Commita ``content`` em ``path`` no repo Git do projeto.

    Returns True se sucesso, False se falhou (loga warning). Não levanta —
    generator decide se isso é fatal.
    """
    try:
        from app.services.git_service import GitService
        gs = GitService(db)
        result = await gs.commit_file(
            project_id=project_id,
            file_path=path,
            content=content,
            commit_message=commit_message,
        )
        return bool(result.get("success"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "deliverable_generator.git_commit_failed",
            project_id=str(project_id),
            path=path,
            error=str(exc),
        )
        return False


# ──────────────────────────── Generators concretos ───────────────────
# Importados em deliverable_generators_impl.py (separação para evitar
# import circular: o registry pode ser importado por outros módulos sem
# carregar todos os impls).

from app.services import deliverable_generators_impl  # noqa: F401, E402
