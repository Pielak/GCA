"""DT-062 — testes estáticos do upgrade.sh.

Validação de salvaguardas críticas do script de upgrade idempotente.
Não executa o script (rodaria git pull / docker build em prod).
"""
import os
import subprocess
from pathlib import Path

import pytest

if os.path.isdir("/host_scripts"):
    SCRIPTS_DIR = Path("/host_scripts")
else:
    SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"

UPGRADE = SCRIPTS_DIR / "upgrade.sh"


def test_upgrade_exists_and_executable():
    assert UPGRADE.exists()
    assert UPGRADE.stat().st_mode & 0o111


def test_upgrade_bash_syntax_ok():
    res = subprocess.run(["bash", "-n", str(UPGRADE)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_upgrade_uses_strict_mode():
    """`set -euo pipefail` é obrigatório — falha silenciosa em upgrade
    deixa cliente em estado inconsistente."""
    content = UPGRADE.read_text()
    assert "set -euo pipefail" in content


def test_upgrade_does_backup_before_anything():
    """Backup pre-upgrade é a primeira ação útil — antes de pull/build.
    Olha a primeira invocação do `backup.sh` real (não comentário)."""
    content = UPGRADE.read_text()
    backup_idx = content.find('"$REPO_DIR/scripts/backup.sh"')
    pull_idx = content.find("git pull --ff-only")
    build_idx = content.find("DOCKER_BUILDKIT=0 docker compose build")
    assert 0 < backup_idx < pull_idx, "backup deve preceder git pull"
    assert backup_idx < build_idx, "backup deve preceder build"


def test_upgrade_idempotent_when_already_up_to_date():
    """Se LOCAL_SHA == REMOTE_SHA, sai sem rebuild — re-run barato."""
    content = UPGRADE.read_text()
    assert "LOCAL_SHA" in content and "REMOTE_SHA" in content
    assert 'LOCAL_SHA" == "$REMOTE_SHA' in content
    # E sai com exit 0 nesse caso (não falha re-run)
    assert "Saindo limpo" in content


def test_upgrade_uses_fast_forward_only():
    """`git pull --ff-only` — recusa merge automático, evita estado misto."""
    content = UPGRADE.read_text()
    assert "git pull --ff-only" in content


def test_upgrade_runs_alembic_after_build():
    """Migrations rodam DEPOIS do build (código novo) e ANTES do recreate."""
    content = UPGRADE.read_text()
    build_idx = content.find("docker compose build")
    alembic_idx = content.find("alembic upgrade head")
    recreate_idx = content.find("force-recreate backend frontend")
    assert build_idx < alembic_idx < recreate_idx


def test_upgrade_healthcheck_loop():
    """Healthcheck pós-upgrade tem loop — backend pode demorar a subir."""
    content = UPGRADE.read_text()
    assert "for i in {1..30}" in content
    assert "metrics/health" in content


def test_upgrade_aborts_with_restore_hint():
    """Se algo falha, mensagem cita comando exato pra restaurar."""
    content = UPGRADE.read_text()
    assert "restore.sh" in content
    assert "i-know-what-im-doing" in content
