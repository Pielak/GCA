"""MVP 9 Fase 9.1.1 — Foundation generator do Roadmap.

Contrato §7 MVP 9: a Fase 1 do Roadmap (Fundação) nasce **do OCG**, sem
depender de Arguidor ou de ingestão de documentos. Ao aprovar o
questionário inicial e gerar OCG v1, este service lê
`STACK_RECOMMENDATION`, `ARCHITECTURE_OVERVIEW` e `PROJECT_PROFILE` e
materializa um TODO de pré-deploy em `module_candidates` com
`source='ocg_foundation'`, `priority='high'`, `status='sugerido'`.

Itens canônicos gerados (determinísticos, não-LLM):
  - Quando backend habilitado → 3 itens (API Skeleton + DB schema + health)
  - Quando frontend habilitado → 1 item (SPA bootstrap)
  - Quando cache habilitado → 1 item (cache layer)
  - Quando messaging habilitado → 1 item (queue layer)
  - Quando ai habilitado → 1 item (AI integration contract)
  - Quando execution_model inclui 'Containerizado' → 2 itens (container + CI/CD)
  - Quando compliance_level ≥ medium ou há PII → 1 item (secrets + audit)
  - Sempre (condicional ao profile) → 1 item de observabilidade básica
  - Sempre → 1 item de deploy initial target

Idempotência: antes de criar, lê os items existentes com
`source='ocg_foundation'` para o projeto e deduplica por `name`.
Itens já presentes não são recriados; não há UPDATE automático.

Nada deste service usa LLM — saída é 100% determinística baseada nos
flags do OCG. Isso economiza tokens e permite regeneração sem custo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.module_categories import DEFAULT_MODULE_STATUS, normalize_module_type
from app.models.base import ModuleCandidate, OCG
from app.services.ocg_reader import load_latest_ocg

logger = structlog.get_logger(__name__)


SOURCE_VALUE = "ocg_foundation"


@dataclass(frozen=True)
class FoundationItem:
    """Definição de um item de Fundação a ser materializado."""
    name: str
    description: str
    module_type: str  # deve ser canônico (normalize no final)
    priority: str = "high"  # Fase 1 por padrão
    pillar_impact: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "module_type": normalize_module_type(self.module_type),
            "priority": self.priority,
            "pillar_impact": list(self.pillar_impact),
        }


class RoadmapFoundationService:
    """Materializa a Fase 1 — Fundação a partir do OCG do projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def sync_foundation(self, project_id: UUID) -> dict[str, Any]:
        """Sincroniza itens de Fundação com o OCG atual. Idempotente.

        Retorna `{"created": int, "skipped": int, "items": [...]}`.
        """
        ocg_data = await self._load_latest_ocg(project_id)
        if not ocg_data:
            logger.info("foundation.no_ocg_yet", project_id=str(project_id))
            return {"created": 0, "skipped": 0, "items": [], "reason": "no_ocg"}

        intended = self.derive_items_from_ocg(ocg_data)

        existing = await self._list_existing_foundation(project_id)
        existing_names = {m.name for m in existing}

        created = 0
        skipped = 0
        created_items: list[dict[str, Any]] = []

        for item in intended:
            if item.name in existing_names:
                skipped += 1
                continue
            mc = ModuleCandidate(
                id=uuid4(),
                project_id=project_id,
                arguider_analysis_id=None,  # foundation não tem análise
                source=SOURCE_VALUE,
                name=item.name,
                description=item.description,
                module_type=item.module_type,
                priority=item.priority,
                status=DEFAULT_MODULE_STATUS,  # 'sugerido'
                dependencies=json.dumps([]),
                source_document_ids=json.dumps([]),
                pillar_impact=json.dumps(
                    {f"p{i}": f"P{i}" in item.pillar_impact for i in range(1, 8)}
                ),
                ready_for_codegen=False,
            )
            self.db.add(mc)
            created += 1
            created_items.append(item.to_dict())

        if created:
            await self.db.commit()

        logger.info(
            "foundation.sync_done",
            project_id=str(project_id),
            created=created,
            skipped=skipped,
            total_intended=len(intended),
        )
        return {
            "created": created,
            "skipped": skipped,
            "items": created_items,
        }

    # ------------------------------------------------------------------
    # Derivação determinística (testável sem DB)
    # ------------------------------------------------------------------

    @staticmethod
    def derive_items_from_ocg(ocg_data: dict[str, Any]) -> list[FoundationItem]:
        """Lê o OCG e retorna a lista canônica de itens de Fundação.

        100% determinístico. Mesmo OCG → mesma lista na mesma ordem.
        """
        items: list[FoundationItem] = []

        stack = ocg_data.get("STACK_RECOMMENDATION") or {}
        arch = ocg_data.get("ARCHITECTURE_OVERVIEW") or {}
        profile = ocg_data.get("PROJECT_PROFILE") or {}

        # --- Backend ---
        backend = stack.get("backend") or {}
        if backend.get("enabled"):
            fw = backend.get("framework") or []
            fw_label = fw[0] if fw else "do backend"
            items.append(FoundationItem(
                name="Esqueleto do Backend (API Skeleton)",
                description=(
                    f"Configurar projeto inicial em {fw_label} com estrutura "
                    f"de pastas, roteamento base, autenticação middleware, "
                    f"validação de configuração via .env e endpoint /health."
                ),
                module_type="backend_service",
                pillar_impact=("P5",),
            ))

        database = stack.get("database") or {}
        if database.get("engine"):
            eng = database.get("engine")
            items.append(FoundationItem(
                name="Schema Inicial do Banco de Dados",
                description=(
                    f"Definir schema inicial em {eng}: tabelas de usuários, "
                    f"permissões, audit_log, configurações. Migrations "
                    f"versionadas + script de seed idempotente."
                ),
                module_type="infrastructure",
                pillar_impact=("P6",),
            ))

        # --- Frontend ---
        frontend = stack.get("frontend") or {}
        if frontend.get("enabled"):
            stack_labels = ", ".join(frontend.get("stack") or ["React"])
            items.append(FoundationItem(
                name="Bootstrap do Frontend (SPA + autenticação)",
                description=(
                    f"Projeto inicial com {stack_labels}, roteamento, "
                    f"cliente HTTP autenticado, store de sessão, "
                    f"layout base e telas de login/logout."
                ),
                module_type="feature",
                pillar_impact=("P5",),
            ))

        # --- Cache ---
        cache = stack.get("cache") or {}
        if cache.get("enabled"):
            items.append(FoundationItem(
                name="Camada de Cache",
                description=(
                    "Instalar/configurar cache, integrar com backend via "
                    "client abstration (get/set/delete com TTL configurável), "
                    "métricas de hit/miss expostas."
                ),
                module_type="middleware",
                pillar_impact=("P4",),
            ))

        # --- Messaging / Queue ---
        messaging = stack.get("messaging") or {}
        if messaging.get("enabled"):
            items.append(FoundationItem(
                name="Fila de Mensagens (worker + broker)",
                description=(
                    "Provisionar broker de mensagens, publisher no backend, "
                    "worker consumidor com retry/dead-letter, observabilidade "
                    "de lag de consumo."
                ),
                module_type="middleware",
                pillar_impact=("P4", "P5"),
            ))

        # --- AI integration contract ---
        ai = stack.get("ai") or {}
        if ai.get("enabled"):
            providers = ai.get("provider") or ["IA"]
            prov_label = providers[0] if isinstance(providers, list) and providers else "IA"
            items.append(FoundationItem(
                name="Contrato de Integração com IA",
                description=(
                    f"Camada de abstração sobre provedor de IA ({prov_label}), "
                    f"gestão de chaves criptografadas no vault, registro de "
                    f"tokens/custos, fallback entre providers configurados."
                ),
                module_type="backend_service",
                pillar_impact=("P5", "P7"),
            ))

        # --- Infraestrutura: containers + CI/CD ---
        execution = arch.get("execution_model") or []
        if isinstance(execution, list):
            exec_set = {str(e).lower() for e in execution}
        else:
            exec_set = {str(execution).lower()}
        if any("contain" in e for e in exec_set):
            items.append(FoundationItem(
                name="Container da Aplicação (Dockerfile + compose)",
                description=(
                    "Dockerfile multi-stage com usuário não-root, "
                    "docker-compose para dev, healthchecks, volumes "
                    "persistentes para dados e storage."
                ),
                module_type="infrastructure",
                pillar_impact=("P5", "P7"),
            ))
            items.append(FoundationItem(
                name="Pipeline de CI/CD Inicial",
                description=(
                    "Pipeline que roda lint + testes + build em cada PR, "
                    "tag de release no merge pra main, gera imagem "
                    "versionada e publica no registry."
                ),
                module_type="deploy_pipeline",
                pillar_impact=("P5",),
            ))

        # --- Secrets + audit quando há AI ou compliance ---
        # COMPLIANCE_CHECKLIST pode ser dict (formato atual) ou list
        # (OCGs antigos). Normalizamos pra conjunto de flags em string.
        compliance_raw = ocg_data.get("COMPLIANCE_CHECKLIST") or {}
        compliance_flags: list[str] = []
        if isinstance(compliance_raw, dict):
            compliance_flags = [str(k).lower() for k, v in compliance_raw.items() if v]
        elif isinstance(compliance_raw, list):
            compliance_flags = [str(x).lower() for x in compliance_raw]
        has_pii = bool(
            profile.get("handles_pii")
            or profile.get("pii_expected")
            or any("lgpd" in f for f in compliance_flags)
        )
        if ai.get("enabled") or has_pii:
            items.append(FoundationItem(
                name="Gestão de Secrets e Audit Log",
                description=(
                    "Vault criptografado para chaves de API e credenciais; "
                    "audit_log de eventos críticos (login, alteração de "
                    "permissão, acesso a dados sensíveis) com hash para "
                    "detecção de tampering."
                ),
                module_type="infrastructure",
                pillar_impact=("P2", "P7"),
            ))

        # --- Observabilidade sempre (mínimo viável) ---
        items.append(FoundationItem(
            name="Observabilidade Básica (logs estruturados + métricas)",
            description=(
                "Logs JSON estruturados com correlation_id por request, "
                "métricas de contagem/latência dos endpoints, endpoint "
                "/metrics no padrão Prometheus, health check contínuo."
            ),
            module_type="observability",
            pillar_impact=("P4",),
        ))

        # --- Deploy inicial target ---
        deliverables = profile.get("deliverables") or arch.get("deliverables") or []
        if isinstance(deliverables, list) and deliverables:
            del_label = ", ".join(str(d) for d in deliverables[:3])
        else:
            del_label = "entregáveis declarados"
        items.append(FoundationItem(
            name="Ambiente de Deploy Inicial (dev)",
            description=(
                f"Provisionar ambiente de desenvolvimento integrado que "
                f"rode os {del_label}; documentar setup local e fluxo de "
                f"deploy para staging."
            ),
            module_type="deploy_pipeline",
            pillar_impact=("P5",),
        ))

        return items

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _load_latest_ocg(self, project_id: UUID) -> dict[str, Any] | None:
        """Thin wrapper sobre ocg_reader.load_latest_ocg que parseia o JSON do campo ocg_data."""
        ocg = await load_latest_ocg(self.db, project_id)
        if not ocg or not ocg.ocg_data:
            return None
        try:
            return json.loads(ocg.ocg_data)
        except (ValueError, TypeError):
            logger.warning("foundation.ocg_parse_failed", project_id=str(project_id))
            return None

    async def _list_existing_foundation(self, project_id: UUID) -> Sequence[ModuleCandidate]:
        rows = await self.db.execute(
            select(ModuleCandidate)
            .where(ModuleCandidate.project_id == project_id)
            .where(ModuleCandidate.source == SOURCE_VALUE)
        )
        return rows.scalars().all()
