"""Persistência de documentos ingeridos em filesystem.

Estrutura: <STORAGE_ROOT>/ingested/<project_id>/<filename>
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

STORAGE_ROOT = Path("/app/storage")


def ingested_path(project_id: UUID, filename: str) -> Path:
    """Caminho final do documento no filesystem."""
    return STORAGE_ROOT / "ingested" / str(project_id) / filename


def write_ingested(project_id: UUID, filename: str, content: bytes) -> Path:
    """Grava bytes em disco, cria diretório se necessário. Retorna path absoluto."""
    target = ingested_path(project_id, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def read_ingested(project_id: UUID, filename: str) -> bytes | None:
    """Lê bytes do disco. Retorna None se arquivo não existe."""
    target = ingested_path(project_id, filename)
    if not target.exists() or not target.is_file():
        return None
    return target.read_bytes()


def ingested_exists(project_id: UUID, filename: str) -> bool:
    return ingested_path(project_id, filename).is_file()
