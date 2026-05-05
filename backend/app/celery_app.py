"""
DEPRECATED (Fase 4, 2026-05-05) — Celery removido completamente.

Substituído por Dramatiq (app/dramatiq_app.py).
Mantém stub para segurança rollback (improvável após 2026-05-10).

Se encontrar import de celery_app em código ativo:
  1. Mudar para: from app.dramatiq_app import broker
  2. Remover .delay() → usar .send()
  3. Grep: git grep "from app.celery_app"

Remoção física: 2026-05-12 (após 7 dias estabilidade).
"""

class _DeprecatedCeleryShim:
    """Placeholder para código legado — levanta erro se acessado."""
    def __getattr__(self, name):
        raise RuntimeError(
            f"Celery foi removido na Fase 4 (2026-05-05). "
            f"Use Dramatiq em seu lugar: from app.dramatiq_app import broker. "
            f"Atributo solicitado: {name}"
        )

celery_app = _DeprecatedCeleryShim()
