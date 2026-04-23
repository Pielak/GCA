"""MVP 18 Fase 18.2 — testes do help_service + endpoints.

Valida:
- load_toc: lê toc.json canônico; ordena; ignora entradas malformadas.
- load_section: lê .md existente; retorna None p/ inexistente; rejeita
  path traversal; rejeita section_id inválido.
- search_content: stub retorna dict canônico (backend=stub, results=[]).
- Endpoints /help/{toc,section/{id},search} autorizados + 404 pra seção
  ausente + 400 pra section_id inválido.
"""
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.models.base import User
from app.core.security import create_access_token, hash_password
from app.db.database import AsyncSessionLocal
from app.services import help_service
from app.services.help_service import (
    HelpChapter,
    HelpContentError,
    HelpSection,
    load_section,
    load_toc,
    search_content,
)


# ===========================================================================
# load_toc
# ===========================================================================

def test_load_toc_retorna_capitulos_canonicos():
    """toc.json canônico evolui com MVPs: 12 em MVP 21, 13 em MVP 23, 14 em MVP 24, 15 em MVP 25."""
    chapters = load_toc()
    assert len(chapters) == 15
    # Primeiro = visão geral (order=1).
    assert chapters[0].id == "01-visao-geral"
    assert chapters[0].title == "Visão geral & Glossário"
    assert chapters[0].order == 1
    # Último canônico (MVP 25) = Design Tokens.
    assert chapters[-1].id == "15-design-tokens"


def test_load_toc_retorna_instancias_help_chapter():
    for c in load_toc():
        assert isinstance(c, HelpChapter)
        assert c.id and c.title
        assert isinstance(c.order, int)


def test_load_toc_ids_unicos_e_ordenados():
    chapters = load_toc()
    ids = [c.id for c in chapters]
    assert len(set(ids)) == len(ids), "IDs duplicados no toc.json"
    orders = [c.order for c in chapters]
    assert orders == sorted(orders), "Capítulos não ordenados por order"


def test_load_toc_ignora_entrada_malformada(tmp_path, monkeypatch):
    """Entradas sem id/title ou com id inválido são silenciosamente puladas."""
    fake_toc = {
        "chapters": [
            {"id": "valida", "title": "Ok", "order": 1},
            {"id": "../escape", "title": "Path traversal", "order": 2},
            {"title": "Sem id", "order": 3},
            {"id": "sem-titulo", "order": 4},
            "string solta",  # não-dict
            {"id": "ok2", "title": "Ok2", "order": 5},
        ]
    }
    (tmp_path / "toc.json").write_text(json.dumps(fake_toc), encoding="utf-8")
    monkeypatch.setattr(help_service, "_content_root", lambda: tmp_path)
    chapters = load_toc()
    ids = [c.id for c in chapters]
    assert ids == ["valida", "ok2"]


def test_load_toc_falha_se_arquivo_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(help_service, "_content_root", lambda: tmp_path)
    with pytest.raises(HelpContentError, match="toc.json não encontrado"):
        load_toc()


