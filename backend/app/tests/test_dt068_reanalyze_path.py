"""DT-068 — /reanalyze constrói path correto e não marca docs como lost.

Bug dogfood 2026-04-19: o endpoint construía
`os.path.join(STORAGE_PATH, doc.filename)` — resolvia pra
`/app/storage/<filename>`. Mas os docs ficam em
`/app/storage/ingested/<project_id>/<filename>` (ver
`utils/ingested_storage.py`). O endpoint sempre falhava E, pior,
marcava `content_status='lost'` como se fosse problema do storage,
corrompendo o estado em cima do bug dele mesmo.

Testes de contrato (inspeção do código fonte + teste unitário do
helper de storage) — sem HTTP, porque o TestClient sincronizado em
cima do db_session async sofre com conflitos de event loop em
handlers que disparam tasks async.
"""
from pathlib import Path
from uuid import uuid4

import pytest


def test_reanalyze_usa_read_ingested_e_nao_storage_path_direto():
    """O handler de reanalyze deve usar `read_ingested(project_id, filename)`
    — caminho correto — e não o antigo `os.path.join(cfg.STORAGE_PATH,
    doc.filename)` que ignorava o project_id."""
    source = Path("/app/app/routers/ingestion_router.py").read_text()

    # Deve importar read_ingested
    assert "from app.utils.ingested_storage import read_ingested" in source, (
        "ingestion_router deve importar read_ingested pro path correto"
    )

    # Não pode mais construir path via os.path.join com STORAGE_PATH
    # dentro da função de reanalyze (busca rígida pelo padrão antigo)
    assert "os.path.join(cfg.STORAGE_PATH, doc.filename)" not in source, (
        "padrão antigo de path ainda presente — deve ser trocado por "
        "read_ingested(project_id, doc.filename)"
    )


def test_read_ingested_retorna_bytes_quando_path_correto():
    """Integração com o helper: grava no path canônico, lê de volta."""
    from app.utils.ingested_storage import write_ingested, read_ingested, ingested_path

    pid = uuid4()
    filename = f"{uuid4()}.docx"
    payload = b"payload real do documento"

    path = write_ingested(pid, filename, payload)
    try:
        expected = ingested_path(pid, filename)
        assert path == expected
        assert "ingested" in str(path)
        assert str(pid) in str(path)

        loaded = read_ingested(pid, filename)
        assert loaded == payload
    finally:
        try:
            path.unlink()
        except Exception:
            pass


def test_read_ingested_retorna_none_quando_arquivo_ausente():
    """Se o arquivo realmente não existe, read_ingested retorna None
    — contrato que o handler usa pra decidir marcar como lost."""
    from app.utils.ingested_storage import read_ingested

    pid = uuid4()
    filename = f"inexistente-{uuid4()}.docx"
    assert read_ingested(pid, filename) is None
