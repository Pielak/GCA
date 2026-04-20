"""MVP 13 Fase 13.1 — pacote de tasks Celery do GCA.

Fases 13.2-13.4 adicionam sub-módulos específicos:
- `app.tasks.arguider` — análise de documentos ingeridos.
- `app.tasks.ocg_updater` — propagação do OCG pós-Arguider.
- `app.tasks.codegen` — geração de código quando OCG muda.

Por ora (Fase 13.1), o pacote existe apenas para que o `include=` do
`celery_app` não falhe. Nenhuma task de pipeline real ainda.
"""
