"""MVP 18 Fases 18.2 + 18.4 — Serviço de conteúdo do help.

Responsabilidades:
- Ler `help_content/toc.json` e retornar a lista de capítulos.
- Ler `help_content/<section_id>.md` e retornar conteúdo + título.
- Buscar termo nos 10 capítulos via SQLite FTS5 (18.4):
  * Index construído lazy na primeira chamada (cache in-memory :memory:).
  * Rebuild automático se algum .md mudar (mtime tracking).
  * Retorna snippets destacando o termo (função `snippet()` do FTS5).

Abstraído em service pra testes + troca de backend sem mexer no router.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
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


# MVP 18 Fase 18.4 — FTS5 index
# ------------------------------------------------------------------
# Index vive em SQLite :memory: compartilhado. Construído lazy na primeira
# busca e reconstruído quando qualquer .md mudar (mtime). Lock pra evitar
# corrida em múltiplas requests concorrentes.

_index_lock = threading.Lock()
_index_conn: Optional[sqlite3.Connection] = None
_index_mtime: float = 0.0


def _corpus_mtime() -> float:
    """mtime máximo entre toc.json + todos os .md. Zero se diretório vazio."""
    root = _content_root()
    if not root.is_dir():
        return 0.0
    mtimes = [p.stat().st_mtime for p in root.glob("*.md")]
    toc = root / "toc.json"
    if toc.is_file():
        mtimes.append(toc.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0


def _build_fts_index() -> sqlite3.Connection:
    """Cria FTS5 virtual table :memory: e popula com o conteúdo atual."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(
        "CREATE VIRTUAL TABLE help_fts USING fts5("
        "  section_id UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2'"
        ")"
    )
    try:
        chapters = load_toc()
    except HelpContentError:
        chapters = []
    chapter_by_id = {c.id: c for c in chapters}

    root = _content_root()
    for md_path in sorted(root.glob("*.md")):
        section_id = md_path.stem
        if not _VALID_SECTION_ID.match(section_id):
            continue
        markdown = md_path.read_text(encoding="utf-8")
        title = _extract_title_from_markdown(
            markdown,
            fallback=chapter_by_id.get(section_id).title if section_id in chapter_by_id else section_id,
        )
        conn.execute(
            "INSERT INTO help_fts(section_id, title, body) VALUES (?, ?, ?)",
            (section_id, title, markdown),
        )
    conn.commit()
    return conn


def _ensure_index() -> sqlite3.Connection:
    """Retorna conn FTS5. Reconstrói se o corpus mudou desde a última build."""
    global _index_conn, _index_mtime
    with _index_lock:
        current_mtime = _corpus_mtime()
        if _index_conn is None or current_mtime > _index_mtime:
            if _index_conn is not None:
                try:
                    _index_conn.close()
                except Exception:  # noqa: BLE001
                    pass
            _index_conn = _build_fts_index()
            _index_mtime = current_mtime
        return _index_conn


def _reset_index() -> None:
    """Uso interno de testes: invalida o cache (força rebuild na próxima)."""
    global _index_conn, _index_mtime
    with _index_lock:
        if _index_conn is not None:
            try:
                _index_conn.close()
            except Exception:  # noqa: BLE001
                pass
        _index_conn = None
        _index_mtime = 0.0


# FTS5 MATCH aceita sintaxe própria (AND, OR, NEAR, *). Pra query livre
# do user sanitizamos: aspas removidas, operadores não-autorizados viram
# prefix search por termo.
_FTS_SANITIZE = re.compile(r'["]')


def _sanitize_fts_query(q: str) -> str:
    """Transforma query livre em FTS5 MATCH válido.

    Estratégia conservadora: quebra por whitespace, aspas em cada termo
    (evita que o FTS5 interprete como operador), junta com OR implícito.
    Resultado: busca por qualquer palavra do user.
    """
    clean = _FTS_SANITIZE.sub("", q).strip()
    if not clean:
        return ""
    # Cada termo vira '"termo"' (exact-prefix quando possível).
    tokens = [t for t in clean.split() if t]
    if not tokens:
        return ""
    # Junta com OR explícito pra máximo recall; FTS5 ranking faz o resto.
    return " OR ".join(f'"{t}"' for t in tokens)


def search_content(query: str, limit: int = 20) -> dict:
    """Busca full-text no help via FTS5.

    Retorna `{backend, query, limit, results}`. Cada result tem
    `{section_id, title, snippet, rank}`. Snippet com match destacado
    via tags `<mark>...</mark>`.
    """
    q = (query or "").strip()
    try:
        limit_int = int(limit) if limit is not None else 20
    except (TypeError, ValueError):
        limit_int = 20
    limit_int = max(1, min(limit_int, 100))

    if not q:
        return {"backend": "fts5", "query": "", "limit": limit_int, "results": []}

    match_expr = _sanitize_fts_query(q)
    if not match_expr:
        return {"backend": "fts5", "query": q, "limit": limit_int, "results": []}

    conn = _ensure_index()
    results: list[dict] = []
    try:
        cursor = conn.execute(
            "SELECT section_id, title, "
            "  snippet(help_fts, 2, '<mark>', '</mark>', '…', 16) AS snip, "
            "  rank "
            "FROM help_fts WHERE help_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (match_expr, limit_int),
        )
        for row in cursor.fetchall():
            results.append(
                {
                    "section_id": row[0],
                    "title": row[1],
                    "snippet": row[2] or "",
                    "rank": row[3],
                }
            )
    except sqlite3.OperationalError:
        # FTS5 pode recusar queries degeneradas; retorna vazio em vez de 500.
        return {"backend": "fts5", "query": q, "limit": limit_int, "results": []}

    return {"backend": "fts5", "query": q, "limit": limit_int, "results": results}
