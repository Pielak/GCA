"""Router para gestao de GPs pelo Admin."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.middleware.auth import require_admin
from app.services.gp_management_service import GPManagementService

router = APIRouter(prefix="/admin/projects", tags=["Admin GP Management"])


class ManageGPRequest(BaseModel):
    action: str  # "add", "remove", "replace"
    email: str | None = None
    remove_user_id: UUID | None = None


@router.post("/{project_id}/manage-gp")
async def manage_gp(
    project_id: UUID,
    request: ManageGPRequest,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Gerenciar GPs de um projeto (adicionar, remover, substituir)."""
    service = GPManagementService()

    if request.action == "add":
        if not request.email:
            raise HTTPException(status_code=422, detail="Email e obrigatorio para adicionar GP")
        result = await service.add_gp(db, project_id, request.email, admin_id)
    elif request.action == "remove":
        if not request.remove_user_id:
            raise HTTPException(status_code=422, detail="remove_user_id e obrigatorio para remover GP")
        result = await service.remove_gp(db, project_id, request.remove_user_id, admin_id)
    elif request.action == "replace":
        if not request.email or not request.remove_user_id:
            raise HTTPException(status_code=422, detail="email e remove_user_id sao obrigatorios para substituir GP")
        result = await service.replace_gp(db, project_id, request.remove_user_id, request.email, admin_id)
    else:
        raise HTTPException(status_code=422, detail=f"Acao invalida: {request.action}")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
