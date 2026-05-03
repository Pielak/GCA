"""DT-060 — Métricas operacionais agregadas.

Fonte primária:
- ai_usage_log (provider, operation, tokens, cost)
- audit_log_global (eventos de governança)
- projects (status, contagem)
- users (papel, atividade)

Saída em 2 formatos:
- `as_dashboard_dict()` — agregação por janela temporal pra render UI
- `as_prometheus_text()` — formato texto Prometheus pra scrape externo

Sem dependência de prometheus_client — texto montado manualmente.
Mantém o footprint do GCA pequeno; observabilidade externa fica como
candidato pra clientes que querem Grafana real.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    AIUsageLog,
    GlobalAuditLog,
    Project,
    ScaffoldRun,
    User,
)
from app.models.base import OCGDeltaLog  # DT-083 — métrica de deltas aplicados

logger = structlog.get_logger(__name__)


class MetricsService:
    """Service que agrega ai_usage_log + audit_log_global + projects + users
    em métricas operacionais."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ai_usage_aggregations(
        self, since: datetime, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Agrupa AIUsageLog por provider/operation desde `since`.
        Quando project_id passado, filtra por AIUsageLog.project_id."""
        stmt = (
            select(
                AIUsageLog.provider,
                AIUsageLog.operation,
                func.count(AIUsageLog.id).label("calls"),
                func.coalesce(func.sum(AIUsageLog.tokens_input), 0).label("tokens_in"),
                func.coalesce(func.sum(AIUsageLog.tokens_output), 0).label("tokens_out"),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("cost_usd"),
            )
            .where(AIUsageLog.created_at >= since)
            .group_by(AIUsageLog.provider, AIUsageLog.operation)
        )
        if project_id is not None:
            stmt = stmt.where(AIUsageLog.project_id == project_id)
        rows = (await self.db.execute(stmt)).all()
        return {
            "since": since.isoformat(),
            "rows": [
                {
                    "provider": r.provider,
                    "operation": r.operation,
                    "calls": int(r.calls),
                    "tokens_in": int(r.tokens_in),
                    "tokens_out": int(r.tokens_out),
                    "cost_usd": float(round(r.cost_usd, 6)),
                }
                for r in rows
            ],
        }

    async def _audit_aggregations(
        self, since: datetime, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Conta eventos de audit por event_type desde `since`.

        Quando project_id passado, filtra por GlobalAuditLog.resource_id.
        Limitação: GlobalAuditLog não tem coluna project_id direta — esse
        filtro pega apenas eventos cujo recurso direto É o projeto
        (ex: project.created). Eventos de recursos-filhos do projeto
        (questionnaire.submitted, ocg.updated, etc) não aparecem aqui
        no escopo por-projeto; aparecem no global.
        """
        stmt = (
            select(
                GlobalAuditLog.event_type,
                func.count(GlobalAuditLog.id).label("count"),
            )
            .where(GlobalAuditLog.created_at >= since)
            .group_by(GlobalAuditLog.event_type)
            .order_by(func.count(GlobalAuditLog.id).desc())
            .limit(20)
        )
        if project_id is not None:
            stmt = stmt.where(GlobalAuditLog.resource_id == project_id)
        rows = (await self.db.execute(stmt)).all()
        return {
            "since": since.isoformat(),
            "events": [{"event_type": r.event_type, "count": int(r.count)} for r in rows],
        }

    async def _project_summary(self) -> Dict[str, Any]:
        """Contagem de projetos por status (ativo, pausado, etc)."""
        stmt = (
            select(Project.status, func.count(Project.id).label("count"))
            .group_by(Project.status)
        )
        rows = (await self.db.execute(stmt)).all()
        return {"by_status": [{"status": r.status, "count": int(r.count)} for r in rows]}

    async def _user_summary(self) -> Dict[str, Any]:
        """Contagem de users ativos vs inativos vs admin."""
        total_active = (await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )).scalar_one()
        total_admin = (await self.db.execute(
            select(func.count(User.id)).where(User.is_admin == True, User.is_active == True)
        )).scalar_one()
        total_inactive = (await self.db.execute(
            select(func.count(User.id)).where(User.is_active == False)
        )).scalar_one()
        return {
            "active": int(total_active),
            "admin_active": int(total_admin),
            "inactive": int(total_inactive),
        }

    async def as_dashboard_dict(
        self, hours: int = 24, project_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Snapshot agregado para a UI — janela default 24h.

        Quando `project_id` é passado (escopo por projeto), ai_usage e
        audit são filtrados; users/projects.by_status são omitidos do
        payload (não fazem sentido no escopo de um único projeto).
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        out: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
            "scope": "project" if project_id else "global",
            "project_id": str(project_id) if project_id else None,
            "ai_usage": await self._ai_usage_aggregations(since, project_id=project_id),
            "audit": await self._audit_aggregations(since, project_id=project_id),
        }
        if project_id is None:
            out["projects"] = await self._project_summary()
            out["users"] = await self._user_summary()
        return out

    async def as_per_project_breakdown(self, hours: int = 24) -> Dict[str, Any]:
        """Breakdown de ai_usage agregado POR PROJETO (admin-only).

        Uma linha por projeto com total de calls, tokens in/out e custo.
        Inclui projetos ativos (sem registro na janela → linha com zeros
        só quando houver uso; projetos completamente sem chamadas não
        aparecem pra economizar tela).
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(
                AIUsageLog.project_id,
                func.count(AIUsageLog.id).label("calls"),
                func.coalesce(func.sum(AIUsageLog.tokens_input), 0).label("tokens_in"),
                func.coalesce(func.sum(AIUsageLog.tokens_output), 0).label("tokens_out"),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("cost_usd"),
            )
            .where(AIUsageLog.created_at >= since)
            .group_by(AIUsageLog.project_id)
        )
        rows = (await self.db.execute(stmt)).all()

        # Hydrate project name + status em 1 query batched.
        pids = [r.project_id for r in rows if r.project_id]
        project_info: Dict[str, Dict[str, Any]] = {}
        if pids:
            info_rows = (await self.db.execute(
                select(Project.id, Project.name, Project.slug, Project.status)
                .where(Project.id.in_(pids))
            )).all()
            for p in info_rows:
                project_info[str(p.id)] = {
                    "name": p.name,
                    "slug": p.slug,
                    "status": p.status,
                }

        items = []
        for r in rows:
            pid_str = str(r.project_id) if r.project_id else None
            info = project_info.get(pid_str or "") if pid_str else None
            items.append({
                "project_id": pid_str,
                "project_name": info["name"] if info else "(sem vínculo)",
                "project_slug": info["slug"] if info else None,
                "project_status": info["status"] if info else None,
                "calls": int(r.calls),
                "tokens_in": int(r.tokens_in),
                "tokens_out": int(r.tokens_out),
                "cost_usd": float(round(r.cost_usd, 6)),
            })
        # Ordena por custo desc (mais caros primeiro — útil pro admin)
        items.sort(key=lambda x: x["cost_usd"], reverse=True)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
            "since": since.isoformat(),
            "items": items,
        }

    async def as_prometheus_text(self, hours: int = 24) -> str:
        """Métricas em formato texto Prometheus (sem prometheus_client).

        Convenção:
        - Counters terminam em `_total`
        - Labels entre `{}` ordenados alfabeticamente
        - HELP + TYPE antes de cada métrica
        """
        d = await self.as_dashboard_dict(hours=hours)
        lines: List[str] = []
        lines.append(f"# Auto-gerado pelo GCA — janela {hours}h")

        # AI usage
        lines.append("# HELP gca_ai_calls_total Chamadas de LLM agregadas")
        lines.append("# TYPE gca_ai_calls_total counter")
        for r in d["ai_usage"]["rows"]:
            lines.append(
                f'gca_ai_calls_total{{operation="{r["operation"]}",provider="{r["provider"]}"}} {r["calls"]}'
            )

        lines.append("# HELP gca_ai_tokens_total Tokens consumidos por direção")
        lines.append("# TYPE gca_ai_tokens_total counter")
        for r in d["ai_usage"]["rows"]:
            lines.append(
                f'gca_ai_tokens_total{{direction="in",operation="{r["operation"]}",provider="{r["provider"]}"}} {r["tokens_in"]}'
            )
            lines.append(
                f'gca_ai_tokens_total{{direction="out",operation="{r["operation"]}",provider="{r["provider"]}"}} {r["tokens_out"]}'
            )

        lines.append("# HELP gca_ai_cost_usd_total Custo agregado em USD")
        lines.append("# TYPE gca_ai_cost_usd_total counter")
        for r in d["ai_usage"]["rows"]:
            lines.append(
                f'gca_ai_cost_usd_total{{operation="{r["operation"]}",provider="{r["provider"]}"}} {r["cost_usd"]}'
            )

        # Audit events
        lines.append("# HELP gca_audit_events_total Eventos de audit por tipo")
        lines.append("# TYPE gca_audit_events_total counter")
        for ev in d["audit"]["events"]:
            lines.append(
                f'gca_audit_events_total{{event_type="{ev["event_type"]}"}} {ev["count"]}'
            )

        # Projects
        lines.append("# HELP gca_projects_total Projetos por status")
        lines.append("# TYPE gca_projects_total gauge")
        for p in d["projects"]["by_status"]:
            status = p["status"] or "unknown"
            lines.append(f'gca_projects_total{{status="{status}"}} {p["count"]}')

        # Users
        lines.append("# HELP gca_users_total Usuários por categoria")
        lines.append("# TYPE gca_users_total gauge")
        lines.append(f'gca_users_total{{category="active"}} {d["users"]["active"]}')
        lines.append(f'gca_users_total{{category="admin_active"}} {d["users"]["admin_active"]}')
        lines.append(f'gca_users_total{{category="inactive"}} {d["users"]["inactive"]}')

        # MVP 14 Fase 14.10 — métricas de Celery (workers, broker, DLQ).
        # Best-effort: falhas do broker não quebram o endpoint; métricas
        # caem para 0/unreachable e o scrape externo alerta.
        try:
            from app.celery_app import (
                check_broker_connection,
                check_workers_alive,
                get_dlq_entries,
            )
            broker = check_broker_connection()
            workers = check_workers_alive(timeout=0.5)
            dlq = get_dlq_entries(limit=200)
        except Exception:  # noqa: BLE001
            broker = {"reachable": False}
            workers = {"workers": 0}
            dlq = []

        lines.append("# HELP gca_celery_broker_reachable 1 se o broker Redis respondeu, 0 caso contrário")
        lines.append("# TYPE gca_celery_broker_reachable gauge")
        lines.append(f"gca_celery_broker_reachable {1 if broker.get('reachable') else 0}")

        lines.append("# HELP gca_celery_workers_online Workers Celery respondendo ao inspect ping")
        lines.append("# TYPE gca_celery_workers_online gauge")
        lines.append(f"gca_celery_workers_online {workers.get('workers', 0)}")

        lines.append("# HELP gca_celery_dlq_entries Entradas atuais na DLQ in-memory (cap 200)")
        lines.append("# TYPE gca_celery_dlq_entries gauge")
        lines.append(f"gca_celery_dlq_entries {len(dlq)}")

        # DT-083 — métricas de OCG e CodeGen Gate (sem prometheus_client).
        # Counters cumulativos derivados de tabelas existentes:
        #   ocg_delta_log → gca_ocg_delta_applied_total{project,trigger_source}
        #   audit_log_global (OCG_NEGATIVE_DELTA_BLOCKED) → gca_ocg_negative_delta_blocked_total{project}
        #   scaffold_runs (status='blocked') → gca_codegen_blocked_total{block_level}
        ocg_deltas = await self._ocg_delta_aggregations()
        lines.append("# HELP gca_ocg_delta_applied_total OCG deltas aplicados por projeto e trigger")
        lines.append("# TYPE gca_ocg_delta_applied_total counter")
        for r in ocg_deltas:
            lines.append(
                f'gca_ocg_delta_applied_total{{project="{r["project_id"]}",trigger_source="{r["trigger_source"]}"}} {r["count"]}'
            )

        negative_blocks = await self._ocg_negative_delta_block_aggregations()
        lines.append("# HELP gca_ocg_negative_delta_blocked_total Eventos de deltas negativos bloqueados pelo filtro")
        lines.append("# TYPE gca_ocg_negative_delta_blocked_total counter")
        for r in negative_blocks:
            lines.append(
                f'gca_ocg_negative_delta_blocked_total{{project="{r["project_id"]}"}} {r["count"]}'
            )

        codegen_blocks = await self._codegen_block_aggregations()
        lines.append("# HELP gca_codegen_blocked_total Runs de CodeGen bloqueadas pelo gate de maturidade do OCG")
        lines.append("# TYPE gca_codegen_blocked_total counter")
        for r in codegen_blocks:
            lines.append(
                f'gca_codegen_blocked_total{{block_level="{r["block_level"]}"}} {r["count"]}'
            )

        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------------------
    # DT-083 — agregações para os 3 contadores Prometheus de OCG / CodeGen.
    # ---------------------------------------------------------------------
    async def _ocg_delta_aggregations(self) -> List[Dict[str, Any]]:
        """Conta deltas aplicados em `ocg_delta_log` agrupado por
        (project_id, trigger_source). Cumulativo desde o início (counter)."""
        stmt = (
            select(
                OCGDeltaLog.project_id,
                OCGDeltaLog.trigger_source,
                func.count(OCGDeltaLog.id).label("count"),
            )
            .group_by(OCGDeltaLog.project_id, OCGDeltaLog.trigger_source)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "project_id": str(r.project_id),
                "trigger_source": r.trigger_source or "unknown",
                "count": int(r.count),
            }
            for r in rows
        ]

    async def _ocg_negative_delta_block_aggregations(self) -> List[Dict[str, Any]]:
        """Conta eventos `OCG_NEGATIVE_DELTA_BLOCKED` em audit_log_global por
        resource_id (que carrega o project_id). Cumulativo desde o início."""
        from app.services.audit_service import AuditEvents

        stmt = (
            select(
                GlobalAuditLog.resource_id,
                func.count(GlobalAuditLog.id).label("count"),
            )
            .where(GlobalAuditLog.event_type == AuditEvents.OCG_NEGATIVE_DELTA_BLOCKED)
            .where(GlobalAuditLog.resource_id.isnot(None))
            .group_by(GlobalAuditLog.resource_id)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {"project_id": str(r.resource_id), "count": int(r.count)}
            for r in rows
        ]

    async def _codegen_block_aggregations(self) -> List[Dict[str, Any]]:
        """Conta runs bloqueadas pelo gate em scaffold_runs.

        Origem: DT-082 (worker Celery do CodeGen). A CHECK constraint do schema
        não permite `status='blocked'`, então o worker usa `status='failed'`
        com prefixo canônico `[ocg_gate:<level>]` em `error`. Filtramos por
        esse prefixo e parseamos o block_level. Cumulativo desde o início.
        """
        stmt = (
            select(ScaffoldRun.error)
            .where(ScaffoldRun.status == "failed")
            .where(ScaffoldRun.error.like("[ocg_gate:%"))
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        # Parse block_level do error canônico
        counts: Dict[str, int] = {}
        for err in rows:
            # Garantia: filtro WHERE LIKE já garante o prefixo, mas defendemos
            # contra payload inesperado para não emitir métrica falsa.
            if err and err.startswith("[ocg_gate:") and "]" in err:
                level = err[len("[ocg_gate:") : err.index("]")]
            else:
                level = "other"
            counts[level] = counts.get(level, 0) + 1
        return [
            {"block_level": level, "count": cnt}
            for level, cnt in sorted(counts.items())
        ]
