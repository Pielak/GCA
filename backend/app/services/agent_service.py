"""
Agent Service
Serviço de orquestração e execução dos 8 agentes OCG
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from anthropic import AsyncAnthropic
from app.core.config import settings
from app.models.base import OCG, OCGAnalysisLog
from app.schemas.ocg import (
    AnalyzerRequest,
    AnalyzerResponse,
    PillarAgentRequest,
    PillarAgentResponse,
    ConsolidatorRequest,
    OCGResponse,
)
from app.services.agent_prompts import (
    ANALYZER_SYSTEM_PROMPT,
    ANALYZER_USER_PROMPT_TEMPLATE,
    PILLAR_SYSTEM_PROMPTS,
    CONSOLIDATOR_SYSTEM_PROMPT,
    CONSOLIDATOR_USER_PROMPT_TEMPLATE,
)

logger = structlog.get_logger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder que converte UUIDs e datetimes para strings"""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class AgentService:
    """Service para gerenciar os 8 agentes OCG.

    CAMADA GCA ADMIN — usa chave global configurada pelo admin.
    Não deve usar chave de projeto. Avalia questionários externos apenas.
    Suporta múltiplos providers: Anthropic, DeepSeek, OpenAI (compatíveis).

    Criticidade (contrato §6.2): **ALTA**. Consolidação do OCG exige modelo
    premium de raciocínio. Sem fallback silencioso a outro provider/chave:
    se o admin configurou provider X mas não forneceu `X_API_KEY`, o service
    falha explicitamente na primeira chamada (ver `_ensure_key`).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Detectar provider configurado pelo admin (camada GCA).
        self.provider = settings.DEFAULT_AI_PROVIDER or "anthropic"
        self.api_key = getattr(settings, f"{self.provider.upper()}_API_KEY", None)
        # Modelo: prefere `{PROVIDER}_MODEL` explícito do admin; se ausente,
        # usa `DEFAULT_AI_MODEL` global (consistente com ocg_updater_service
        # e ai_service). Sem isso, admin precisava setar uma env var por
        # provider mesmo tendo DEFAULT_AI_MODEL apontando para o escolhido.
        self.model = (
            getattr(settings, f"{self.provider.upper()}_MODEL", None)
            or settings.DEFAULT_AI_MODEL
        )

        # Cliente SDK nativo apenas para Anthropic. Outros providers usam httpx
        # em `_call_llm` (rota OpenAI-compatible).
        if self.provider == "anthropic" and self.api_key:
            self.client = AsyncAnthropic(api_key=self.api_key)
        else:
            self.client = None

    async def _project_id_for_questionnaire(self, questionnaire_id) -> Optional[UUID]:
        """Resolve project_id a partir de um questionnaire_id.

        O billing exige project_id NOT NULL (migration 009). O analyzer e
        pillar agents são disparados com questionnaire_id conhecido e é daí
        que derivamos o projeto. Sem isso, cada log falha com
        IntegrityError NotNullViolationError e arrasta a transação — o
        OCG nem chega a ser salvo.
        """
        if questionnaire_id is None:
            return None
        from sqlalchemy import text
        try:
            result = await self.db.execute(
                text("SELECT project_id FROM questionnaires WHERE id = :qid"),
                {"qid": str(questionnaire_id)},
            )
            row = result.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _ensure_key(self) -> None:
        """Garante que o provider configurado tem chave. Falha explícita se
        não tiver — evita fallback silencioso (contrato §6.4).
        """
        if not self.api_key:
            raise RuntimeError(
                f"Provider de IA '{self.provider}' configurado (DEFAULT_AI_PROVIDER) "
                f"mas {self.provider.upper()}_API_KEY está ausente. "
                f"Admin deve configurar a chave correspondente em /admin/gca/ai-providers. "
                f"Geração de OCG é tarefa de ALTA criticidade (contrato §6.2) e não "
                f"aceita fallback silencioso para outro provider."
            )
        if not self.model:
            raise RuntimeError(
                f"Provider de IA '{self.provider}' sem modelo configurado "
                f"({self.provider.upper()}_MODEL). Admin deve definir o modelo."
            )

    async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096, project_id: UUID = None, operation: str = "ocg_generation") -> tuple[str, int]:
        """Chamada unificada ao LLM — suporta Anthropic e OpenAI-compatible (DeepSeek, Grok, etc.)
        Returns: (response_text, tokens_used)
        Integra billing ao final da chamada.

        Criticidade: **ALTA** (contrato §6.2). Falha explícita se provider
        configurado não tiver chave — sem fallback silencioso.
        """
        self._ensure_key()
        import httpx

        tokens_in = 0
        tokens_out = 0

        if self.provider == "anthropic" and self.client:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=getattr(settings, 'ANTHROPIC_TEMPERATURE', 0.3),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            tokens = tokens_in + tokens_out
        else:
            # OpenAI-compatible (DeepSeek, Grok, OpenAI)
            provider_urls = {
                "deepseek": "https://api.deepseek.com/chat/completions",
                "openai": "https://api.openai.com/v1/chat/completions",
                "grok": "https://api.x.ai/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions",
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            }
            url = provider_urls.get(self.provider)
            if not url:
                raise ValueError(f"Provider '{self.provider}' não suportado para OCG pipeline")

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_tokens,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )

            if resp.status_code not in (200, 201):
                raise ValueError(f"LLM API error ({resp.status_code}): {resp.text[:300]}")

            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            tokens_in = data.get("usage", {}).get("prompt_tokens", 0)
            tokens_out = data.get("usage", {}).get("completion_tokens", 0)
            tokens = tokens_in + tokens_out

        # Registrar billing
        try:
            from app.services.ai_billing_service import AIBillingService
            billing = AIBillingService(self.db)
            await billing.log_usage(
                project_id=project_id,
                provider=self.provider,
                model=self.model,
                operation=operation,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
            )
            await self.db.flush()
        except Exception as e:
            logger.warning("billing.log_failed", error=str(e))

        return text, tokens

    # ========== AGENT 0: ANALYZER ==========

    async def analyze_questionnaire(
        self,
        req: AnalyzerRequest,
    ) -> AnalyzerResponse:
        """
        Agent 0: Questionnaire Analyzer

        Classifica respostas por pilar e extrai metadata do projeto.

        Args:
            req: AnalyzerRequest com questionnaire_id, answers, metadata

        Returns:
            AnalyzerResponse com classificação e informações extraídas
        """
        try:
            logger.info(
                "agent.analyzer_starting",
                questionnaire_id=str(req.questionnaire_id),
            )

            # Preparar prompt do usuário
            responses_json = json.dumps(
                [{"q": a.get("question_id", ""), "answer": a.get("text", "")} for a in req.answers],
                ensure_ascii=False,
                indent=2,
            )

            user_prompt = ANALYZER_USER_PROMPT_TEMPLATE.format(
                responses_json=responses_json,
                project_name=req.project_metadata.get("project_name", "Unknown") if req.project_metadata else "Unknown",
                submitted_by=req.project_metadata.get("submitted_by", "Unknown") if req.project_metadata else "Unknown",
                submitted_at=datetime.now(timezone.utc).isoformat(),
            )

            # Chamar LLM (Anthropic, DeepSeek, etc.). project_id é resolvido
            # a partir do questionnaire_id para permitir billing correto.
            start_time = datetime.now(timezone.utc)
            pid = await self._project_id_for_questionnaire(req.questionnaire_id)
            response_text, tokens_used = await self._call_llm(
                system_prompt=ANALYZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=pid,
                operation="analyzer",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            ocg_json = self._extract_json(response_text)

            # Normalizar classification: extrair apenas question IDs
            classification = {}
            for pillar, items in ocg_json.get("classification", {}).items():
                if isinstance(items, list):
                    if items and isinstance(items[0], str):
                        classification[pillar] = items
                    else:
                        classification[pillar] = [item.get("question") if isinstance(item, dict) else str(item) for item in items]
                else:
                    classification[pillar] = []

            result = AnalyzerResponse(
                questionnaire_id=req.questionnaire_id,
                classification=classification,
                extracted_info=ocg_json.get("extracted_info", {}),
                anomalies=ocg_json.get("anomalies", []),
            )

            logger.info(
                "agent.analyzer_success",
                questionnaire_id=str(req.questionnaire_id),
                pillars_found=len(result.classification),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return result

        except Exception as e:
            logger.error(
                "agent.analyzer_error",
                questionnaire_id=str(req.questionnaire_id),
                error=str(e),
            )
            raise

    # ========== AGENTS 1-7: PILLAR SPECIALISTS ==========

    async def analyze_pillar(
        self,
        pillar_id: int,
        req: PillarAgentRequest,
    ) -> PillarAgentResponse:
        """
        Agents 1-7: Pillar Specialist

        Analisa respostas específicas de um pilar.

        Args:
            pillar_id: 1-7
            req: PillarAgentRequest com questions, responses, metadata

        Returns:
            PillarAgentResponse com score e findings
        """
        if pillar_id < 1 or pillar_id > 7:
            raise ValueError("pillar_id deve estar entre 1 e 7")

        try:
            logger.info(
                "agent.pillar_starting",
                pillar_id=pillar_id,
                questionnaire_id=str(req.questionnaire_id),
            )

            # Preparar contexto
            pillar_questions_str = "\n".join(
                [f"- {q.get('question_id')}: {q.get('text', '')}" for q in req.questions]
            )

            responses_str = "\n".join(
                [f"- {k}: {v}" for k, v in req.responses.items()]
            )

            system_prompt = PILLAR_SYSTEM_PROMPTS.get(pillar_id, "")

            user_prompt = f"""Analyze these responses for Pillar P{pillar_id}:

