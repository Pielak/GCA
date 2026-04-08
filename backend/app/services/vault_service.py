"""
Vault Service — Armazenamento criptografado de secrets por projeto.
Usa pgcrypto (pgp_sym_encrypt/pgp_sym_decrypt) com chave mestra do .env.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class VaultService:
    """Vault de chaves criptografadas por projeto."""

    def __init__(self):
        self.master_key = settings.GCA_MASTER_KEY
        if len(self.master_key) < 32:
            logger.warning("vault.master_key_too_short", length=len(self.master_key))

    async def store_secret(
        self,
        db: AsyncSession,
        project_id: UUID,
        secret_type: str,
        secret_key: str,
        secret_value: str,
        created_by: UUID | None = None,
    ) -> bool:
        """
        Criptografa e armazena um secret.
        Se já existir (project_id, secret_type, secret_key), sobrescreve.
        """
        try:
            # Verificar se já existe
            result = await db.execute(
                text("""
                    SELECT id FROM project_secrets
                    WHERE project_id = :project_id
                      AND secret_type = :secret_type
                      AND secret_key = :secret_key
                """),
                {
                    "project_id": str(project_id),
                    "secret_type": secret_type,
                    "secret_key": secret_key,
                },
            )
            existing = result.fetchone()

            if existing:
                # Atualizar
                await db.execute(
                    text("""
                        UPDATE project_secrets
                        SET secret_value_encrypted = pgp_sym_encrypt(:value, :master_key),
                            updated_at = :now
                        WHERE project_id = :project_id
                          AND secret_type = :secret_type
                          AND secret_key = :secret_key
                    """),
                    {
                        "value": secret_value,
                        "master_key": self.master_key,
                        "now": datetime.now(timezone.utc),
                        "project_id": str(project_id),
                        "secret_type": secret_type,
                        "secret_key": secret_key,
                    },
                )
            else:
                # Inserir
                await db.execute(
                    text("""
                        INSERT INTO project_secrets
                            (id, project_id, secret_type, secret_key,
                             secret_value_encrypted, created_by, created_at, updated_at)
                        VALUES (
                            gen_random_uuid(), :project_id, :secret_type, :secret_key,
                            pgp_sym_encrypt(:value, :master_key), :created_by, :now, :now
                        )
                    """),
                    {
                        "project_id": str(project_id),
                        "secret_type": secret_type,
                        "secret_key": secret_key,
                        "value": secret_value,
                        "master_key": self.master_key,
                        "created_by": str(created_by) if created_by else None,
                        "now": datetime.now(timezone.utc),
                    },
                )

            await db.commit()
            logger.info("vault.secret_stored", project_id=str(project_id), type=secret_type, key=secret_key)
            return True

        except Exception as e:
            await db.rollback()
            logger.error("vault.store_error", error=str(e), project_id=str(project_id))
            return False

    async def get_secret(
        self,
        db: AsyncSession,
        project_id: UUID,
        secret_type: str,
        secret_key: str,
    ) -> str | None:
        """Recupera e descriptografa um secret."""
        try:
            result = await db.execute(
                text("""
                    SELECT pgp_sym_decrypt(secret_value_encrypted::bytea, :master_key) as value
                    FROM project_secrets
                    WHERE project_id = :project_id
                      AND secret_type = :secret_type
                      AND secret_key = :secret_key
                """),
                {
                    "master_key": self.master_key,
                    "project_id": str(project_id),
                    "secret_type": secret_type,
                    "secret_key": secret_key,
                },
            )
            row = result.fetchone()
            if row:
                return row[0]
            return None

        except Exception as e:
            logger.error("vault.get_error", error=str(e), project_id=str(project_id))
            return None

    async def delete_secret(
        self,
        db: AsyncSession,
        project_id: UUID,
        secret_type: str,
        secret_key: str,
    ) -> bool:
        """Remove um secret."""
        try:
            result = await db.execute(
                text("""
                    DELETE FROM project_secrets
                    WHERE project_id = :project_id
                      AND secret_type = :secret_type
                      AND secret_key = :secret_key
                """),
                {
                    "project_id": str(project_id),
                    "secret_type": secret_type,
                    "secret_key": secret_key,
                },
            )
            await db.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info("vault.secret_deleted", project_id=str(project_id), type=secret_type, key=secret_key)
            return deleted

        except Exception as e:
            await db.rollback()
            logger.error("vault.delete_error", error=str(e))
            return False

    async def list_secrets(
        self,
        db: AsyncSession,
        project_id: UUID,
    ) -> list[dict]:
        """Lista secrets SEM descriptografar valores."""
        try:
            result = await db.execute(
                text("""
                    SELECT secret_type, secret_key, created_at, updated_at
                    FROM project_secrets
                    WHERE project_id = :project_id
                    ORDER BY secret_type, secret_key
                """),
                {"project_id": str(project_id)},
            )
            rows = result.fetchall()
            return [
                {
                    "secret_type": row[0],
                    "secret_key": row[1],
                    "created_at": row[2].isoformat() if row[2] else None,
                    "updated_at": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]

        except Exception as e:
            logger.error("vault.list_error", error=str(e))
            return []

    async def rotate_secret(
        self,
        db: AsyncSession,
        project_id: UUID,
        secret_type: str,
        secret_key: str,
        new_value: str,
    ) -> bool:
        """Atualiza valor criptografado de um secret existente."""
        return await self.store_secret(db, project_id, secret_type, secret_key, new_value)
