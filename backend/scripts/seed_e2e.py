"""MVP 12 Fase 12.6 — Seed canônico para a lane E2E do CI.

Cria o ambiente mínimo reprodutível que `test_fluxo_completo.py`
espera:
- Admin `admin@gca.local` com senha `SenhaAdmin@2026`, ativo e
  com `first_access_completed=True` (evita bloqueio de 1º login).
- Uma Organization.
- 1 Project com id fixo `00000000-0000-0000-0000-000000000001`
  (casa com `PROJECT_ID = "1"` do teste, convertido para UUID).
- ProjectMember do admin como GP ativo (accepted_at + joined_at
  preenchidos, conforme Fase 12.3).

Executado idempotentemente: se o objeto já existe, faz update dos
campos críticos e segue. Seguro para rodar múltiplas vezes.

Uso:
    python backend/scripts/seed_e2e.py

Ou via env var com DATABASE_URL apontando para o banco de CI.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Permite import do pacote app/ quando chamado de backend/
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from app.core.security import hash_password  # noqa: E402
from app.models.base import Organization, Project, ProjectMember, User  # noqa: E402


ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@gca.local")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASS", "SenhaAdmin@2026")
PROJECT_ID = UUID(os.environ.get("E2E_PROJECT_UUID", "00000000-0000-0000-0000-000000000001"))
PROJECT_SLUG = os.environ.get("E2E_PROJECT_SLUG", "e2e-canary")


async def seed() -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL (ou TEST_DATABASE_URL) não definida. "
            "Exporte a URL do banco alvo antes de rodar."
        )
    engine = create_async_engine(db_url, future=True)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        async with db.begin():
            # Admin canônico
            res = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
            admin = res.scalar_one_or_none()
            if not admin:
                admin = User(
                    email=ADMIN_EMAIL,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    full_name="E2E Admin",
                    is_active=True,
                    is_admin=True,
                    first_access_completed=True,
                    created_at=now,
                )
                db.add(admin)
                await db.flush()
                print(f"[seed] admin criado: {admin.email} ({admin.id})")
            else:
                admin.password_hash = hash_password(ADMIN_PASSWORD)
                admin.is_active = True
                admin.is_admin = True
                admin.first_access_completed = True
                print(f"[seed] admin atualizado: {admin.email} ({admin.id})")

            # Organization
            res = await db.execute(
                select(Organization).where(Organization.name == "E2E Canary Org")
            )
            org = res.scalar_one_or_none()
            if not org:
                org = Organization(
                    name="E2E Canary Org",
                    slug="e2e-canary-org",
                    owner_id=admin.id,
                    is_active=True,
                    created_at=now,
                )
                db.add(org)
                await db.flush()
                print(f"[seed] org criada: {org.slug} ({org.id})")

            # Project (UUID fixo para casar com PROJECT_ID do teste)
            res = await db.execute(select(Project).where(Project.id == PROJECT_ID))
            proj = res.scalar_one_or_none()
            if not proj:
                proj = Project(
                    id=PROJECT_ID,
                    organization_id=org.id,
                    name="E2E Canary Project",
                    slug=PROJECT_SLUG,
                    description="Projeto canônico da lane e2e",
                    deliverable_type="new_system",
                    status="active",
                    created_at=now,
                )
                db.add(proj)
                await db.flush()
                print(f"[seed] project criado: {proj.slug} ({proj.id})")

            # Membership GP do admin (Fase 12.3: accepted_at + joined_at)
            res = await db.execute(
                select(ProjectMember).where(
                    (ProjectMember.project_id == PROJECT_ID)
                    & (ProjectMember.user_id == admin.id)
                )
            )
            mem = res.scalar_one_or_none()
            if not mem:
                db.add(ProjectMember(
                    project_id=PROJECT_ID,
                    user_id=admin.id,
                    role="gp",
                    is_active=True,
                    invited_at=now,
                    accepted_at=now,
                    joined_at=now,
                ))
                print(f"[seed] membership gp criado para admin em {PROJECT_ID}")

    await engine.dispose()
    print("[seed] done.")


if __name__ == "__main__":
    asyncio.run(seed())
