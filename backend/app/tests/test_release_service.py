"""MVP 7 — testes do release_service.

Cobertura F1:
- parse de YAML (kind/roles/campos obrigatórios válidos)
- sync_declared_releases cria Release + items + idempotência (2ª run não duplica)
- apply_nondestructive_pending marca applied + gera log entry 'applied'
- apply_nondestructive_pending ignora destrutivas (ficam pending)
- list_releases + get_release_with_items
- items_visible_to_role filtra por papel e pelo literal 'all'
- YAML inválido não derruba o startup (retorna só os válidos)
"""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.base import Release, ReleaseApplicationLog, ReleaseItem
from app.services import release_service as svc


def _write_yaml(tmp_dir: Path, filename: str, content: str) -> Path:
    p = tmp_dir / filename
    p.write_text(content, encoding="utf-8")
    return p


# ─── Parse ─────────────────────────────────────────────────────────────────

def test_parse_release_yaml_basic(tmp_path):
    p = _write_yaml(tmp_path, "v1.0.0.yaml", """
tag: v1.0.0
title: "Release inicial"
body: |
  Corpo da release.
is_destructive: false
items:
  - kind: mvp
    ref_id: MVP1
    title: "Base"
    affected_roles: ["all"]
""")
    d = svc._parse_release_yaml(p)
    assert d["tag"] == "v1.0.0"
    assert d["title"] == "Release inicial"
    assert d["is_destructive"] is False
    assert len(d["items"]) == 1
    assert d["items"][0]["kind"] == "mvp"


def test_parse_release_yaml_rejects_invalid_kind(tmp_path):
    p = _write_yaml(tmp_path, "bad.yaml", """
tag: v0.1.0
title: x
items:
  - kind: not_a_kind
    title: x
""")
    with pytest.raises(ValueError, match="kind inválido"):
        svc._parse_release_yaml(p)


def test_parse_release_yaml_rejects_missing_tag(tmp_path):
    p = _write_yaml(tmp_path, "notag.yaml", """
title: x
items: []
""")
    with pytest.raises(ValueError, match="tag"):
        svc._parse_release_yaml(p)


def test_parse_release_yaml_rejects_invalid_role(tmp_path):
    p = _write_yaml(tmp_path, "badrole.yaml", """
tag: v0.2.0
title: x
items:
  - kind: mvp
    title: y
    affected_roles: ["cto"]
""")
    with pytest.raises(ValueError, match="affected_roles"):
        svc._parse_release_yaml(p)


def test_load_declared_releases_skips_invalid(tmp_path):
    _write_yaml(tmp_path, "good.yaml", """
tag: v1.0.0
title: Good
items: []
""")
    _write_yaml(tmp_path, "bad.yaml", """
title: "Sem tag"
items: []
""")
    releases = svc.load_declared_releases(tmp_path)
    assert len(releases) == 1
    assert releases[0]["tag"] == "v1.0.0"


# ─── Sync ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_declared_creates_release_and_items(db_session, tmp_path):
    _write_yaml(tmp_path, "v1.0.0.yaml", """
tag: v1.0.0
title: "Inicial"
is_destructive: false
items:
  - kind: mvp
    ref_id: MVP1
    title: "Base operacional"
    affected_roles: ["all"]
  - kind: fix
    ref_id: BUG-1
    title: "Correção X"
    affected_roles: ["dev"]
""")
    created = await svc.sync_declared_releases(db_session, tmp_path)
    assert len(created) == 1
    rel = created[0]
    assert rel.tag == "v1.0.0"
    assert rel.status == "pending"

    items = (await db_session.execute(
        select(ReleaseItem).where(ReleaseItem.release_id == rel.id)
    )).scalars().all()
    assert len(items) == 2
    kinds = sorted(i.kind for i in items)
    assert kinds == ["fix", "mvp"]


@pytest.mark.asyncio
async def test_sync_declared_is_idempotent(db_session, tmp_path):
    _write_yaml(tmp_path, "v1.0.0.yaml", """
tag: v1.0.0
title: Inicial
items:
  - kind: mvp
    title: Base
""")
    first = await svc.sync_declared_releases(db_session, tmp_path)
    second = await svc.sync_declared_releases(db_session, tmp_path)
    assert len(first) == 1
    assert len(second) == 0  # já existia
    total = (await db_session.execute(
        select(Release).where(Release.tag == "v1.0.0")
    )).scalars().all()
    assert len(total) == 1


# ─── Apply ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_nondestructive_marks_applied_and_logs(db_session, tmp_path):
    _write_yaml(tmp_path, "v1.0.0.yaml", """
tag: v1.0.0-apply
title: X
is_destructive: false
items:
  - kind: mvp
    title: Y
""")
    await svc.sync_declared_releases(db_session, tmp_path)
    applied = await svc.apply_nondestructive_pending(db_session)
    assert len(applied) >= 1
    rel = next(r for r in applied if r.tag == "v1.0.0-apply")
    assert rel.status == "applied"
    assert rel.applied_at is not None

    logs = (await db_session.execute(
        select(ReleaseApplicationLog).where(ReleaseApplicationLog.release_id == rel.id)
    )).scalars().all()
    assert any(l.event_type == "applied" for l in logs)


@pytest.mark.asyncio
async def test_apply_nondestructive_ignores_destructive(db_session, tmp_path):
    _write_yaml(tmp_path, "v2.0.0.yaml", """
tag: v2.0.0-destruct
title: Quebra coisa
is_destructive: true
items:
  - kind: schema_change
    title: Coluna removida
""")
    await svc.sync_declared_releases(db_session, tmp_path)
    applied = await svc.apply_nondestructive_pending(db_session)
    # v2.0.0-destruct NÃO deve estar em applied
    assert all(r.tag != "v2.0.0-destruct" for r in applied)

    rel = (await db_session.execute(
        select(Release).where(Release.tag == "v2.0.0-destruct")
    )).scalar_one()
    assert rel.status == "pending"


# ─── Leitura ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_and_get_release_with_items(db_session, tmp_path):
    _write_yaml(tmp_path, "v0.9.0.yaml", """
tag: v0.9.0-list
title: Foo
items:
  - kind: feature
    title: F1
  - kind: fix
    title: F2
""")
    await svc.sync_declared_releases(db_session, tmp_path)

    all_rel = await svc.list_releases(db_session)
    tags = {r.tag for r in all_rel}
    assert "v0.9.0-list" in tags

    rel = next(r for r in all_rel if r.tag == "v0.9.0-list")
    rel2, items = await svc.get_release_with_items(db_session, rel.id)
    assert rel2.id == rel.id
    assert len(items) == 2
    assert [it.display_order for it in items] == [0, 1]


def test_items_visible_to_role_all_wildcard():
    from unittest.mock import MagicMock
    import json as _json
    it_all = MagicMock(affected_roles=_json.dumps(["all"]))
    it_dev = MagicMock(affected_roles=_json.dumps(["dev"]))
    it_gp = MagicMock(affected_roles=_json.dumps(["gp", "admin"]))
    out = svc.items_visible_to_role([it_all, it_dev, it_gp], role="dev")
    assert it_all in out
    assert it_dev in out
    assert it_gp not in out


def test_items_visible_to_role_admin_sees_own_role():
    from unittest.mock import MagicMock
    import json as _json
    it_admin = MagicMock(affected_roles=_json.dumps(["admin"]))
    it_all = MagicMock(affected_roles=_json.dumps(["all"]))
    out = svc.items_visible_to_role([it_admin, it_all], role="admin")
    assert it_admin in out
    assert it_all in out
