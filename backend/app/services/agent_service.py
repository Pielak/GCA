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
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Detectar provider configurado pelo admin
        self.provider = settings.DEFAULT_AI_PROVIDER or "anthropic"
        self.api_key = getattr(settings, f"{self.provider.upper()}_API_KEY", None) or settings.ANTHROPIC_API_KEY
        self.model = getattr(settings, f"{self.provider.upper()}_MODEL", None) or settings.ANTHROPIC_MODEL

        if self.provider == "anthropic" and self.api_key:
            self.client = AsyncAnthropic(api_key=self.api_key)
        else:
            self.client = None  # Usará _call_llm via httpx

    async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> tuple[str, int]:
        """Chamada unificada ao LLM — suporta Anthropic e OpenAI-compatible (DeepSeek, Grok, etc.)
        Returns: (response_text, tokens_used)
        """
        import httpx

        if self.provider == "anthropic" and self.client:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=getattr(settings, 'ANTHROPIC_TEMPERATURE', 0.3),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens
            return text, tokens

        # OpenAI-compatible (DeepSeek, Grok, OpenAI)
        provider_urls = {
            "deepseek": "https://api.deepseek.com/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions",
            "grok": "https://api.x.ai/v1/chat/completions",
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
        tokens = data.get("usage", {}).get("total_tokens", 0)
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

            # Chamar LLM (Anthropic, DeepSeek, etc.)
            start_time = datetime.now(timezone.utc)
            response_text, tokens_used = await self._call_llm(
                system_prompt=ANALYZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
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

            # Chamar LLM
            start_time = datetime.now(timezone.utc)
            response_text, tokens_used = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
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
            for pillar_id in range(1, 8):
                # Filtrar perguntas para este pilar
                pillar_question_ids = analyzer_result.classification.get(f"P{pillar_id}", [])
                pillar_questions = [q for q in req.questions if q.get("question_id") in pillar_question_ids]

                if not pillar_questions:
                    logger.warning(f"agent.pillar_no_questions", pillar_id=pillar_id)
                    # Criar response vazio como coroutine
                    task = create_empty_pillar_response(pillar_id)
                    tasks.append(task)
                    continue

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

            # Executar em paralelo
            results = await asyncio.gather(*tasks, return_exceptions=False)
            results = [r for r in results if isinstance(r, PillarAgentResponse)]

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
                analyzer_output_json=json.dumps(analyzer_json, ensure_ascii=False, indent=2, cls=UUIDEncoder),
                pillar_results_json=json.dumps(pillar_json, ensure_ascii=False, indent=2, cls=UUIDEncoder),
            )

            # Chamar LLM
            start_time = datetime.now(timezone.utc)
            response_text, tokens_used = await self._call_llm(
                system_prompt=CONSOLIDATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Extrair JSON
            ocg_json = self._extract_json(response_text)

            # Construir OCGResponse
            ocg_response = OCGResponse(
                ocg_id=uuid4(),
                questionnaire_id=req.questionnaire_id,
                project_id=req.project_id,
                generated_at=datetime.now(timezone.utc),
                PROJECT_PROFILE=ocg_json.get("PROJECT_PROFILE", {}),
                PILLAR_SCORES=ocg_json.get("PILLAR_SCORES", {}),
                COMPOSITE_SCORE=ocg_json.get("COMPOSITE_SCORE", {}),
                STACK_RECOMMENDATION=ocg_json.get("STACK_RECOMMENDATION", {}),
                CRITICAL_FINDINGS=ocg_json.get("CRITICAL_FINDINGS", []),
                TESTING_REQUIREMENTS=ocg_json.get("TESTING_REQUIREMENTS", {}),
                COMPLIANCE_CHECKLIST=ocg_json.get("COMPLIANCE_CHECKLIST", []),
                DELIVERABLES=ocg_json.get("DELIVERABLES", {}),
                ARCHITECTURE_OVERVIEW=ocg_json.get("ARCHITECTURE_OVERVIEW", {}),
                RISK_ANALYSIS=ocg_json.get("RISK_ANALYSIS", {}),
                APPROVAL_STATUS=ocg_json.get("APPROVAL_STATUS", {}),
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
                overall_score=ocg_response.COMPOSITE_SCORE.get("overall", 0),
                is_blocking=ocg_response.COMPOSITE_SCORE.get("is_blocking", False),
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
            ocg = OCG(
                id=ocg_response.ocg_id,
                questionnaire_id=ocg_response.questionnaire_id,
                project_id=ocg_response.project_id,
                p1_business_score=ocg_response.PILLAR_SCORES.get("P1_Business", {}).get("score", 0),
                p2_rules_score=ocg_response.PILLAR_SCORES.get("P2_Rules", {}).get("score", 0),
                p3_features_score=ocg_response.PILLAR_SCORES.get("P3_Features", {}).get("score", 0),
                p4_nfr_score=ocg_response.PILLAR_SCORES.get("P4_NFR", {}).get("score", 0),
                p5_architecture_score=ocg_response.PILLAR_SCORES.get("P5_Architecture", {}).get("score", 0),
                p6_data_score=ocg_response.PILLAR_SCORES.get("P6_Data", {}).get("score", 0),
                p7_security_score=ocg_response.PILLAR_SCORES.get("P7_Security", {}).get("score", 0),
                overall_score=ocg_response.COMPOSITE_SCORE.get("overall", 0),
                status=ocg_response.COMPOSITE_SCORE.get("status", "NEEDS_REVIEW"),
                is_blocking=ocg_response.COMPOSITE_SCORE.get("is_blocking", False),
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
