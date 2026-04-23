"""MVP 23 Fase 23.4 — Testes canônicos do `rnf_validation_service`.

Cobre:
  1. Contrato vazio → report vazio (zero-impact backcompat).
  2. Rate limit declarado + arquivo com `slowapi` → sem violação.
  3. Rate limit declarado + arquivo sem middleware → violação blocker
     com `file_path="*"` (scope any_file_in_module).
  4. CWE-89 declarado + concatenação de SQL → sem padrão positivo
     encontrado → violação blocker.
  5. CWE-89 declarado + `select(...)` SQLAlchemy → sem violação.
  6. Sensitive data logged (`logger.info(...password...)`) → violação
     por padrão negativo.
  7. CWE-798 declarado + password hardcoded → depende do padrão positivo
     existir no arquivo (VaultService/os.environ).
  8. Arquivos não-código (.md, .yml) são ignorados.
"""
from __future__ import annotations

from app.services.rnf_contracts import (
    RnfContracts, SecurityContract, from_ocg_dict,
)
from app.services.rnf_validation_service import validate_files


def _mkfile(path: str, content: str) -> dict:
    return {"path": path, "content": content}


def test_empty_contract_empty_report():
    rnf = RnfContracts()
    report = validate_files(rnf, [_mkfile("a.py", "print('hi')")])
    assert report.violations == ()
    assert not report.has_blocker
    assert report.checks_evaluated == 0


def test_rate_limit_with_slowapi_ok():
    rnf = RnfContracts(security=SecurityContract(rate_limit_rpm_public=60))
    files = [_mkfile("api.py", "from slowapi import Limiter\nlimiter = Limiter()")]
    report = validate_files(rnf, files)
    assert report.violations == ()
    assert report.checks_evaluated >= 1


def test_rate_limit_missing_middleware_blocker():
    rnf = RnfContracts(security=SecurityContract(rate_limit_rpm_public=60))
    files = [_mkfile("api.py", "def hello(): return 'ok'")]
    report = validate_files(rnf, files)
    assert report.has_blocker
    blocker = [v for v in report.violations if v.check_id == "rate_limit_middleware"]
    assert blocker, "esperada violação rate_limit_middleware"
    assert blocker[0].file_path == "*"  # scope any_file_in_module


def test_cwe_89_sql_concat_violates():
    rnf = from_ocg_dict({
        "security": {"required_cwe_protections": ["CWE-89"]},
    })
    # Código com concatenação de SQL (anti-pattern clássico)
    files = [_mkfile("repo.py", 'query = "SELECT * FROM users WHERE id=" + user_id\n')]
    report = validate_files(rnf, files)
    # Não tem nenhum padrão positivo canônico → violação
    cwe_vios = [v for v in report.violations if "cwe_89" in v.check_id]
    assert cwe_vios, "esperada violação CWE-89"
    assert cwe_vios[0].severity == "blocker"


def test_cwe_89_sqlalchemy_select_ok():
    rnf = from_ocg_dict({
        "security": {"required_cwe_protections": ["CWE-89"]},
    })
    files = [_mkfile(
        "repo.py",
        "from sqlalchemy import select\nq = select(User).where(User.id == user_id)\n",
    )]
    report = validate_files(rnf, files)
    cwe_vios = [v for v in report.violations if "cwe_89" in v.check_id]
    assert not cwe_vios


def test_sensitive_data_logged_blocker():
    rnf = from_ocg_dict({
        "security": {"sensitive_data_categories": ["password"]},
    })
    files = [_mkfile(
        "auth.py",
        'logger.info("user_password_is=" + password)\n',
    )]
    report = validate_files(rnf, files)
    sens = [v for v in report.violations if v.check_id == "sensitive_data_not_logged"]
    assert sens, "esperada violação sensitive_data_not_logged"
    assert sens[0].severity == "blocker"


def test_cwe_798_vault_ok():
    rnf = from_ocg_dict({
        "security": {"required_cwe_protections": ["CWE-798"]},
    })
    files = [_mkfile(
        "cfg.py",
        "from app.services.vault import VaultService\nkey = VaultService.get('api')\n",
    )]
    report = validate_files(rnf, files)
    cwe_vios = [v for v in report.violations if "cwe_798" in v.check_id]
    assert not cwe_vios


def test_cwe_798_no_vault_violates():
    rnf = from_ocg_dict({
        "security": {"required_cwe_protections": ["CWE-798"]},
    })
    files = [_mkfile("cfg.py", "API_KEY = 'literal-key-here'\n")]
    report = validate_files(rnf, files)
    cwe_vios = [v for v in report.violations if "cwe_798" in v.check_id]
    assert cwe_vios
    assert cwe_vios[0].severity == "blocker"


def test_non_code_files_ignored():
    rnf = RnfContracts(security=SecurityContract(rate_limit_rpm_public=60))
    files = [
        _mkfile("README.md", "sem middleware aqui"),
        _mkfile("config.yml", "app: no limiter"),
    ]
    report = validate_files(rnf, files)
    # Nenhum arquivo de código → files_scanned==0 → any_file_in_module falha
    # porque "nenhum arquivo do módulo contém padrão", mas fica claro que o
    # validator não inspecionou docs.
    assert report.files_scanned == 0


def test_multiple_files_one_satisfies():
    """Scope `any_file_in_module` fica satisfeito se UM arquivo cobre."""
    rnf = RnfContracts(security=SecurityContract(rate_limit_rpm_public=60))
    files = [
        _mkfile("module.py", "from slowapi import Limiter"),
        _mkfile("handler.py", "def handle(): pass"),
    ]
    report = validate_files(rnf, files)
    rl = [v for v in report.violations if v.check_id == "rate_limit_middleware"]
    assert not rl, "rate_limit satisfeito por module.py"


def test_report_to_dict_shape():
    rnf = RnfContracts(security=SecurityContract(rate_limit_rpm_public=60))
    files = [_mkfile("x.py", "# sem rate limit")]
    report = validate_files(rnf, files)
    d = report.to_dict()
    assert set(d.keys()) == {
        "violations", "checks_evaluated", "files_scanned",
        "has_blocker", "blocker_files",
    }
    assert d["has_blocker"] is True
    assert isinstance(d["violations"], list)
