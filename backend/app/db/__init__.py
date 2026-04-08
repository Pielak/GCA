"""Database module"""
from app.db.database import engine, AsyncSessionLocal, Base, get_db, init_db

# NOTE: Models are imported in database.py via get_alembic_config() and init_db()
# to ensure Base is initialized before model definitions are loaded.
# Do NOT import models here as it creates circular dependencies.

__all__ = [
    "engine", "AsyncSessionLocal", "Base", "get_db", "init_db",
]
