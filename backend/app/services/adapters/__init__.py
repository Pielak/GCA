"""MVP 20 — Adapters concretos de integrações externas.

Cada adapter implementa a porta canônica correspondente em
`app.services.ports.*`. Adapters são puros (sem DB): recebem
`ProviderConfig`, fazem HTTP, retornam dataclasses canônicas.

Orquestração (decidir QUANDO criar issue, QUANDO enviar notificação)
fica nos services (`issue_tracker_service`, `notifier_service`). Adapters
só EXECUTAM.
"""
