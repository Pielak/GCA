"""
GCA Database Setup
SQLAlchemy async engine, base, and session management
"""
from typing import AsyncGenerator, Optional
from contextvars import ContextVar
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ============================================================================
# DATABASE ENGINE
# ============================================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=settings.DATABASE_ECHO,
    connect_args={
        "timeout": 10,
        "command_timeout": 10,
    },
)

# ============================================================================
# SESSION FACTORY
# ============================================================================
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ============================================================================
# DECLARATIVE BASE FOR ORM MODELS
# ============================================================================
Base = declarative_base()


# ============================================================================
# TENANT CONTEXT
# ============================================================================
# Context variable to store current tenant schema name during request
current_tenant_schema: ContextVar[Optional[str]] = ContextVar(
    "current_tenant_schema", default=None
)


def set_tenant_schema(schema_name: str) -> None:
    """Set the current tenant schema for this context"""
    current_tenant_schema.set(schema_name)
    logger.info("tenant.context_set", schema=schema_name)


def get_tenant_schema() -> Optional[str]:
    """Get the current tenant schema"""
    return current_tenant_schema.get()


def clear_tenant_schema() -> None:
    """Clear the tenant schema context"""
    current_tenant_schema.set(None)


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get async database session"""
    async with AsyncSessionLocal() as session:
        yield session


class TenantAwareSession:
    """
    Helper class for tenant-aware database operations.
    Automatically sets search_path to include tenant schema.
    """

    def __init__(self, db: AsyncSession, tenant_schema: str):
        self.db = db
        self.tenant_schema = tenant_schema

    async def _setup_search_path(self) -> None:
        """Set search_path to include tenant schema"""
        if self.tenant_schema:
            # Search path: tenant schema first, then public
            search_path = f"{self.tenant_schema}, public"
            await self.db.execute(text(f"SET search_path = {search_path}"))
            logger.debug("tenant.search_path_set", schema=self.tenant_schema)

    async def __aenter__(self):
        await self._setup_search_path()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.db.rollback()
            logger.error(
                "tenant.session_rollback",
                schema=self.tenant_schema,
                error=str(exc_val),
            )
        else:
            await self.db.commit()


# ============================================================================
# INITIALIZATION
# ============================================================================
async def init_db() -> None:
    """Initialize database by creating all tables"""
    logger.info("database.initialization_start")
    try:
        # Create pgcrypto extension
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("database.initialization_complete")
    except Exception as e:
        logger.error("database.initialization_failed", error=str(e))
        raise
