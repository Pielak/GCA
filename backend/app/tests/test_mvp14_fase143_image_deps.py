"""MVP 14 Fase 14.3 — Rebuild --no-cache definitivo.

Contrato §7 MVP 14 Fase 14.3:
- `docker compose build --no-cache backend` persiste celery + slowapi
  + pypdf + reportlab + esprima na imagem.
- CI atualiza verificação para incluir celery + slowapi além das
  3 libs já cobertas em 11.5.

Testes aqui validam apenas que o CI yml tem a verificação atualizada
(o rebuild real é operacional — validado manualmente no container
antes do commit).
"""
import pathlib

import pytest


def _find_workflow():
    """Localiza backend-tests.yml — pode estar em múltiplos paths
    dependendo do ambiente (host vs container)."""
    candidates = [pathlib.Path("/home/luiz/GCA/.github/workflows/backend-tests.yml")]
    try:
        base = pathlib.Path(__file__).resolve()
        for depth in range(1, 8):
            try:
                candidates.append(base.parents[depth] / ".github" / "workflows" / "backend-tests.yml")
            except IndexError:
                break
    except Exception:
        pass
    return next((p for p in candidates if p.exists()), None)


def test_ci_test_job_verifica_celery_e_slowapi():
    """Job `test` do CI inclui celery + slowapi no import check."""
    wf = _find_workflow()
    if wf is None:
        pytest.skip("backend-tests.yml não disponível neste ambiente")
    content = wf.read_text(encoding="utf-8")
    # Deve ter import único contendo todas as 5 libs
    assert "import pypdf, reportlab, esprima, celery, slowapi" in content


def test_ci_docker_image_job_verifica_celery_e_slowapi():
    """Job `docker-image` do CI estende verificação pós-rebuild."""
    wf = _find_workflow()
    if wf is None:
        pytest.skip("backend-tests.yml não disponível neste ambiente")
    content = wf.read_text(encoding="utf-8")
    # Ambos jobs (test + docker-image) compartilham o mesmo import;
    # procuramos pelas 2 ocorrências distintas (uma no test, outra no docker-image).
    count = content.count("import pypdf, reportlab, esprima, celery, slowapi")
    assert count >= 2, f"esperava ≥2 ocorrências, veio {count}"


def test_runtime_imports_celery_slowapi():
    """Smoke: as libs estão importáveis no ambiente de teste atual."""
    import celery
    import slowapi  # noqa: F401
    import pypdf  # noqa: F401
    import reportlab  # noqa: F401
    import esprima  # noqa: F401
    assert celery.__version__
