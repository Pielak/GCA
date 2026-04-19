"""DT-061 — testes estáticos dos scripts de backup/restore.

Não chamamos os scripts (afetam DB de produção). Validamos:
- Sintaxe bash (`bash -n`)
- Presença de salvaguardas críticas (set -e, validação de hash, prompts)
- Estrutura do manifest gerado por backup.sh
"""
import json
import subprocess
from pathlib import Path

import pytest

# DT-061: scripts mountados em /host_scripts (read-only) via compose.
# Fora do container (dev local): cair no path relativo ao repo.
import os
if os.path.isdir("/host_scripts"):
    SCRIPTS_DIR = Path("/host_scripts")
else:
    SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"

BACKUP_SCRIPT = SCRIPTS_DIR / "backup.sh"
RESTORE_SCRIPT = SCRIPTS_DIR / "restore.sh"


def _bash_syntax_ok(script_path: Path) -> tuple[bool, str]:
    res = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True, text=True,
    )
    return res.returncode == 0, res.stderr


def test_backup_script_exists_and_executable():
    assert BACKUP_SCRIPT.exists()
    assert BACKUP_SCRIPT.stat().st_mode & 0o111, "backup.sh sem +x"


def test_restore_script_exists_and_executable():
    assert RESTORE_SCRIPT.exists()
    assert RESTORE_SCRIPT.stat().st_mode & 0o111, "restore.sh sem +x"


def test_backup_script_bash_syntax_ok():
    ok, err = _bash_syntax_ok(BACKUP_SCRIPT)
    assert ok, f"backup.sh tem erro de sintaxe: {err}"


def test_restore_script_bash_syntax_ok():
    ok, err = _bash_syntax_ok(RESTORE_SCRIPT)
    assert ok, f"restore.sh tem erro de sintaxe: {err}"


def test_backup_uses_strict_mode():
    """`set -euo pipefail` é obrigatório — falhas silenciosas em backup
    são a pior classe de bug operacional."""
    content = BACKUP_SCRIPT.read_text()
    assert "set -euo pipefail" in content


def test_restore_uses_strict_mode():
    content = RESTORE_SCRIPT.read_text()
    assert "set -euo pipefail" in content


def test_restore_requires_explicit_flag():
    """`--i-know-what-im-doing` é obrigatória — confirma intencionalidade."""
    content = RESTORE_SCRIPT.read_text()
    assert "--i-know-what-im-doing" in content
    assert "SHOULD_PROCEED" in content


def test_restore_validates_hash_before_destruction():
    """Hash do dump precisa ser validado ANTES de DROP DATABASE.
    Sem isso, um arquivo corrompido apaga prod sem restaurar."""
    content = RESTORE_SCRIPT.read_text()
    drop_idx = content.find("DROP DATABASE")
    hash_check_idx = content.find("hash de db_gca.sql.gz")
    assert hash_check_idx > 0, "validação de hash ausente"
    assert hash_check_idx < drop_idx, "validação de hash deve ser ANTES do DROP"


def test_restore_requires_double_confirmation():
    """Prompt textual + flag — duas barreiras independentes."""
    content = RESTORE_SCRIPT.read_text()
    assert "Digite o path do backup novamente para confirmar" in content


def test_backup_includes_postgres_user_gca_not_postgres():
    """User correto do compose é `gca`, não `postgres` (bug do script
    antigo). Regressão pra evitar voltar ao errado."""
    content = BACKUP_SCRIPT.read_text()
    # pg_dump roda como user gca
    assert "pg_dump -U gca" in content
    # NÃO usa user postgres
    assert "pg_dump -U postgres" not in content


def test_backup_uses_correct_container_name():
    """Container é `gca-postgres`, não `postgres` (bug do script antigo)."""
    content = BACKUP_SCRIPT.read_text()
    assert "docker exec gca-postgres" in content


def test_backup_includes_uploads_volume():
    """Volume `gca_gca-uploads-storage` (DT-030) deve ser backupeado."""
    content = BACKUP_SCRIPT.read_text()
    assert "gca_gca-uploads-storage" in content


def test_backup_writes_manifest_json():
    """manifest.json com hashes é a base do restore confiável."""
    content = BACKUP_SCRIPT.read_text()
    assert "manifest.json" in content
    assert "sha256" in content
