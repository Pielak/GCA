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

logger = structlog.get_logger(__name__)

# Evento de auditoria dedicado ao updater
OCG_UPDATED = "OCG_UPDATED"


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
        actor_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Atualiza o OCG do projeto com base na análise do Arguidor.

        Args:
            project_id: UUID do projeto
            arguider_analysis: Dict com a análise completa do Arguidor
            actor_id: UUID do usuário que disparou a ação (opcional)
            document_id: UUID do documento ingerido que originou o update (opcional)

        Returns:
            Dict com: ocg_id, version_from, version_to, change_type, context_health, changes
        """
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

        # 3. Parse da resposta
        updated_ocg, changes, change_type, context_health = self._parse_llm_response(llm_result)

        # 4. Atualizar o registro OCG
        version_to = version_from + 1
        await self._update_ocg_record(
            ocg=ocg,
            updated_ocg=updated_ocg,
            change_type=change_type,
            context_health=context_health,
            version_to=version_to,
        )

        # 5. Registrar delta
        await self._log_delta(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            changes=changes,
        )

        # 6. Registrar billing
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

        # 7. Evento de auditoria
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
        """Carrega o OCG ativo do projeto."""
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

        if provider == "deepseek":
            return await self._call_deepseek(api_key, model, system_prompt, user_prompt)
        elif provider == "anthropic":
            return await self._call_anthropic(api_key, model, system_prompt, user_prompt)
        elif provider in ("openai", "grok"):
            return await self._call_openai_compatible(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                base_url=(
                    "https://api.x.ai" if provider == "grok" else "https://api.openai.com/v1"
                ),
                provider=provider,
            )
        else:
            # Fallback genérico: tenta como OpenAI-compatible
            return await self._call_openai_compatible(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                base_url="https://api.openai.com/v1",
                provider=provider,
            )

    async def _call_deepseek(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """Chama a API do DeepSeek (compatível com OpenAI)."""
        import openai

        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        response = client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return {
            "raw_text": response.choices[0].message.content,
            "tokens_input": response.usage.prompt_tokens if response.usage else 0,
            "tokens_output": response.usage.completion_tokens if response.usage else 0,
            "provider": "deepseek",
            "model": model or "deepseek-chat",
        }

    async def _call_anthropic(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """Chama a API da Anthropic (Claude)."""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model or settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            temperature=settings.ANTHROPIC_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text if response.content else ""
        return {
            "raw_text": raw_text,
            "tokens_input": response.usage.input_tokens if response.usage else 0,
            "tokens_output": response.usage.output_tokens if response.usage else 0,
            "provider": "anthropic",
            "model": model or settings.ANTHROPIC_MODEL,
        }

    async def _call_openai_compatible(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        base_url: str,
        provider: str,
    ) -> Dict[str, Any]:
        """Chama qualquer API compatível com OpenAI (Grok, OpenAI, etc.)."""
        import openai

        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return {
            "raw_text": response.choices[0].message.content,
            "tokens_input": response.usage.prompt_tokens if response.usage else 0,
            "tokens_output": response.usage.completion_tokens if response.usage else 0,
            "provider": provider,
            "model": model,
        }

    def _build_system_prompt(self) -> str:
        return (
            "Você é o motor de atualização do OCG (Objeto de Contexto Global) do sistema GCA. "
            "Seu papel é analisar o OCG atual de um projeto e a análise mais recente do Arguidor "
            "(que valida e questiona os requisitos), e então produzir uma versão atualizada do OCG.\n\n"
            "REGRAS OBRIGATÓRIAS:\n"
            "1. Nunca remova informação consolidada sem justificativa explícita.\n"
            "2. Se o Arguidor identificou GAPs ou inconsistências, reflita isso nos scores dos pilares afetados.\n"
            "3. O campo change_type deve ser: EXPAND (nova informação positiva), CONTRACT (informação removida "
            "ou score reduzido), ou UPDATE (ajuste neutro sem expansão/contração significativa).\n"
            "4. O campo context_health deve ter: depth (0-1), confidence (0-1), quality (0-1).\n"
            "5. Retorne APENAS o JSON, sem nenhum texto adicional antes ou depois.\n\n"
            "FORMATO DE SAÍDA (JSON obrigatório):\n"
            "{\n"
            '  "updated_ocg": { ... objeto OCG completo atualizado ... },\n'
            '  "changes": [\n'
            '    { "field": "nome_do_campo", "old_value": "...", "new_value": "...", "reasoning": "..." }\n'
            "  ],\n"
            '  "change_type": "EXPAND" | "CONTRACT" | "UPDATE",\n'
            '  "context_health": { "depth": 0.0-1.0, "confidence": 0.0-1.0, "quality": 0.0-1.0 }\n'
            "}"
        )

    def _build_user_prompt(
        self,
        current_ocg: Dict[str, Any],
        arguider_analysis: Dict[str, Any],
    ) -> str:
        ocg_str = json.dumps(current_ocg, ensure_ascii=False, indent=2)
        arguider_str = json.dumps(arguider_analysis, ensure_ascii=False, indent=2)
        return (
            "## OCG ATUAL DO PROJETO\n\n"
            f"{ocg_str}\n\n"
            "## ANÁLISE DO ARGUIDOR\n\n"
            f"{arguider_str}\n\n"
            "Com base na análise do Arguidor, atualize o OCG conforme as instruções do sistema. "
            "Retorne apenas o JSON no formato especificado."
        )

    def _parse_llm_response(
        self, llm_result: Dict[str, Any]
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], str, Dict[str, Any]]:
        """
        Faz parse da resposta do LLM.

        Retorna: (updated_ocg, changes, change_type, context_health)
        Em caso de erro de parse, retorna valores seguros para não corromper o OCG.
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

        updated_ocg = parsed.get("updated_ocg", {})
        changes: List[Dict[str, Any]] = parsed.get("changes", [])
        change_type: str = parsed.get("change_type", "UPDATE")
        context_health: Dict[str, Any] = parsed.get("context_health", {
            "depth": 0.5,
            "confidence": 0.5,
            "quality": 0.5,
        })

        # Validação básica do change_type
        if change_type not in ("EXPAND", "CONTRACT", "UPDATE"):
            change_type = "UPDATE"

        return updated_ocg, changes, change_type, context_health

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
    ) -> None:
        """
        Registra o delta de mudança no ocg_delta_log.
        document_id é opcional neste contexto (update disparado por Arguidor, não por ingestão direta).
        """
        if not document_id:
            # OCGDeltaLog requer document_id por FK — registramos apenas se disponível.
            # Quando não há documento associado, logamos via structured logging.
            logger.info(
                "ocg_updater.delta_skipped_no_document",
                project_id=str(project_id),
                version_from=ocg_version_from,
                version_to=ocg_version_to,
                changes_count=len(changes),
            )
            return

        # Construir o campo fields_changed {field: {old, new, reasoning}}
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
            for c in changes[:5]  # máximo 5 no resumo
        ]
        change_summary = "; ".join(summary_parts) if summary_parts else "Nenhuma mudança registrada."

        delta_entry = OCGDeltaLog(
            project_id=project_id,
            document_id=document_id,
            ocg_version_from=ocg_version_from,
            ocg_version_to=ocg_version_to,
            fields_changed=json.dumps(fields_changed, ensure_ascii=False),
            change_summary=change_summary,
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
