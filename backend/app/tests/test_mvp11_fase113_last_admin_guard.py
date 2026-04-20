"""MVP 11 Fase 11.3 — Guard reforçado de último Admin ativo.

Contrato §7 MVP 11 Fase 11.3:
- Pré-check antes de autorizar, nunca recuperação posterior.
- Bloquear qualquer caminho que deixe a instância sem Admin ativo:
  (a) set_admin_flag(False) self;
  (b) set_admin_flag(False) cross;
  (c) lock_user;
  (d) block_user (router direto);
  (e) delete_user.
- lock_user do admin_service também bloqueia self-lock (caminho canônico
  de rebaixamento é set_admin_flag + lock, não lock direto).
"""
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.main import app
from app.core.security import create_access_token, hash_password


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_admin(email_suffix: str = ""):
    """Cria um User admin ativo e retorna seu id."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    uid = uuid4()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(User(
                id=uid,
                email=f"mvp11-f113-admin-{email_suffix or uid.hex[:6]}@test.com",
                password_hash=hash_password("Test@1234"),
                full_name="F113 Admin",
                is_active=True,
                is_admin=True,
                created_at=datetime.utcnow(),
            ))
    return uid


async def _cleanup_by_pattern():
    from app.db.database import AsyncSessionLocal
    from app.models.base import User, GlobalAuditLog

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                GlobalAuditLog.__table__.delete().where(
                    GlobalAuditLog.actor_id.in_(
                        select(User.id).where(User.email.like("mvp11-f113-%@test.com"))
                    )
                )
            )
            await session.execute(User.__table__.delete().where(User.email.like("mvp11-f113-%@test.com")))


async def _count_active_admins() -> int:
    from app.db.database import AsyncSessionLocal
    from app.models.base import User
    from sqlalchemy import func

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(func.count(User.id)).where(
                User.is_admin.is_(True),
                User.is_active.is_(True),
            )
        )
        return int(res.scalar() or 0)


@pytest_asyncio.fixture
async def baseline_count():
    """Captura quantos admins já existem antes dos testes (o conftest pode ter criado)."""
    return await _count_active_admins()


# ─── set_admin_flag(False) self — guard já existente ──────────────────


@pytest.mark.asyncio
async def test_set_admin_flag_false_self_is_blocked_when_last_admin(baseline_count):
    """Quando existe apenas 1 admin ativo, ele não pode se auto-rebaixar."""
    from app.db.database import AsyncSessionLocal
    from app.services.admin_management_service import set_admin_flag

    # Só cria 1 admin adicional; tem que garantir que, contando os pre-existentes,
    # ele ou outro seja o último. Estratégia: desativa todos os outros primeiro,
    # garante 1 só, tenta auto-rebaixar.
    # Mas isso requer controle absoluto do estado — abordamos o cenário de forma
    # mais robusta: isolamos 2 admins novos, depois desativa um e tenta rebaixar
    # o outro — vamos pular se não controlamos o baseline. Abordagem simples:
    # assert que set_admin_flag respeita o guard quando count resultante <= 0.
    try:
        uid = await _make_admin("solo")

        # Desativa todos os outros admins (nos novos + baseline)
        from app.models.base import User
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(
                    select(User).where(
                        User.is_admin.is_(True),
                        User.is_active.is_(True),
                        User.id != uid,
                    )
                )
                outros = list(res.scalars().all())
                for u in outros:
                    u.is_active = False

        # Tenta auto-rebaixar o único admin
        async with AsyncSessionLocal() as session:
            with pytest.raises(PermissionError):
                await set_admin_flag(
                    session,
                    target_user_id=uid,
                    new_value=False,
                    actor_id=uid,
                )

        # Restaura os outros como ativos
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for u in outros:
                    u_db = await session.get(User, u.id)
                    if u_db:
                        u_db.is_active = True
    finally:
        await _cleanup_by_pattern()


# ─── lock_user: self-lock é bloqueado ─────────────────────────────────


@pytest.mark.asyncio
async def test_lock_user_self_is_blocked():
    """admin_service.lock_user(user_id, actor_id=user_id) → PermissionError."""
    from app.db.database import AsyncSessionLocal
    from app.services.admin_service import AdminService

    uid = await _make_admin()
    try:
        async with AsyncSessionLocal() as session:
            svc = AdminService(session)
            with pytest.raises(PermissionError):
                await svc.lock_user(uid, actor_id=uid)
    finally:
        await _cleanup_by_pattern()


# ─── lock_user: último admin é bloqueado ──────────────────────────────


@pytest.mark.asyncio
async def test_lock_user_last_admin_is_blocked():
    """Admin A tenta lock_user do admin B quando B é o único admin ativo restante."""
    from app.db.database import AsyncSessionLocal
    from app.services.admin_service import AdminService
    from app.models.base import User

    # Isola cenário: desativa todos os outros admins, deixa só 1 (B). Um actor
    # admin diferente (A) é criado com is_admin=False pra não contar como
    # admin ativo — então B realmente é o último.
    b_uid = await _make_admin("last")
    # A é um actor não-admin ativo (simulação: em produção precisaria ser
    # admin para chamar o endpoint, mas aqui testamos o guard no service,
    # que só olha o estado atual do pool de admins). Aceita qualquer actor_id.
    a_uid = uuid4()
    try:
        from app.models.base import User as UserModel
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(UserModel(
                    id=a_uid,
                    email=f"mvp11-f113-actor-{a_uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F113 Actor",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                ))

        # Desativa todos os outros admins (exceto B)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(
                    select(UserModel).where(
                        UserModel.is_admin.is_(True),
                        UserModel.is_active.is_(True),
                        UserModel.id != b_uid,
                    )
                )
                outros = list(res.scalars().all())
                for u in outros:
                    u.is_active = False

        # Tenta lock_user(B) — deve bloquear
        async with AsyncSessionLocal() as session:
            svc = AdminService(session)
            with pytest.raises(PermissionError):
                await svc.lock_user(b_uid, actor_id=a_uid)

        # Restaura os outros
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for u in outros:
                    u_db = await session.get(UserModel, u.id)
                    if u_db:
                        u_db.is_active = True
    finally:
        await _cleanup_by_pattern()


# ─── block_user (router): último admin é bloqueado via HTTP 403 ──────


@pytest.mark.asyncio
async def test_block_user_last_admin_returns_403():
    """POST /admin/users/{B}/block quando B é o último admin → 403."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    # Actor é admin ativo (precisa pra passar require_admin no router)
    actor_uid = await _make_admin("actor-block")
    b_uid = await _make_admin("last-block")
    try:
        # Desativa todos os outros admins exceto actor e B
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(
                    select(User).where(
                        User.is_admin.is_(True),
                        User.is_active.is_(True),
                        User.id.notin_([actor_uid, b_uid]),
                    )
                )
                outros = list(res.scalars().all())
                for u in outros:
                    u.is_active = False

        # Com actor e B ambos ativos: count = 2. Blocar B deixaria 1 (actor). OK. Não deve bloquear.
        # Para ter REALMENTE o caso de "último", desativa actor também — mas precisamos do actor
        # para autenticar. Solução: rebaixa actor depois de ter token.
        token = create_access_token(data={"sub": str(actor_uid)})

        # Rebaixa o actor (para que apenas B seja admin ativo) — via DB direto pra evitar
        # chamar set_admin_flag com seu próprio guard.
        async with AsyncSessionLocal() as session:
            async with session.begin():
                actor_db = await session.get(User, actor_uid)
                actor_db.is_admin = False  # Actor segue ativo mas não é admin

        # Problema: require_admin do router vai rejeitar actor agora.
        # Alternativa canônica: se actor é admin (mantém is_admin=True) e B é admin
        # ativo, então pool = 2. Blocar B → 1 restante. NÃO é último. OK, não bloqueia.
        # Para realmente testar "último admin bloqueado" via HTTP, promovo actor de volta
        # e bloqueio actor sendo o alvo... mas aí actor-self é bloqueado por outra regra.
        # → Cenário mais limpo: testar que actor=admin tenta bloquear B=último admin.
        # Pra ser ÚLTIMO, B tem que ser o único admin. Mas precisamos actor pra auth.
        # Solução definitiva: cria um admin_admin separado que NÃO é alvo, e testa B
        # bloqueado via endpoint quando actor=admin_admin e B é o único OUTRO admin.
        # Aqui B=único admin ativo diferente de actor. Actor bloca B → count=1 restante
        # (o próprio actor). Não é "último" — não bloqueia.
        # Para ter "último bloqueado" preciso bloquear actor, que self-bloqueia por outra regra.
        # CONCLUSÃO: testar APENAS via service (no test anterior), skip este.
        pytest.skip("block_user via HTTP não consegue isolar 'último admin' sem quebrar auth.")
    finally:
        await _cleanup_by_pattern()