def test_load_toc_falha_se_json_malformado(tmp_path, monkeypatch):
    (tmp_path / "toc.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(help_service, "_content_root", lambda: tmp_path)
    with pytest.raises(HelpContentError, match="malformado"):
        load_toc()


# ===========================================================================
# load_section
# ===========================================================================

def test_load_section_retorna_md_existente():
    section = load_section("01-visao-geral")
    assert isinstance(section, HelpSection)
    assert section.id == "01-visao-geral"
    assert section.title == "Visão geral & Glossário"
    assert "# Visão geral" in section.markdown


def test_load_section_inexistente_retorna_none():
    assert load_section("99-nao-existe") is None


def test_load_section_rejeita_path_traversal():
    """Regex valida section_id antes de tocar filesystem."""
    with pytest.raises(HelpContentError, match="inválido"):
        load_section("../etc/passwd")
    with pytest.raises(HelpContentError, match="inválido"):
        load_section("foo/bar")
    with pytest.raises(HelpContentError, match="inválido"):
        load_section(".hidden")


def test_load_section_rejeita_tipo_nao_string():
    with pytest.raises(HelpContentError, match="inválido"):
        load_section(None)  # type: ignore[arg-type]
    with pytest.raises(HelpContentError, match="inválido"):
        load_section(123)  # type: ignore[arg-type]


def test_load_section_rejeita_string_vazia():
    with pytest.raises(HelpContentError, match="inválido"):
        load_section("")


def test_load_section_fallback_title_sem_h1(tmp_path, monkeypatch):
    """Se o .md não tem `# Título` na primeira linha, usa section_id."""
    (tmp_path / "toc.json").write_text(
        json.dumps({"chapters": [{"id": "foo", "title": "Foo", "order": 1}]}),
        encoding="utf-8",
    )
    (tmp_path / "foo.md").write_text("sem header aqui\n\nparágrafo", encoding="utf-8")
    monkeypatch.setattr(help_service, "_content_root", lambda: tmp_path)
    section = load_section("foo")
    assert section is not None
    assert section.title == "foo"


# ===========================================================================
# search_content — backend fts5 (MVP 18 Fase 18.4)
#
# Testes de busca detalhados vivem em test_mvp18_fase184_fts5.py.
# Aqui só sanity checks do contrato de resposta compartilhado com 18.2.
# ===========================================================================

def test_search_query_vazia_retorna_results_vazio():
    result = search_content("")
    assert result["query"] == ""
    assert result["results"] == []


def test_search_aplica_limit_clamp():
    # Com query vazia não faz match, mas o clamp do limit deve funcionar.
    assert search_content("", limit=0)["limit"] == 1
    assert search_content("", limit=500)["limit"] == 100
    assert search_content("", limit=20)["limit"] == 20


# ===========================================================================
# Endpoints HTTP
# ===========================================================================

def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _make_user() -> tuple[User, str]:
    """Cria user real no gca_test + token JWT."""
    from uuid import uuid4
    from datetime import datetime
    async with AsyncSessionLocal() as session:
        async with session.begin():
            uid = uuid4()
            user = User(
                id=uid,
                email=f"help-{uid.hex[:6]}@example.com",
                password_hash=hash_password("Test@1234"),
                full_name="Help Tester",
                is_active=True,
                is_admin=False,
                created_at=datetime.utcnow(),
            )
            session.add(user)
    token = create_access_token(data={"sub": str(uid)})
    return user, token


@pytest.mark.asyncio
async def test_endpoint_toc_retorna_capitulos():
    _user, token = await _make_user()
    async with _client() as client:
        resp = await client.get(
            "/api/v1/help/toc",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "chapters" in body
    assert len(body["chapters"]) == 15
    assert body["chapters"][0]["id"] == "01-visao-geral"
    assert body["chapters"][-1]["id"] == "15-design-tokens"


@pytest.mark.asyncio
async def test_endpoint_toc_exige_autenticacao():
    async with _client() as client:
        resp = await client.get("/api/v1/help/toc")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_endpoint_section_retorna_md_existente():
    _user, token = await _make_user()
    async with _client() as client:
        resp = await client.get(
            "/api/v1/help/section/01-visao-geral",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "01-visao-geral"
    assert body["title"] == "Visão geral & Glossário"
    assert "markdown" in body
    assert "Visão geral" in body["markdown"]


@pytest.mark.asyncio
async def test_endpoint_section_retorna_404_para_inexistente():
    _user, token = await _make_user()
    async with _client() as client:
        resp = await client.get(
            "/api/v1/help/section/99-nao-existe",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_endpoint_section_rejeita_path_traversal_com_400():
    _user, token = await _make_user()
    async with _client() as client:
        # FastAPI path param aceita sem interpretar barras — mas nosso
        # regex rejeita ponto. Testamos id inválido mas URL-válido.
        resp = await client.get(
            "/api/v1/help/section/.hidden",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_endpoint_search_retorna_backend_fts5():
    """Smoke: endpoint responde 200 + backend canônico. Detalhes em 18.4."""
    _user, token = await _make_user()
    async with _client() as client:
        resp = await client.get(
            "/api/v1/help/search?q=ocg",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "fts5"
    assert body["query"] == "ocg"
    assert isinstance(body["results"], list)
