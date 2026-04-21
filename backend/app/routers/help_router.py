"""MVP 18 Fase 18.2 — Router /api/v1/help/*.

3 endpoints:
- GET /api/v1/help/toc — lista canônica de capítulos
- GET /api/v1/help/section/{section_id} — conteúdo markdown + título
- GET /api/v1/help/search?q=... — busca (stub em 18.2; FTS5 em 18.4)

Autorização: usuário autenticado (qualquer papel). Conteúdo do help é
global — não segmentado por projeto nem por papel em V1.

RBAC das rotas frontend (`/admin/help` e `/projects/:id/help`) já é
imposto pelos guards existentes (`RequireAdmin` / `ProjectDetailLayout`)
e isso é o que decide quem vê a aba. Os endpoints aqui apenas garantem
autenticação válida.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.middleware.auth import get_current_user_from_token
from app.services.help_service import (
    HelpContentError,
    load_section,
    load_toc,
    search_content,
)


router = APIRouter(prefix="/help", tags=["help"])


def _require_auth(user_id: Optional[UUID]) -> UUID:
    """Middleware canônico do GCA retorna None quando Authorization ausente
    (pra rotas que suportam anônimo). Aqui forçamos 401.
    """
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória para acessar o help",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


@router.get("/toc")
async def get_toc(
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
) -> dict:
    """Retorna a estrutura canônica de capítulos do help."""
    _require_auth(user_id)
    try:
        chapters = load_toc()
    except HelpContentError as exc:
        raise HTTPException(status_code=500, detail=f"Help indisponível: {exc}")
    return {"chapters": [c.as_dict() for c in chapters]}


@router.get("/section/{section_id}")
async def get_section(
    section_id: str,
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
) -> dict:
    """Retorna o conteúdo markdown de uma seção."""
    _require_auth(user_id)
    try:
        section = load_section(section_id)
    except HelpContentError as exc:
        # section_id inválido (path traversal etc) → 400, não 500.
        raise HTTPException(status_code=400, detail=str(exc))
    if section is None:
        raise HTTPException(status_code=404, detail=f"Seção '{section_id}' não encontrada")
    return section.as_dict()


@router.get("/search")
async def search(
    q: str = Query("", description="Termo de busca"),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = Depends(get_current_user_from_token),
) -> dict:
    """Busca full-text no help — stub em 18.2; FTS5 em 18.4."""
    _require_auth(user_id)
    return search_content(q, limit=limit)
