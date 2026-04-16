"""
OCGUpdaterService — Atualiza o OCG de forma reativa após análise do Arguidor.

Fluxo:
  1. Carrega OCG atual do projeto
  2. Chama LLM (DeepSeek/Anthropic) com OCG atual + análise do Arguidor
  3. Faz parse da resposta: updated_ocg, changes[], change_type, context_health
  4. Atualiza o registro OCG (incrementa versão, salva novos dados)
  5. Registra delta no ocg_delta_log
  6. Registra billing
  7. Emite evento de auditoria OCG_UPDATED
  8. Em caso de falha do LLM: marca status como ocg_pending (nunca corrompe o OCG)
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.base import OCG, OCGDeltaLog
from app.services.ai_billing_service import AIBillingService
from app.services.ai_key_resolver import AIKeyResolver
from app.services.audit_service import AuditService
from app.services.ocg_compactor import compact_ocg_for_prompt
from app.services.ocg_delta_applier import apply_deltas

logger = structlog.get_logger(__name__)

# Evento de auditoria dedicado ao updater
OCG_UPDATED = "OCG_UPDATED"

# Lock por project_id para serializar updates concorrentes do OCG.
# Sem isto, N tasks paralelas leem version=V, todas escrevem version=V+1,
# causando lost updates (a última commit vence). Com lock asyncio, cada
# task aguarda a anterior antes de ler o OCG, então cada uma vê a versão
# mais recente e incrementa corretamente (V → V+1 → V+2 → ...).
# Limitação: lock é per-process. Em deployment multi-worker (gunicorn N
# workers), conflitos entre workers ainda são possíveis — para isso
# precisaria de lock distribuído (Redis SETNX) ou version_id_col do SA.
_PROJECT_LOCKS: Dict[UUID, asyncio.Lock] = {}


def _get_project_lock(project_id: UUID) -> asyncio.Lock:
    """Lock dedicado por project_id, criado on-demand."""
    lock = _PROJECT_LOCKS.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_LOCKS[project_id] = lock
    return lock


class OCGUpdaterService:
    """
    Serviço reativo que atualiza o OCG após análise do Arguidor.
    Nunca corrompe o OCG existente — em caso de falha do LLM apenas sinaliza.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.billing_service = AIBillingService(db)
        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------ #
    #  Ponto de entrada principal                                          #
    # ------------------------------------------------------------------ #

    async def update_ocg_from_arguider(
        self,
        project_id: UUID,
        arguider_analysis: Dict[str, Any],
        document_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
    ) -> Optional[Dict[str, Any]]:
        """
        Atualiza o OCG do projeto com base na análise do Arguidor.

        Serializado por project_id via asyncio.Lock para evitar lost updates
        quando múltiplos documentos do mesmo projeto disparam updates em paralelo
        (cenário típico: ingestão de N markdowns de um repo externo).

        Args:
            project_id: UUID do projeto
            arguider_analysis: Dict com a análise completa do Arguidor
            actor_id: UUID do usuário que disparou a ação (opcional)
            document_id: UUID do documento ingerido que originou o update (opcional)

        Returns:
            Dict com: ocg_id, version_from, version_to, change_type, context_health, changes
        """
        async with _get_project_lock(project_id):
            return await self._update_ocg_from_arguider_locked(
                project_id=project_id,
                arguider_analysis=arguider_analysis,
                document_id=document_id,
                actor_id=actor_id,
                trigger_source=trigger_source,
            )

    async def _update_ocg_from_arguider_locked(
        self,
        project_id: UUID,
        arguider_analysis: Dict[str, Any],
        document_id: Optional[UUID],
        actor_id: Optional[UUID],
        trigger_source: str,
    ) -> Optional[Dict[str, Any]]:
        """Implementação real — sempre executada sob _get_project_lock(project_id)."""
        logger.info(
            "ocg_updater.start",
            project_id=str(project_id),
            actor_id=str(actor_id) if actor_id else None,
        )

        # 1. Carregar OCG atual
        ocg = await self._load_current_ocg(project_id)
        if not ocg:
            logger.warning("ocg_updater.ocg_not_found", project_id=str(project_id))
            raise ValueError(f"OCG não encontrado para o projeto {project_id}.")

        version_from = ocg.version
        current_ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}

        # 2. Chamar o LLM
        try:
            llm_result = await self._call_llm(current_ocg_data, arguider_analysis)
        except Exception as exc:
            logger.error(
                "ocg_updater.llm_failed",
                project_id=str(project_id),
                error=str(exc),
            )
            await self._mark_ocg_pending(ocg)
            await self.db.commit()
            return {
                "ocg_id": str(ocg.id),
                "version_from": version_from,
                "version_to": version_from,
                "status": "ocg_pending",
                "error": str(exc),
            }

        # 3. Parse da resposta (formato delta)
        deltas, change_type, context_health = self._parse_llm_response(llm_result)

        # 4. Aplicar deltas localmente (deterministic, sem LLM, com optimistic concurrency)
        updated_ocg, applied, rejected = apply_deltas(current_ocg_data, deltas)

        if rejected:
            logger.warning(
                "ocg_updater.deltas_rejected",
                project_id=str(project_id),
                rejected_count=len(rejected),
                applied_count=len(applied),
                samples=[
                    {"path": r.get("path"), "op": r.get("op"), "reason": r.get("_reason")}
                    for r in rejected[:5]
                ],
            )

        # Se LLM não propôs nenhum delta válido → não criar nova versão
        if not applied:
            logger.info(
                "ocg_updater.no_changes",
                project_id=str(project_id),
                rejected_count=len(rejected),
            )
            return {
                "ocg_id": str(ocg.id),
                "version_from": version_from,
                "version_to": version_from,
                "change_type": change_type,
                "context_health": context_health,
                "changes": [],
                "rejected_count": len(rejected),
                "status": "no_changes",
            }

        # changes no formato legado (para _log_delta + audit/notif)
        changes = [
            {
                "field": d.get("path", ""),
                "old_value": d.get("old_value"),
                "new_value": d.get("new_value") if d.get("op") == "replace" else d.get("value"),
                "reasoning": d.get("reasoning", ""),
            }
            for d in applied
        ]

        # 5. Atualizar o registro OCG
        version_to = version_from + 1
        await self._update_ocg_record(
            ocg=ocg,
            updated_ocg=updated_ocg,
            change_type=change_type,
            context_health=context_health,
            version_to=version_to,
        )

        # 6. Registrar delta no audit log
        await self._log_delta(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            changes=changes,
            changed_by=actor_id,
            trigger_source=trigger_source,
            ocg_snapshot=updated_ocg,
        )

        # 7. Registrar billing
        tokens_in = llm_result.get("tokens_input", 0)
        tokens_out = llm_result.get("tokens_output", 0)
        provider = llm_result.get("provider", settings.DEFAULT_AI_PROVIDER)
        model = llm_result.get("model", settings.DEFAULT_AI_MODEL)
        await self.billing_service.log_usage(
            project_id=project_id,
            provider=provider,
            model=model,
            operation="ocg_update",
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            actor_id=actor_id,
            metadata={"version_from": version_from, "version_to": version_to},
        )

        # 8. Evento de auditoria
        await self.audit_service.log_event(
            event_type=OCG_UPDATED,
            resource_type="ocg",
            actor_id=actor_id,
            resource_id=ocg.id,
            details={
                "project_id": str(project_id),
                "version_from": version_from,
                "version_to": version_to,
                "change_type": change_type,
                "changes_count": len(changes),
            },
        )

        await self.db.commit()

        # Notificar GPs do projeto sobre atualização do OCG
        try:
            from app.services.notification_inapp_service import InAppNotificationService
            from app.models.base import ProjectMember
            gps_result = await self.db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.role == "gp",
                    ProjectMember.is_active == True,
                )
            )
            notif = InAppNotificationService(self.db)
            for gp in gps_result.scalars().all():
                await notif.notify(
                    user_id=gp.user_id,
                    event_type="ocg_updated",
                    title=f"OCG atualizado (v{version_from} → v{version_to})",
                    message=f"{len(changes)} mudança(s) aplicada(s). Trigger: {change_type}.",
                    project_id=project_id,
                    resource_type="ocg",
                    resource_id=ocg.id,
                    link=f"/projects/{project_id}/ocg",
                    severity="info",
                )
        except Exception as notif_err:
            logger.warning("ocg_updater.notify_failed", error=str(notif_err))

        logger.info(
            "ocg_updater.success",
            project_id=str(project_id),
            version_from=version_from,
            version_to=version_to,
            change_type=change_type,
        )

        return {
            "ocg_id": str(ocg.id),
            "version_from": version_from,
            "version_to": version_to,
            "change_type": change_type,
            "context_health": context_health,
            "changes": changes,
            "status": "updated",
        }

    # ------------------------------------------------------------------ #
    #  Helpers internos                                                    #
    # ------------------------------------------------------------------ #

    async def _load_current_ocg(self, project_id: UUID) -> Optional[OCG]:
        """Carrega o OCG ativo do projeto.

        Concorrência é serializada em camada superior (asyncio.Lock por
        project_id em update_ocg_from_arguider). Não usar with_for_update
        aqui porque a transação fica viva durante a chamada LLM (~30-60s)
        e bloqueia outras conexões do pool.
        """
        stmt = (
            select(OCG)
            .where(OCG.project_id == project_id)
            .order_by(OCG.version.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _call_llm(
        self,
        current_ocg_data: Dict[str, Any],
        arguider_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Chama o LLM com o OCG atual e a análise do Arguidor.
        Suporta DeepSeek (padrão) e Anthropic como fallback.

        Retorna dict com: raw_text, tokens_input, tokens_output, provider, model
        """
        # Carregar chaves do banco (system_settings) antes de resolver
        from app.routers.admin_gca_router import _load_ai_providers_from_db
        await _load_ai_providers_from_db(self.db)

        provider = settings.DEFAULT_AI_PROVIDER
        api_key = await AIKeyResolver.get_gca_key(provider)

        if not api_key:
            raise ValueError(
                f"Chave de IA não configurada para o provider '{provider}'. "
                "O Admin deve configurar em Configurações > Provedores de IA."
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(current_ocg_data, arguider_analysis)

        model = settings.DEFAULT_AI_MODEL

        logger.info(
            "ocg_updater.llm_call",
            provider=provider,
            model=model,
            prompt_len=len(user_prompt),
        )

        # Chamada unificada via httpx (mesmo padrão do agent_service._call_llm)
        import httpx

        provider_urls = {
            "deepseek": "https://api.deepseek.com/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions",
            "grok": "https://api.x.ai/v1/chat/completions",
        }
        url = provider_urls.get(provider, "https://api.deepseek.com/chat/completions")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }, json={
                "model": model,
                "max_tokens": 8192,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            })

        if resp.status_code not in (200, 201):
            raise ValueError(f"LLM API error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        return {
            "raw_text": data["choices"][0]["message"]["content"],
            "tokens_input": data.get("usage", {}).get("prompt_tokens", 0),
            "tokens_output": data.get("usage", {}).get("completion_tokens", 0),
            "provider": provider,
            "model": model,
        }

    def _build_system_prompt(self) -> str:
        return (
            "Você é o motor de atualização do OCG (Objeto de Contexto Global) do GCA.\n"
            "Recebe o OCG atual e a análise do Arguidor; retorna **apenas um delta** "
            "descrevendo o que mudar — NÃO reescreve o OCG inteiro.\n\n"
            "## REGRAS\n"
            "1. Use APENAS as operações 'replace' e 'append'.\n"
            "2. Cada delta tem o formato:\n"
            "   - replace: {op:'replace', path, old_value, new_value, reasoning}\n"
            "     * 'old_value' é OBRIGATÓRIO — se divergir do atual, o delta é rejeitado (optimistic concurrency).\n"
            "     * 'path' em dot-notation: 'PILLAR_SCORES.P3_Scope_Management', 'STACK_RECOMMENDATION.backend.framework'.\n"
            "     * Para item de lista por índice: 'RISK_ANALYSIS.high_risks.0.mitigation'.\n"
            "   - append: {op:'append', path, value, reasoning}\n"
            "     * path deve apontar para uma lista existente (DELIVERABLES, COMPLIANCE_CHECKLIST, RISK_ANALYSIS.high_risks, etc.).\n"
            "3. Top-level keys permitidos: PROJECT_PROFILE, PILLAR_SCORES, COMPOSITE_SCORE, STACK_RECOMMENDATION, "
            "CRITICAL_FINDINGS, TESTING_REQUIREMENTS, COMPLIANCE_CHECKLIST, DELIVERABLES, ARCHITECTURE_OVERVIEW, "
            "RISK_ANALYSIS, APPROVAL_STATUS. Qualquer outra é rejeitada.\n"
            "4. Se a análise não justifica nenhuma mudança real, devolva 'deltas': [] (vazio).\n"
            "5. change_type:\n"
            "   - EXPAND: informação nova positiva sendo adicionada (novo entregável, novo módulo).\n"
            "   - CONTRACT: score reduzido ou informação descartada por GAP do Arguidor.\n"
            "   - UPDATE: ajuste neutro (refinamento de descrição, etc.). Use UPDATE se deltas=[].\n"
            "6. context_health: {depth, confidence, quality} valores entre 0.0 e 1.0.\n"
            "7. Nunca remova informação consolidada sem justificativa explícita no 'reasoning'.\n"
            "8. Retorne APENAS o JSON. Sem markdown, sem comentários, sem preamble.\n\n"
            "## FORMATO DE SAÍDA (JSON obrigatório)\n"
            "{\n"
            '  "deltas": [\n'
            '    {"op":"replace", "path":"PILLAR_SCORES.P3_Scope_Management", "old_value":75, "new_value":65, "reasoning":"GAP G003: requisitos não-implementáveis"},\n'
            '    {"op":"append", "path":"DELIVERABLES", "value":"SBOM inicial do projeto", "reasoning":"resposta ao GAP G002"}\n'
            '  ],\n'
            '  "change_type": "EXPAND" | "CONTRACT" | "UPDATE",\n'
            '  "context_health": {"depth": 0.0, "confidence": 0.0, "quality": 0.0}\n'
            "}"
        )

    def _build_user_prompt(
        self,
        current_ocg: Dict[str, Any],
        arguider_analysis: Dict[str, Any],
    ) -> str:
        # Compactar OCG para prompts longos: trima textos verbosos (rationale,
        # description, mitigation, etc.) sem mexer em scores/listas/items.
        # Compactor é no-op se o OCG for pequeno o suficiente.
        compact_ocg = compact_ocg_for_prompt(current_ocg)
        ocg_str = json.dumps(compact_ocg, ensure_ascii=False, indent=2)
        arguider_str = json.dumps(arguider_analysis, ensure_ascii=False, indent=2)
        return (
            "## OCG ATUAL DO PROJETO (textos longos compactados; valores/scores intactos)\n\n"
            f"{ocg_str}\n\n"
            "## ANÁLISE DO ARGUIDOR\n\n"
            f"{arguider_str}\n\n"
            "Com base na análise do Arguidor, gere o **delta** (lista de operações replace/append) "
            "que reflete as mudanças necessárias no OCG. Retorne apenas o JSON no formato especificado pelo system prompt."
        )

    def _parse_llm_response(
        self, llm_result: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """
        Faz parse da resposta do LLM no formato delta.

        Retorna: (deltas, change_type, context_health)
        Em caso de erro de parse, levanta ValueError — caller marca OCG como
        ocg_pending e preserva versão atual.
        """
        raw_text = llm_result.get("raw_text", "")

        # Tenta extrair JSON da resposta (pode ter markdown code fences)
        json_text = self._extract_json(raw_text)

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "ocg_updater.parse_failed",
                error=str(exc),
                raw_snippet=raw_text[:200],
            )
            raise ValueError(f"Resposta do LLM não é JSON válido: {exc}") from exc

        deltas: List[Dict[str, Any]] = parsed.get("deltas", [])
        if not isinstance(deltas, list):
            logger.warning("ocg_updater.deltas_not_list", got_type=type(deltas).__name__)
            deltas = []

        change_type: str = parsed.get("change_type", "UPDATE")
        context_health: Dict[str, Any] = parsed.get("context_health", {
            "depth": 0.5,
            "confidence": 0.5,
            "quality": 0.5,
        })

        # Validação básica do change_type
        if change_type not in ("EXPAND", "CONTRACT", "UPDATE"):
            change_type = "UPDATE"

        return deltas, change_type, context_health

    def _extract_json(self, text: str) -> str:
        """Extrai o JSON de uma resposta que pode conter markdown code fences."""
        # Tenta remover ```json ... ``` ou ``` ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return match.group(1).strip()
        # Tenta encontrar o primeiro { ... } de nível superior
        start = text.find("{")
        if start != -1:
            return text[start:]
        return text.strip()

    async def _update_ocg_record(
        self,
        ocg: OCG,
        updated_ocg: Dict[str, Any],
        change_type: str,
        context_health: Dict[str, Any],
        version_to: int,
    ) -> None:
        """Atualiza o registro OCG existente (UNIQUE questionnaire_id)."""
        # Atualizar scores dos pilares se presentes no updated_ocg
        pillar_map = {
            "p1_business_score": ["p1_score", "p1_business_score"],
            "p2_rules_score": ["p2_score", "p2_rules_score"],
            "p3_features_score": ["p3_score", "p3_features_score"],
            "p4_nfr_score": ["p4_score", "p4_nfr_score"],
            "p5_architecture_score": ["p5_score", "p5_architecture_score"],
            "p6_data_score": ["p6_score", "p6_data_score"],
            "p7_security_score": ["p7_score", "p7_security_score"],
        }

        for ocg_col, source_keys in pillar_map.items():
            for key in source_keys:
                val = updated_ocg.get(key)
                if val is not None:
                    setattr(ocg, ocg_col, float(val))
                    break

        # Overall score
        overall = updated_ocg.get("overall_score")
        if overall is not None:
            ocg.overall_score = float(overall)

        # Dados completos
        ocg.ocg_data = json.dumps(updated_ocg, ensure_ascii=False)
        ocg.change_type = change_type
        ocg.context_health = json.dumps(context_health, ensure_ascii=False)
        ocg.version = version_to
        ocg.updated_at = datetime.now(timezone.utc)

        self.db.add(ocg)
        await self.db.flush()

    async def _log_delta(
        self,
        project_id: UUID,
        document_id: Optional[UUID],
        ocg_version_from: int,
        ocg_version_to: int,
        changes: List[Dict[str, Any]],
        changed_by: Optional[UUID] = None,
        trigger_source: str = "document_ingestion",
        ocg_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra delta sempre — document_id opcional (updates não-ingestão também contam)."""
        fields_changed: Dict[str, Any] = {}
        for change in changes:
            field = change.get("field", "unknown")
            fields_changed[field] = {
                "old": change.get("old_value"),
                "new": change.get("new_value"),
                "reasoning": change.get("reasoning", ""),
            }

        summary_parts = [
            f"{c.get('field', '?')}: {c.get('reasoning', '')}"
            for c in changes[:5]
        ]
        change_summary = "; ".join(summary_parts) if summary_parts else f"Mudança via {trigger_source}"

        delta_entry = OCGDeltaLog(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=ocg_version_from,
            ocg_version_to=ocg_version_to,
            fields_changed=json.dumps(fields_changed, ensure_ascii=False),
            change_summary=change_summary,
            changed_by=changed_by,
            trigger_source=trigger_source,
            ocg_snapshot=json.dumps(ocg_snapshot, ensure_ascii=False) if ocg_snapshot else None,
        )
        self.db.add(delta_entry)
        await self.db.flush()

    async def _mark_ocg_pending(self, ocg: OCG) -> None:
        """
        Marca o OCG como ocg_pending quando o LLM falha.
        Preserva todos os dados atuais — nunca corrompe o OCG.
        """
        ocg.status = "ocg_pending"
        ocg.updated_at = datetime.now(timezone.utc)
        self.db.add(ocg)
        await self.db.flush()
        logger.warning(
            "ocg_updater.marked_pending",
            ocg_id=str(ocg.id),
            version=ocg.version,
        )
