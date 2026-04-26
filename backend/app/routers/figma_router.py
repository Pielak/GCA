"""MVP-H — Endpoints de import nativo de Figma.

Fluxo canônico:
  1. POST /projects/{id}/design/figma/config — owner cola URL/file_key
     + PAT pessoal. Backend valida, persiste file_key em
     project_settings (não-secreto) e PAT criptografado no vault.
  2. POST /projects/{id}/design/figma/import — dispara import:
     puxa variables + frames do Figma, normaliza pros 16 roles
     canônicos do MVP 25, retorna estrutura pra owner aprovar antes
     de gravar no OCG (próxima fase).

PAT é per-projeto e per-owner (não compartilhado entre projetos).
File_key é pública. Não armazenamos screenshots nesta primeira fase.
"""
from __future__ import annotations

import json
import re
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import ProjectSettings
from app.services.figma_import_service import import_figma_design
from app.services.vault_service import VaultService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["design.figma"])


_FIGMA_URL_RE = re.compile(
    r"figma\.com/(?:design|file|board|make)/([A-Za-z0-9]{15,})",
)


def _extract_file_key(url_or_key: str) -> str:
    """Extrai file_key de uma URL Figma ou retorna a string como-está se já
    parecer file_key (alfanumérico, 15+ chars). Levanta ValueError se
    não conseguir."""
    s = (url_or_key or "").strip()
    if not s:
        raise ValueError("URL/file_key vazio")
    m = _FIGMA_URL_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{15,}", s):
        return s
    raise ValueError(
        f"Não foi possível extrair file_key de '{s[:80]}'. "
        "Cole URL completa do Figma ou só o file_key alfanumérico.",
    )


class FigmaConfigRequest(BaseModel):
    url_or_key: str = Field(..., description="URL completa do Figma ou file_key alfanumérico")
    pat: str = Field(..., min_length=10, description="Personal Access Token do Figma (X-Figma-Token)")


class FigmaConfigResponse(BaseModel):
    file_key: str
    has_pat: bool
    last_imported_at: str | None = None
    last_status: str | None = None


class FigmaImportResponse(BaseModel):
    file_name: str
    version: str
    palette_by_role: dict[str, str]
    frames: list[dict[str, str]]
    raw_variable_count: int


async def _get_or_create_settings(
    db: AsyncSession, project_id: UUID,
) -> ProjectSettings:
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "figma",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = ProjectSettings(
            project_id=project_id,
            setting_type="figma",
            settings_json="{}",
        )
        db.add(row)
        await db.flush()
    return row


@router.get(
    "/projects/{project_id}/design/figma/config",
    response_model=FigmaConfigResponse,
    summary="Lê config Figma do projeto (file_key + flag se PAT existe)",
)
async def get_figma_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "figma",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return FigmaConfigResponse(file_key="", has_pat=False)
    try:
        data = json.loads(row.settings_json or "{}")
    except json.JSONDecodeError:
        data = {}
    pat = await VaultService().get_secret(db, project_id, "figma", "pat")
    return FigmaConfigResponse(
        file_key=data.get("file_key") or "",
        has_pat=bool(pat),
        last_imported_at=data.get("last_imported_at"),
        last_status=data.get("last_status"),
    )


@router.post(
    "/projects/{project_id}/design/figma/config",
    response_model=FigmaConfigResponse,
    summary="Salva config Figma (file_key + PAT criptografado)",
)
async def save_figma_config(
    project_id: UUID,
    payload: FigmaConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    try:
        file_key = _extract_file_key(payload.url_or_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings_row = await _get_or_create_settings(db, project_id)
    try:
        data = json.loads(settings_row.settings_json or "{}")
    except json.JSONDecodeError:
        data = {}
    data["file_key"] = file_key
    settings_row.settings_json = json.dumps(data, ensure_ascii=False)
    await db.commit()

    # Vault em session separada — VaultService.store_secret commita
    # internamente; misturar com session do router quebra atomicidade.
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as vault_db:
        ok = await VaultService().store_secret(
            vault_db, project_id, "figma", "pat", payload.pat,
            created_by=current_user_id,
        )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao armazenar PAT no vault.",
        )

    logger.info(
        "figma.config_saved",
        project_id=str(project_id),
        file_key=file_key,
    )
    return FigmaConfigResponse(
        file_key=file_key,
        has_pat=True,
        last_imported_at=data.get("last_imported_at"),
        last_status=data.get("last_status"),
    )


@router.post(
    "/projects/{project_id}/design/figma/import",
    response_model=FigmaImportResponse,
    summary="Importa design tokens + frames do Figma (MVP-H)",
    description=(
        "Lê variables COLOR via Figma REST API, mapeia pros 16 roles "
        "canônicos (primary/secondary/.../brand) por heurística de nome, "
        "e lista frames como specs candidatos a tela do scaffold. Cliente "
        "aprova/edita o resultado antes de gravar no OCG (próxima fase)."
    ),
)
async def import_figma(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_from_token),
):
    # 1. Lê file_key do project_settings
    result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "figma",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Figma não configurado pra este projeto. Salve URL + PAT primeiro.",
        )
    try:
        data = json.loads(row.settings_json or "{}")
    except json.JSONDecodeError:
        data = {}
    file_key = data.get("file_key")
    if not file_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="file_key Figma ausente. Reconfigure.",
        )

    # 2. Lê PAT do vault
    pat = await VaultService().get_secret(db, project_id, "figma", "pat")
    if not pat:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PAT Figma não encontrado no vault. Reconfigure.",
        )

    # 3. Dispara import (chama Figma REST)
    try:
        result_dict = await import_figma_design(
            file_key=file_key,
            pat=pat,
            project_id=project_id,
        )
    except RuntimeError as exc:
        # Atualiza last_status pra UI ver erro persistido
        data["last_status"] = f"erro: {str(exc)[:200]}"
        row.settings_json = json.dumps(data, ensure_ascii=False)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    # 4. Persiste timestamp do último import bem-sucedido
    from datetime import datetime, timezone as _tz
    data["last_imported_at"] = datetime.now(_tz.utc).isoformat()
    data["last_status"] = (
        f"OK — {len(result_dict['palette_by_role'])} roles, "
        f"{len(result_dict['frames'])} frames"
    )
    row.settings_json = json.dumps(data, ensure_ascii=False)
    await db.commit()

    return FigmaImportResponse(**result_dict)