Questions:
{pillar_questions_str}

Responses:
{responses_str}

Project Context:
- Type: {req.project_metadata.get('project_type', 'Unknown')}
- Team Size: {req.project_metadata.get('team_size', 'Unknown')}
- Timeline: {req.project_metadata.get('timeline_months', 'Unknown')} months

Return complete JSON analysis with score, classification, findings, and recommendations."""

            # Chamar LLM. project_id resolvido via questionnaire_id → billing
            # evita IntegrityError que antes derrubava a transação do OCG.
            start_time = datetime.now(timezone.utc)
            pid = await self._project_id_for_questionnaire(req.questionnaire_id)
            response_text, tokens_used = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=pid,
                operation=f"pillar_p{pillar_id}",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Extrair JSON
            ocg_json = self._extract_json(response_text)

            result = PillarAgentResponse(
                pillar_id=pillar_id,
                score=ocg_json.get("score", 50.0),
                adherence_level=ocg_json.get("adherence_level", "MEDIUM"),
                classification=ocg_json.get("classification", {}),
                findings=ocg_json.get("findings", []),
                stack_implications=ocg_json.get("stack_implications", {}),
                checklist=ocg_json.get("checklist", []),
                is_blocking=ocg_json.get("is_blocking", False) if pillar_id == 7 else False,
            )

            logger.info(
                "agent.pillar_success",
                pillar_id=pillar_id,
                questionnaire_id=str(req.questionnaire_id),
                score=result.score,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return result

        except Exception as e:
            logger.error(
                "agent.pillar_error",
                pillar_id=pillar_id,
                questionnaire_id=str(req.questionnaire_id),
                error=str(e),
            )
            raise

    async def analyze_all_pillars(
        self,
        analyzer_result: AnalyzerResponse,
        req: PillarAgentRequest,
    ) -> List[PillarAgentResponse]:
        """
        Executar Agents 1-7 em paralelo.

        Args:
            analyzer_result: Output do Analyzer com classificação
            req: Request base para os pillar agents

        Returns:
            List de 7 PillarAgentResponse
        """
        try:
            logger.info(
                "agent.all_pillars_starting",
                questionnaire_id=str(req.questionnaire_id),
            )

            async def create_empty_pillar_response(pillar_id: int) -> PillarAgentResponse:
                """Helper to create empty pillar response as async"""
                return PillarAgentResponse(
                    pillar_id=pillar_id,
                    score=50.0,
                    adherence_level="POOR",
                    classification={},
                    findings=[{"severity": "warning", "finding": "No questions assigned to this pillar"}],
                    stack_implications={},
                    checklist=[],
                    is_blocking=False,
                )

            tasks = []
            all_questions = req.questions  # Todas as questões disponíveis

            for pillar_id in range(1, 8):
                # Filtrar perguntas classificadas para este pilar
                pillar_question_ids = analyzer_result.classification.get(f"P{pillar_id}", [])

                # Match flexível: tentar IDs diretos, com prefixo Q, e numéricos
                pillar_questions = []
                for q in all_questions:
                    qid = str(q.get("question_id", ""))
                    if (qid in pillar_question_ids or
                        f"Q{qid}" in pillar_question_ids or
                        qid.lstrip("Q") in [str(x).lstrip("Q") for x in pillar_question_ids]):
                        pillar_questions.append(q)

                # Se nenhum match, enviar TODAS as questões — o LLM filtra
                if not pillar_questions:
                    logger.info("agent.pillar_sending_all_questions", pillar_id=pillar_id,
                               classified_ids=pillar_question_ids[:5])
                    pillar_questions = all_questions

                # Adaptar request para este pilar
                pillar_req = PillarAgentRequest(
                    pillar_id=pillar_id,
                    questionnaire_id=req.questionnaire_id,
                    questions=pillar_questions,
                    responses=req.responses,
                    project_metadata=req.project_metadata,
                )

                task = self.analyze_pillar(pillar_id, pillar_req)
                tasks.append(task)

            # Executar em paralelo. return_exceptions=True para que falha em
            # 1 pilar não derrube os outros 6 (antes: gather levantava na 1ª
            # exceção, perdendo TODOS os resultados parciais).
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            results = []
            failed_pillars = []
            for idx, r in enumerate(raw_results, start=1):
                if isinstance(r, PillarAgentResponse):
                    results.append(r)
                elif isinstance(r, Exception):
                    failed_pillars.append({"pillar_id": idx, "error": str(r)})
                    logger.error(
                        "agent.pillar_failed",
                        pillar_id=idx,
                        error=str(r),
                        error_type=type(r).__name__,
                    )

            if failed_pillars:
                logger.warning(
                    "agent.pillars_partial",
                    questionnaire_id=str(req.questionnaire_id),
                    succeeded=len(results),
                    failed=len(failed_pillars),
                    failed_pillars=failed_pillars,
                )
            else:
                logger.info(
                    "agent.all_pillars_success",
                    questionnaire_id=str(req.questionnaire_id),
                    pillars_analyzed=len(results),
                )

            return results

        except Exception as e:
            logger.error(
                "agent.all_pillars_error",
                questionnaire_id=str(req.questionnaire_id),
                error=str(e),
            )
            raise

    # ========== AGENT 8: CONSOLIDATOR ==========

    async def consolidate_ocg(
        self,
        req: ConsolidatorRequest,
    ) -> OCGResponse:
        """
        Agent 8: OCG Consolidator

        Consolida resultados de todos os pilares em OCG final.

        Args:
            req: ConsolidatorRequest com analyzer output e pillar results

        Returns:
            OCGResponse completo, salvo no banco
        """
        try:
            logger.info(
                "agent.consolidator_starting",
                questionnaire_id=str(req.questionnaire_id),
                num_pillars=len(req.pillar_results),
            )

            # Preparar JSON dos resultados
            analyzer_json = req.analyzer_output.dict()
            pillar_json = [p.dict() for p in req.pillar_results]

            user_prompt = CONSOLIDATOR_USER_PROMPT_TEMPLATE.format(
                project_name=req.project_metadata.get("project_name", "Unknown"),
                project_type=req.project_metadata.get("project_type", "Unknown"),
                team_size=req.project_metadata.get("team_size", "Unknown"),
                project_metadata_json=json.dumps(req.project_metadata, ensure_ascii=False, indent=2, cls=UUIDEncoder),
                analyzer_output_json=json.dumps(analyzer_json, ensure_ascii=False, indent=2, cls=UUIDEncoder),
                pillar_results_json=json.dumps(pillar_json, ensure_ascii=False, indent=2, cls=UUIDEncoder),
            )

            # Chamar LLM
            start_time = datetime.now(timezone.utc)
            response_text, tokens_used = await self._call_llm(
                system_prompt=CONSOLIDATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=req.project_id,
                operation="consolidator",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Extrair JSON
            ocg_json = self._extract_json(response_text)

            logger.info("agent.consolidator_raw_keys",
                       keys=list(ocg_json.keys())[:15] if isinstance(ocg_json, dict) else "NOT_DICT",
                       raw_len=len(response_text))

            # Se o JSON não tem as chaves esperadas, usar resposta bruta como contexto
            if not ocg_json.get("PROJECT_PROFILE") and not ocg_json.get("PILLAR_SCORES"):
                # Consolidator pode ter usado chaves diferentes ou formato livre
                # Salvar tudo o que veio como contexto
                logger.warning("agent.consolidator_unexpected_format",
                              keys=list(ocg_json.keys())[:10] if isinstance(ocg_json, dict) else "not_dict")

            # Construir PILLAR_SCORES a partir dos resultados reais dos agentes (mais confiável)
            pillar_scores_from_agents = {}
            for pr in req.pillar_results:
                pillar_scores_from_agents[f"P{pr.pillar_id}"] = {
                    "score": pr.score,
                    "adherence_level": pr.adherence_level,
                    "is_blocking": pr.is_blocking,
                    "findings_count": len(pr.findings),
                }

            # Score composto a partir dos pilares reais
            scores = [pr.score for pr in req.pillar_results]
            overall_score = round(sum(scores) / len(scores), 1) if scores else 0
            any_blocking = any(pr.is_blocking for pr in req.pillar_results)

            # Construir OCGResponse — mesclando dados do consolidator com os pilares reais
            ocg_response = OCGResponse(
                ocg_id=uuid4(),
                questionnaire_id=req.questionnaire_id,
                project_id=req.project_id,
                generated_at=datetime.now(timezone.utc),
                PROJECT_PROFILE=ocg_json.get("PROJECT_PROFILE") or ocg_json.get("project_profile") or req.project_metadata or {},
                PILLAR_SCORES=ocg_json.get("PILLAR_SCORES") or ocg_json.get("pillar_scores") or pillar_scores_from_agents,
                COMPOSITE_SCORE=self._normalize_composite_score(
                    ocg_json.get("COMPOSITE_SCORE") or ocg_json.get("composite_score"),
                    overall_score, any_blocking
                ),
                STACK_RECOMMENDATION=(
                    ocg_json.get("STACK_RECOMMENDATION")
                    or ocg_json.get("stack_recommendation")
                    or ocg_json.get("stack")
                    or self._stack_from_metadata(req.project_metadata or {})
                ),
                CRITICAL_FINDINGS=ocg_json.get("CRITICAL_FINDINGS") or ocg_json.get("critical_findings") or [f for pr in req.pillar_results for f in pr.findings if f.get("severity") == "critical"],
                TESTING_REQUIREMENTS=ocg_json.get("TESTING_REQUIREMENTS") or ocg_json.get("testing_requirements") or ocg_json.get("testing", {}),
                COMPLIANCE_CHECKLIST=ocg_json.get("COMPLIANCE_CHECKLIST") or ocg_json.get("compliance_checklist") or ocg_json.get("compliance", []),
                DELIVERABLES=ocg_json.get("DELIVERABLES") or ocg_json.get("deliverables", {}),
                ARCHITECTURE_OVERVIEW=(
                    ocg_json.get("ARCHITECTURE_OVERVIEW")
                    or ocg_json.get("architecture_overview")
                    or ocg_json.get("architecture")
                    or self._architecture_from_metadata(req.project_metadata or {})
                ),
                RISK_ANALYSIS=ocg_json.get("RISK_ANALYSIS") or ocg_json.get("risk_analysis") or ocg_json.get("risks", {}),
                APPROVAL_STATUS=ocg_json.get("APPROVAL_STATUS") or ocg_json.get("approval_status") or {"status": "NEEDS_REVIEW" if any_blocking else "APPROVED", "overall_score": overall_score},
            )

            # Salvar no banco
            await self.save_ocg(ocg_response)

            # Log de análise
            await self.log_analysis(
                ocg_id=ocg_response.ocg_id,
                agent_name="consolidator",
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            logger.info(
                "agent.consolidator_success",
                questionnaire_id=str(req.questionnaire_id),
                ocg_id=str(ocg_response.ocg_id),
                overall_score=self._safe_get(ocg_response.COMPOSITE_SCORE, "overall", 0),
                is_blocking=self._safe_get(ocg_response.COMPOSITE_SCORE, "is_blocking", False),
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return ocg_response

        except Exception as e:
            logger.error(
                "agent.consolidator_error",
                questionnaire_id=str(req.questionnaire_id),
                error=str(e),
            )
            raise

    # ========== UTILITIES ==========

    async def save_ocg(self, ocg_response: OCGResponse) -> OCG:
        """Salvar OCG no banco de dados"""
        try:
            # Extrair scores dos pilares (flexível: P1, P1_Business, etc.)
            ps = ocg_response.PILLAR_SCORES
            def _get_pillar_score(ps: dict, pillar_num: int) -> float:
                """Busca score do pilar com fallback para diferentes formatos de chave"""
                for key in [f"P{pillar_num}", f"P{pillar_num}_Business", f"P{pillar_num}_Rules",
                           f"P{pillar_num}_Features", f"P{pillar_num}_NFR", f"P{pillar_num}_Architecture",
                           f"P{pillar_num}_Data", f"P{pillar_num}_Security"]:
                    val = ps.get(key)
                    if isinstance(val, dict):
                        return val.get("score", 0)
                    elif isinstance(val, (int, float)):
                        return val
                return 0

            ocg = OCG(
                id=ocg_response.ocg_id,
                questionnaire_id=ocg_response.questionnaire_id,
                project_id=ocg_response.project_id,
                p1_business_score=_get_pillar_score(ps, 1),
                p2_rules_score=_get_pillar_score(ps, 2),
                p3_features_score=_get_pillar_score(ps, 3),
                p4_nfr_score=_get_pillar_score(ps, 4),
                p5_architecture_score=_get_pillar_score(ps, 5),
                p6_data_score=_get_pillar_score(ps, 6),
                p7_security_score=_get_pillar_score(ps, 7),
                overall_score=self._safe_get(ocg_response.COMPOSITE_SCORE, "overall") or self._safe_get(ocg_response.COMPOSITE_SCORE, "value") or (ocg_response.COMPOSITE_SCORE if isinstance(ocg_response.COMPOSITE_SCORE, (int, float)) else 0),
                status=self._safe_get(ocg_response.COMPOSITE_SCORE, "status") or ("BLOCKED" if self._safe_get(ocg_response.COMPOSITE_SCORE, "is_blocking") else "NEEDS_REVIEW"),
                is_blocking=bool(self._safe_get(ocg_response.COMPOSITE_SCORE, "is_blocking")),
                ocg_data=json.dumps(ocg_response.dict(), ensure_ascii=False, cls=UUIDEncoder),
                generated_at=ocg_response.generated_at,
            )

            self.db.add(ocg)
            await self.db.commit()

            logger.info("agent.ocg_saved", ocg_id=str(ocg.id))
            return ocg

        except Exception as e:
            logger.error("agent.ocg_save_error", error=str(e))
            raise

    @staticmethod
    def _pick(meta: dict, *keys, default=None):
        """DT-046: leitura tolerante a variantes de nome de campo.

        `project_metadata` e `PROJECT_PROFILE` carregam os mesmos dados com
        nomes parcialmente distintos (ex: `architecture` vs
        `architectural_profile`, `redis_purpose` vs `redis_usage`,
        `ai_purpose` vs `ai_use_cases`). O helper aceita lista de nomes e
        retorna o primeiro valor truthy encontrado.
        """
        if default is None:
            default = []
        if not isinstance(meta, dict):
            return default
        for k in keys:
            v = meta.get(k)
            if v not in (None, "", [], {}):
                return v
        return default

    @staticmethod
    def _stack_from_metadata(meta: dict) -> dict:
        """DT-046: fallback determinístico para STACK_RECOMMENDATION.

        Contrato §5: "nenhum módulo deve assumir defaults invisíveis quando o
        OCG estiver incompleto". Se o LLM consolidator não retorna
        STACK_RECOMMENDATION (JSON mal formatado, truncation, omissão), o
        sistema DEVE reconstituir a partir do que o GP já respondeu no
        questionário — não pode ficar vazio e dar a impressão de que o OCG
        não tem contexto.

        Aceita tanto `project_metadata` (montado em `ocg_service`) quanto
        `PROJECT_PROFILE` (salvo no OCG), cujos campos têm alguns nomes
        distintos. Retorno tem `source: "questionnaire_deterministic_fallback"`
        para auditar na UI/log que é fallback, não saída do LLM.
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        return {
            "frontend": {
                "enabled": bool(meta.get("has_frontend", False)),
                "stack": pick(meta, "frontend_stack"),
                "language": pick(meta, "frontend_language", default=""),
                "type": pick(meta, "frontend_type"),
                "requirements": pick(meta, "frontend_requirements"),
            },
            "backend": {
                "enabled": bool(meta.get("has_backend", False)),
                "language": pick(meta, "backend_language", default=""),
                "framework": pick(meta, "backend_framework"),
                "type": pick(meta, "backend_type"),
                "requirements": pick(meta, "backend_requirements"),
            },
            "database": {
                "engine": pick(meta, "database", default=""),
                "profile": pick(meta, "database_profile"),
            },
            "cache": {
                "enabled": bool(meta.get("uses_redis")),
                # project_metadata usa `redis_purpose`; PROJECT_PROFILE usa `redis_usage`
                "purpose": pick(meta, "redis_purpose", "redis_usage"),
            },
            "messaging": {
                "enabled": bool(meta.get("uses_messaging")),
                "purpose": pick(meta, "messaging_purpose", "messaging_usage"),
            },
            "ai": {
                "enabled": bool(meta.get("uses_ai")),
                "provider": pick(meta, "ai_provider"),
                # project_metadata usa `ai_purpose`; PROJECT_PROFILE usa `ai_use_cases`
                "purpose": pick(meta, "ai_purpose", "ai_use_cases"),
                "restrictions": pick(meta, "ai_restrictions"),
            },
            "source": "questionnaire_deterministic_fallback",
        }

    @staticmethod
    def _architecture_from_metadata(meta: dict) -> dict:
        """DT-046: fallback determinístico para ARCHITECTURE_OVERVIEW.

        Mesma motivação do `_stack_from_metadata`: o GP já respondeu Q16/Q17
        (architecture + execution_model) e Q18/Q19/Q20 (multi-tenant/HA/async)
        no questionário — não deve aparecer "vazio" na UI se o LLM omitir.
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        return {
            # project_metadata: `architecture`; PROJECT_PROFILE: `architectural_profile`
            "architectural_profile": pick(meta, "architecture", "architectural_profile"),
            "execution_model": pick(meta, "execution_model"),
            "multi_tenant": pick(meta, "multi_tenant", default=""),
            "high_availability": pick(meta, "high_availability", default=""),
            "async_processing": pick(meta, "async_processing", default=""),
            # project_metadata: `deliverables`; PROJECT_PROFILE: `main_deliverable`
            "deliverables": pick(meta, "deliverables", "main_deliverable", "pipeline_deliverables"),
            "source": "questionnaire_deterministic_fallback",
        }

    @staticmethod
    def _normalize_composite_score(raw, fallback_score: float, fallback_blocking: bool) -> dict:
        """Normaliza COMPOSITE_SCORE para dict — LLMs podem retornar float, dict ou None"""
        if isinstance(raw, dict) and raw:
            # Garantir que tem 'overall'
            if 'overall' not in raw and 'value' in raw:
                raw['overall'] = raw['value']
            if 'overall' not in raw:
                raw['overall'] = fallback_score
            return raw
        if isinstance(raw, (int, float)):
            return {"overall": raw, "is_blocking": fallback_blocking}
        return {"overall": fallback_score, "is_blocking": fallback_blocking}

    @staticmethod
    def _safe_get(obj, key, default=None):
        """Get de dict seguro — retorna default se obj não for dict"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    async def log_analysis(
        self,
        ocg_id,
        agent_name: str,
        tokens_used: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        error_message: str = None,
    ) -> OCGAnalysisLog:
        """Logar análise de agente"""
        try:
            log = OCGAnalysisLog(
                ocg_id=ocg_id,
                agent_name=agent_name,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
            )

            self.db.add(log)
            await self.db.commit()

            return log

        except Exception as e:
            logger.error("agent.log_analysis_error", agent=agent_name, error=str(e))
            # Don't raise - logging failure shouldn't block analysis

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """
        Extrai JSON válido de resposta de modelo.

        Procura por blocos JSON dentro do texto.
        """
        try:
            # Tenta parse direto
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Procura por bloco JSON dentro do texto
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: retorna dict vazio
        logger.warning("agent.json_extraction_failed", text_preview=text[:100])
        return {}
