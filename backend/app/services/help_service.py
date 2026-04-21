"""MVP 18 Fase 18.2 — Serviço de conteúdo do help.

Responsabilidades:
- Ler `help_content/toc.json` e retornar a lista de capítulos.
- Ler `help_content/<section_id>.md` e retornar conteúdo + título.
- Busca: stub em 18.2 (retorna lista vazia + backend="stub");
  implementação FTS5 vem em 18.4.

Abstraído em service (não inline no router) pra:
- Testes podem mockar I/O.
- 18.4 troca o backend de busca sem mexer no router.
- Caching futuro fica fácil.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Raiz do conteúdo canônico. Path relativo ao arquivo do service pra
# funcionar tanto em dev local quanto dentro do container (WORKDIR=/app).
_CONTENT_ROOT = Path(__file__).resolve().parent.parent / "help_content"

# Slug de section_id: letras, números, hífen e underscore. Protege contra
# path traversal (`../`, `/etc/passwd`, etc).
_VALID_SECTION_ID = re.compile(r"^[a-zA-Z0-9_\-]+$")


class HelpContentError(Exception):
    """Erro canônico do módulo help (leitura/validação)."""


@dataclass
class HelpChapter:
    id: str
    title: str
    order: int

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "order": self.order}


@dataclass
class HelpSection:
    id: str
    title: str
    markdown: str

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "markdown": self.markdown}


def _content_root() -> Path:
    """Hook pra testes trocarem a raiz via monkeypatch se necessário."""
    return _CONTENT_ROOT


def load_toc() -> list[HelpChapter]:
    """Lê e ordena os capítulos canônicos do `toc.json`.

    Raises:
        HelpContentError: se `toc.json` ausente, malformado ou sem chapters.
    """
    toc_path = _content_root() / "toc.json"
    if not toc_path.is_file():
        raise HelpContentError(f"toc.json não encontrado em {_content_root()}")
    try:
        raw = json.loads(toc_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HelpContentError(f"toc.json malformado: {exc}") from exc

    chapters_raw = raw.get("chapters") if isinstance(raw, dict) else None
    if not isinstance(chapters_raw, list) or not chapters_raw:
        raise HelpContentError("toc.json sem lista 'chapters' válida")

    chapters: list[HelpChapter] = []
    for item in chapters_raw:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        title = item.get("title")
        order = item.get("order")
        if not isinstance(cid, str) or not isinstance(title, str):
            continue
        if not _VALID_SECTION_ID.match(cid):
            continue
        try:
            order_int = int(order) if order is not None else 0
        except (TypeError, ValueError):
            order_int = 0
        chapters.append(HelpChapter(id=cid, title=title, order=order_int))

    chapters.sort(key=lambda c: (c.order, c.id))
    return chapters


def _extract_title_from_markdown(md: str, fallback: str) -> str:
    """Primeira linha `# Título` vira o título; caso contrário, fallback."""
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def load_section(section_id: str) -> Optional[HelpSection]:
    """Lê `<section_id>.md` e devolve conteúdo + título.

    Retorna `None` se a seção não existe. Levanta `HelpContentError` se
    o `section_id` for inválido (anti path-traversal).
    """
    if not isinstance(section_id, str) or not _VALID_SECTION_ID.match(section_id):
        raise HelpContentError(f"section_id inválido: {section_id!r}")

    md_path = _content_root() / f"{section_id}.md"
    # Defesa em profundidade: `md_path` precisa resolver debaixo da raiz
    # canônica. Sem isso, um symlink apontando pra fora bypasssaria o regex.
    try:
        resolved = md_path.resolve()
        root_resolved = _content_root().resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError):
        raise HelpContentError(f"section_id fora da raiz: {section_id!r}")

    if not md_path.is_file():
        return None

    markdown = md_path.read_text(encoding="utf-8")
    title = _extract_title_from_markdown(markdown, fallback=section_id)
    return HelpSection(id=section_id, title=title, markdown=markdown)


def search_content(query: str, limit: int = 20) -> dict:
    """Busca full-text do help — stub em 18.2.

    Retorna `{"backend": "stub", "query": ..., "results": []}`.
    Implementação real (SQLite FTS5 + indexação dos .md + snippets) vem na
    Fase 18.4. Enquanto isso o frontend pode filtrar títulos localmente.

    O `limit` é aceito pra futuro — guarda no response mas não altera o
    resultado em 18.2. Clamp [1, 100].
    """
    q = (query or "").strip()
    try:
        limit_int = int(limit) if limit is not None else 20
    except (TypeError, ValueError):
        limit_int = 20
    return {
        "backend": "stub",
        "query": q,
        "limit": max(1, min(limit_int, 100)),
        "results": [],
    }
