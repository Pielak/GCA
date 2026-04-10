"""Endpoints para gestao de papeis multiplos por membro."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.require_action import require_action
from app.services.member_roles_service import MemberRolesService

router = APIRouter(tags=["Member Roles"])
service = MemberRolesService()

VALID_ADDITIONAL_ROLES = {"tech_lead", "dev_senior", "dev_pleno", "qa", "compliance", "stakeholder"}


class AddRolesRequest(BaseModel):
    roles: list[str]


@router.get("/projects/{project_id}/members/self/roles")
async def get_my_roles(
    project_id: UUID,
    permissions: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna meus papeis no projeto."""
    user_id = permissions["user_id"]
    roles = await service.get_member_roles(db, project_id, user_id)
    return {"roles": roles}


@router.post("/projects/{project_id}/members/self/roles")
async def add_my_roles(
    project_id: UUID,
    request: AddRolesRequest,
    permissions: dict = Depends(require_action("project:manage_team")),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona papeis ao meu membro no projeto (auto-atribuicao GP)."""
    user_id = permissions["user_id"]
    invalid = set(request.roles) - VALID_ADDITIONAL_ROLES
    if invalid:
        raise HTTPException(status_code=422, detail=f"Papeis invalidos: {invalid}")

    result = await service.add_roles(db, project_id, user_id, request.roles, user_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/projects/{project_id}/audit/roles")
async def get_role_audit(
    project_id: UUID,
    permissions: dict = Depends(require_action("audit:view")),
    db: AsyncSession = Depends(get_db),
):
    """Historico de atribuicoes de papeis no projeto."""
    audit = await service.get_role_audit(db, project_id)
    return {"audit": audit}