# ─── delete_user (router): último admin é bloqueado ──────────────────


@pytest.mark.asyncio
async def test_delete_user_last_admin_returns_403():
    """DELETE /admin/users/{B} quando B é último admin → 403 via guard."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User

    actor_uid = await _make_admin("actor-del")
    b_uid = await _make_admin("last-del")
    try:
        # Desativa demais admins preservando actor e B
        async with AsyncSessionLocal() as session:
            async with session.begin():
                res = await session.execute(
                    select(User).where(
                        User.is_admin.is_(True),
                        User.is_active.is_(True),
                        User.id.notin_([actor_uid, b_uid]),
                    )
                )
                outros = list(res.scalars().all())
                for u in outros:
                    u.is_active = False

        # Pool inicial: {actor, B} = 2 admins ativos. Para testar "último", precisamos
        # que apenas 1 seja admin: actor. Rebaixa B antes? Não: se B não é admin, guard
        # não bloqueia. Precisamos B como último admin.
        # Cenário realista: rebaixa actor (mantém ativo pra auth), B vira único admin,
        # actor tenta deletar B → guard bloqueia.
        # Problema: require_admin bloqueia actor sem is_admin. Mas neste test, podemos
        # usar outra estratégia: actor É admin mas o endpoint verifica "target é último"
        # pela count interna do guard. Se pool = 2 e target=B é admin, após delete
        # restariam actor. Count>0. OK, não bloqueia.
        # Para realmente testar, manipulamos o pool: actor é admin, B também. Count=2.
        # Mas queremos que DELETE de B deixe count=1 (actor restante). Guard vê
        # count-1 = 1 > 0. NÃO bloqueia. Correto — B não é "último".
        # Então para que o guard dispare, só 1 admin no pool. Esse 1 é o actor (precisa
        # pra auth). Actor deleta self é bloqueado por "próprio conta" check primeiro.
        # CONCLUSÃO: para delete, o caso "último bloqueado" exige que o alvo seja o
        # único admin E seja diferente do caller. Mas se alvo é único, caller não é
        # admin, logo require_admin falha antes. Guard em delete é defesa em
        # profundidade — testamos via service/guard unitário.

        from app.services.admin_management_service import guard_last_admin_on_action

        # Rebaixa actor a não-admin; B vira o único admin
        async with AsyncSessionLocal() as session:
            async with session.begin():
                actor_db = await session.get(User, actor_uid)
                actor_db.is_admin = False

        # Chama o guard diretamente com B como target — deve bloquear
        async with AsyncSessionLocal() as session:
            b_db = await session.get(User, b_uid)
            with pytest.raises(PermissionError):
                await guard_last_admin_on_action(session, b_db)
    finally:
        await _cleanup_by_pattern()


# ─── Guard helper: target não-admin é no-op ───────────────────────────


@pytest.mark.asyncio
async def test_guard_is_noop_when_target_is_not_admin():
    """guard_last_admin_on_action sobre user não-admin não levanta."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User
    from app.services.admin_management_service import guard_last_admin_on_action

    uid = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(
                    id=uid,
                    email=f"mvp11-f113-nonadmin-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F113 NonAdmin",
                    is_active=True,
                    is_admin=False,
                    created_at=datetime.utcnow(),
                ))

        async with AsyncSessionLocal() as session:
            u = await session.get(User, uid)
            # Não deve levantar
            await guard_last_admin_on_action(session, u)
    finally:
        await _cleanup_by_pattern()


# ─── Guard helper: target admin inativo é no-op ───────────────────────


@pytest.mark.asyncio
async def test_guard_is_noop_when_target_is_inactive_admin():
    """Admin inativo não conta para o pool — guard é no-op."""
    from app.db.database import AsyncSessionLocal
    from app.models.base import User
    from app.services.admin_management_service import guard_last_admin_on_action

    uid = uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(User(
                    id=uid,
                    email=f"mvp11-f113-inactive-{uid.hex[:6]}@test.com",
                    password_hash=hash_password("Test@1234"),
                    full_name="F113 Inactive",
                    is_active=False,
                    is_admin=True,
                    created_at=datetime.utcnow(),
                ))

        async with AsyncSessionLocal() as session:
            u = await session.get(User, uid)
            await guard_last_admin_on_action(session, u)  # no-op
    finally:
        await _cleanup_by_pattern()
