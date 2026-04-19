"""DT-072 — Pipeline não avançava arguider_stage pra completed/100.

Bug dogfood 2026-04-19: após ingestão bem-sucedida de PDF (Arguidor +
OCG updater + propagação completaram todos), o doc ficava travado em
`arguider_stage='updating_ocg'`, `arguider_progress_percent=70`. Logs
mostravam `ingestion.ocg_reactive_complete` ser emitido normalmente,
mas as chamadas subsequentes de `_update_stage` silenciavam.

Causa: OCGUpdaterService compartilhava a session `db` do
_analyze_async e fazia múltiplos commits internos. Depois disso, a
session entrava em estado onde `db.commit()` em `_update_stage`
sumia silenciosamente (sem exception, sem persistência).

Fix: `_update_stage_fresh` que SEMPRE abre `AsyncSessionLocal()`
nova. Chamadas finais do pipeline (regenerating_backlog,
completed/100, completed/95 em erro) usam a versão fresh.
`_update_stage` original ganhou log quando doc não é encontrado e
try/except em torno do commit pra flagrar falhas futuras.
"""
import pytest
from pathlib import Path


def test_pipeline_usa_update_stage_fresh_nos_pontos_finais():
    """Contrato de código: chamadas de _update_stage nos pontos finais
    do pipeline (após OCG updater) DEVEM usar a versão fresh pra
    isolar a session corrompida pelo updater."""
    source = Path("/app/app/services/ingestion_service.py").read_text()

    # Deve ter helper novo
    assert "_update_stage_fresh" in source
    assert "async def _update_stage_fresh" in source

    # Nos 3 pontos finais do pipeline (regenerating_backlog,
    # completed/100, completed/95), é _update_stage_fresh que roda
    # — não _update_stage direto na session db compartilhada.
    assert '_update_stage_fresh(document_id, "regenerating_backlog")' in source
    assert '_update_stage_fresh(document_id, "completed", percent=100)' in source
    assert '_update_stage_fresh(document_id, "completed", percent=95)' in source


def test_update_stage_loga_quando_doc_nao_existe():
    """Defesa em profundidade: se algum dia algo deletar o doc entre
    o dispatch e o _update_stage, ao menos log fica — em vez de
    silêncio."""
    source = Path("/app/app/services/ingestion_service.py").read_text()
    assert "ingestion.update_stage_doc_not_found" in source


def test_update_stage_captura_commit_failure():
    """Se o commit falhar (ex: session em estado inválido), loga e
    propaga — não silencia."""
    source = Path("/app/app/services/ingestion_service.py").read_text()
    assert "ingestion.update_stage_commit_failed" in source


def test_update_stage_fresh_abre_session_nova():
    """Contrato: o helper deve instanciar AsyncSessionLocal() própria
    em vez de receber a session do caller."""
    source = Path("/app/app/services/ingestion_service.py").read_text()
    # A função abre AsyncSessionLocal via import local e usa async with
    assert "from app.db.database import AsyncSessionLocal as _ASL" in source
    assert "async with _ASL() as _fresh:" in source
