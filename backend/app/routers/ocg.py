"""OCG (Objeto de Contexto Global) Router"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_ocg():
    """List all OCG contexts"""
    return {"message": "TODO: List OCG contexts"}
