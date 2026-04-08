"""Users Router"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_users():
    """List all users"""
    return {"message": "TODO: List users"}
