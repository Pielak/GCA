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
        # DT-023: Ollama (camada GCA) usa env var OLLAMA_BASE_URL.
        self.base_url = (
            (settings.OLLAMA_BASE_URL or "").rstrip("/")
            if self.provider == "ollama" and settings.OLLAMA_BASE_URL
            else None
        )
        # Modelo: prefere `{PROVIDER}_MODEL` explícito do admin; se ausente,
        # usa `DEFAULT_AI_MODEL` global (consistente com ocg_updater_service
        # e ai_service). Sem isso, admin precisava setar uma env var por
        # provider mesmo tendo DEFAULT_AI_MODEL apontando para o escolhido.
        self.model = (
            getattr(settings, f"{self.provider.upper()}_MODEL", None)
            or settings.DEFAULT_AI_MODEL
        )
        # Default específico pro Ollama (admin pode override via env).
        if self.provider == "ollama" and not self.model:
            self.model = "llama3.1:8b"

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

        DT-023: Ollama dispensa chave (URL local) mas exige `OLLAMA_BASE_URL`.
        """
        if self.provider == "ollama":
            if not self.base_url:
                raise RuntimeError(
                    "Provider 'ollama' configurado (DEFAULT_AI_PROVIDER=ollama) "
                    "mas OLLAMA_BASE_URL ausente. Admin deve definir o endpoint "
                    "do daemon Ollama (ex: http://host.docker.internal:11434)."
                )
        elif not self.api_key:
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
            # OpenAI-compatible (DeepSeek, Grok, OpenAI, Ollama via /v1/chat/completions)
            provider_urls = {
                "deepseek": "https://api.deepseek.com/chat/completions",
                "openai": "https://api.openai.com/v1/chat/completions",
                "grok": "https://api.x.ai/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions",
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                # DT-023: Ollama do admin (camada GCA) via OLLAMA_BASE_URL.
                "ollama": f"{self.base_url}/v1/chat/completions" if self.base_url else None,
            }
            url = provider_urls.get(self.provider)
            if not url:
                raise ValueError(f"Provider '{self.provider}' não suportado para OCG pipeline")

            # Ollama típico não exige Authorization. Bearer só se houver api_key.
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    url,
                    headers=headers,
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

    # ========== DT-049: wrapper com retry quando LLM não devolve JSON ==========

    async def _call_llm_expecting_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        project_id=None,
        operation: str = "ocg_generation",
    ) -> tuple[dict, int]:
        """DT-049: chama `_call_llm` + extrai JSON; retry 1x se inválido.

        Alguns modelos (especialmente os menos novos) ignoram instruções de
        formato e embrulham o JSON em prosa ou markdown — e custa $0,59
        por chamada Anthropic do consolidator. Antes, o extrator devolvia
        `{}` e o fluxo seguia silenciosamente com todos os campos em
        fallback. Agora:

        1. Tenta uma vez com o prompt original.
        2. Se `_extract_json` retornar `{}` (e o texto não for vazio),
           faz **uma** retentativa apendando diretiva dura pedindo JSON
           puro. Essa tentativa usa o dobro do max_tokens base, porque
           alguns modelos cortam JSON grande.
        3. Se a segunda tentativa também vier vazia, devolve dict vazio
           + log estruturado `agent.llm_json_retry_failed` com preview.

        Retorno: `(ocg_json, tokens_totais_gastos)` — tokens somados das
        duas chamadas quando houver retry.
        """
        response_text, tokens_used = await self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            project_id=project_id,
            operation=operation,
        )
        parsed = self._extract_json(response_text)

        # Se o parser direto/fence/regex conseguiu, seguimos.
        if parsed:
            return parsed, tokens_used

        # Só faz retry se o texto não for vazio (LLM respondeu mas fora de formato).
        if not response_text or not response_text.strip():
            logger.warning(
                "agent.llm_empty_response",
                operation=operation,
                project_id=str(project_id) if project_id else None,
            )
            return {}, tokens_used

        logger.warning(
            "agent.llm_json_retry_attempt",
            operation=operation,
            project_id=str(project_id) if project_id else None,
            raw_len=len(response_text),
        )

        retry_system = system_prompt + (
            "\n\nIMPORTANTE (retry após JSON inválido): Responda APENAS com JSON puro, "
            "sem markdown (nada de ```), sem prosa explicativa, sem texto antes ou depois. "
            "O primeiro caractere da sua resposta DEVE ser `{` e o último DEVE ser `}`. "
            "Se o conteúdo for extenso, resuma arrays e strings — nunca corte o JSON no meio."
        )
        response_text_retry, tokens_retry = await self._call_llm(
            system_prompt=retry_system,
            user_prompt=user_prompt,
            max_tokens=max_tokens * 2,
            project_id=project_id,
            operation=f"{operation}_retry",
        )
        parsed_retry = self._extract_json(response_text_retry)
        total_tokens = tokens_used + tokens_retry

        if parsed_retry:
            logger.info(
                "agent.llm_json_retry_success",
                operation=operation,
                tokens_total=total_tokens,
            )
            return parsed_retry, total_tokens

        logger.error(
            "agent.llm_json_retry_failed",
            operation=operation,
            project_id=str(project_id) if project_id else None,
            tokens_wasted=total_tokens,
            preview_head=response_text_retry[:300] if response_text_retry else "",
        )
        return {}, total_tokens

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
            ocg_json, tokens_used = await self._call_llm_expecting_json(
                system_prompt=ANALYZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=pid,
                operation="analyzer",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

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
            ocg_json, tokens_used = await self._call_llm_expecting_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=pid,
                operation=f"pillar_p{pillar_id}",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

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
            ocg_json, tokens_used = await self._call_llm_expecting_json(
                system_prompt=CONSOLIDATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                project_id=req.project_id,
                operation="consolidator",
            )
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            logger.info("agent.consolidator_raw_keys",
                       keys=list(ocg_json.keys())[:15] if isinstance(ocg_json, dict) else "NOT_DICT")

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
                TESTING_REQUIREMENTS=(
                    ocg_json.get("TESTING_REQUIREMENTS")
                    or ocg_json.get("testing_requirements")
                    or ocg_json.get("testing")
                    or self._testing_from_metadata(req.project_metadata or {})
                ),
                COMPLIANCE_CHECKLIST=(
                    ocg_json.get("COMPLIANCE_CHECKLIST")
                    or ocg_json.get("compliance_checklist")
                    or ocg_json.get("compliance")
                    or self._compliance_from_metadata(req.project_metadata or {})
                ),
                DELIVERABLES=(
                    ocg_json.get("DELIVERABLES")
                    or ocg_json.get("deliverables")
                    or self._deliverables_from_metadata(req.project_metadata or {})
                ),
                ARCHITECTURE_OVERVIEW=(
                    ocg_json.get("ARCHITECTURE_OVERVIEW")
                    or ocg_json.get("architecture_overview")
                    or ocg_json.get("architecture")
                    or self._architecture_from_metadata(req.project_metadata or {})
                ),
                RISK_ANALYSIS=(
                    ocg_json.get("RISK_ANALYSIS")
                    or ocg_json.get("risk_analysis")
                    or ocg_json.get("risks")
                    or self._risk_from_metadata(req.project_metadata or {}, req.pillar_results)
                ),
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
        """Salvar OCG no banco.

        DT-048: UPSERT por `questionnaire_id` (UNIQUE no schema).
        - Se já existe OCG para o questionário: UPDATE in-place, preserva
          `id` (mantém FKs de `ocg_analysis_log`/`ocg_delta_log` íntegros),
          incrementa `version`, marca `change_type=REGENERATED`.
          `ocg_response.ocg_id` é sincronizado com o id existente para que
          o caller (consolidate_ocg) use o id correto em log_analysis.
        - Se não existe: INSERT como antes (path inicial).

        Antes deste fix, Regenerate sempre morria com
        `UniqueViolationError: ix_ocg_questionnaire_id` porque o código
        tentava INSERT cego com novo uuid4.
        """
        from sqlalchemy import select as _select

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

            # Campos comuns ao INSERT e ao UPDATE
            overall_score = (
                self._safe_get(ocg_response.COMPOSITE_SCORE, "overall")
                or self._safe_get(ocg_response.COMPOSITE_SCORE, "value")
                or (ocg_response.COMPOSITE_SCORE if isinstance(ocg_response.COMPOSITE_SCORE, (int, float)) else 0)
            )
            status = (
                self._safe_get(ocg_response.COMPOSITE_SCORE, "status")
                or ("BLOCKED" if self._safe_get(ocg_response.COMPOSITE_SCORE, "is_blocking") else "NEEDS_REVIEW")
            )
            is_blocking = bool(self._safe_get(ocg_response.COMPOSITE_SCORE, "is_blocking"))
            ocg_data_json = json.dumps(ocg_response.dict(), ensure_ascii=False, cls=UUIDEncoder)

            # DT-048: detectar OCG existente pra esse questionário
            existing = (await self.db.execute(
                _select(OCG).where(OCG.questionnaire_id == ocg_response.questionnaire_id)
            )).scalar_one_or_none()

            if existing is not None:
                existing.project_id = ocg_response.project_id
                existing.p1_business_score = _get_pillar_score(ps, 1)
                existing.p2_rules_score = _get_pillar_score(ps, 2)
                existing.p3_features_score = _get_pillar_score(ps, 3)
                existing.p4_nfr_score = _get_pillar_score(ps, 4)
                existing.p5_architecture_score = _get_pillar_score(ps, 5)
                existing.p6_data_score = _get_pillar_score(ps, 6)
                existing.p7_security_score = _get_pillar_score(ps, 7)
                existing.overall_score = overall_score
                existing.status = status
                existing.is_blocking = is_blocking
                existing.ocg_data = ocg_data_json
                existing.version = (existing.version or 1) + 1
                existing.change_type = "REGENERATED"
                existing.updated_at = datetime.now(timezone.utc)
                # Mantém generated_at inicial; regeneration não altera a origem.

                # Sincroniza o ocg_response com o id efetivamente persistido,
                # pra log_analysis/caller usarem o id correto.
                ocg_response.ocg_id = existing.id

                await self.db.commit()
                logger.info(
                    "agent.ocg_upserted",
                    ocg_id=str(existing.id),
                    version=existing.version,
                    action="update",
                )
                return existing

            # Path inicial: INSERT novo
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
                overall_score=overall_score,
                status=status,
                is_blocking=is_blocking,
                ocg_data=ocg_data_json,
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
    def _testing_from_metadata(meta: dict) -> dict:
        """DT-047: fallback determinístico para TESTING_REQUIREMENTS.

        Deriva de `test_types` (Q45), `quality_gate` (Q46), `qa_evidence`
        (Q47) e `criticality` (Q5). Nunca deixa vazio quando o GP respondeu
        esses campos no questionário.
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        test_types = pick(meta, "test_types") or []
        return {
            "test_types": test_types,
            "has_unit_tests": "Unitários" in test_types,
            "has_integration_tests": "Integração" in test_types,
            "has_e2e_tests": "E2E" in test_types,
            "has_security_tests": "Segurança" in test_types,
            "has_performance_tests": "Performance" in test_types or "Carga" in test_types,
            "quality_gate_enabled": bool(meta.get("quality_gate", False)),
            "formal_qa_enabled": bool(meta.get("formal_qa", False) or meta.get("qa_evidence", False)),
            "criticality": pick(meta, "criticality", default=""),
            # Heurística simples de cobertura esperada por criticidade
            "coverage_target_pct": {
                "Alta": 80, "Média": 70, "Baixa": 60,
            }.get(pick(meta, "criticality", default=""), 70),
            "source": "questionnaire_deterministic_fallback",
        }

    @staticmethod
    def _compliance_from_metadata(meta: dict) -> list:
        """DT-047: fallback determinístico para COMPLIANCE_CHECKLIST.

        Deriva de `security_controls` (Q43), `info_classification` (Q6),
        `ai_restrictions` (Q42) e deliverables que contêm "Plano"
        (segurança/testes/observabilidade). Retorna lista de itens no
        formato `{control, source, question}` para auditabilidade.
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        items = []
        controls = pick(meta, "security_controls") or []
        for c in controls:
            items.append({
                "control": c,
                "source": "Q43 — Controles de segurança obrigatórios",
                "status": "declared",
            })
        info_class = pick(meta, "info_classification", default="")
        if info_class:
            items.append({
                "control": f"Classificação da informação: {info_class}",
                "source": "Q6 — Classificação da informação",
                "status": "declared",
            })
        ai_restr = pick(meta, "ai_restrictions") or []
        for r in ai_restr:
            items.append({
                "control": f"Restrição de IA: {r}",
                "source": "Q42 — Restrições de IA",
                "status": "declared",
            })
        # Planos declarados em Q48 (deliverables)
        plans = pick(meta, "pipeline_deliverables", "expected_deliverables") or []
        for p in plans:
            if isinstance(p, str) and ("Plano" in p or "plano" in p):
                items.append({
                    "control": p,
                    "source": "Q48 — Entregáveis esperados",
                    "status": "declared",
                })
        return items

    @staticmethod
    def _deliverables_from_metadata(meta: dict) -> dict:
        """DT-047: fallback determinístico para DELIVERABLES.

        Deriva de `pipeline_deliverables` (Q48 — o que o GP espera que o
        pipeline entregue) e `output_formats` (formatos de saída).
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        return {
            "expected": pick(meta, "pipeline_deliverables", "expected_deliverables", "deliverables"),
            "output_formats": pick(meta, "output_formats"),
            "source": "questionnaire_deterministic_fallback",
        }

    @staticmethod
    def _risk_from_metadata(meta: dict, pillar_results=None) -> dict:
        """DT-047: fallback determinístico para RISK_ANALYSIS.

        Combina: (a) findings de severidade `high`/`critical` agregados dos
        pillar_results (quando disponíveis); (b) riscos estruturais
        derivados da criticidade + HA + multi-tenant + uso de IA.
        """
        if not isinstance(meta, dict):
            meta = {}
        pick = AgentService._pick
        high_findings = []
        if pillar_results:
            for pr in pillar_results:
                findings = getattr(pr, "findings", None) or []
                if not isinstance(findings, list):
                    continue
                for f in findings:
                    if isinstance(f, dict) and f.get("severity") in ("high", "critical"):
                        high_findings.append({
                            "pillar": f"P{getattr(pr, 'pillar_id', '?')}",
                            "severity": f.get("severity"),
                            "finding": f.get("finding") or f.get("description") or "",
                            "recommendation": f.get("recommendation") or f.get("mitigation") or "",
                        })

        structural = []
        criticality = pick(meta, "criticality", default="")
        if criticality == "Alta":
            structural.append({
                "risk": "Criticidade alta — impacto de falha elevado",
                "mitigation": "Monitoramento ativo, runbook, rollback plano",
            })
        if pick(meta, "high_availability", default="") in ("Não", "Futuramente"):
            structural.append({
                "risk": "Alta disponibilidade não planejada para a versão atual",
                "mitigation": "Documentar janela de indisponibilidade aceitável e plano de DR",
            })
        if pick(meta, "multi_tenant", default="") == "Sim":
            structural.append({
                "risk": "Multi-tenant — isolamento entre clientes obrigatório",
                "mitigation": "Revisar RBAC, auditar queries por tenant_id, testar cross-tenant",
            })
        if bool(meta.get("uses_ai")):
            structural.append({
                "risk": "Uso de IA — risco de alucinação, vazamento e custo variável",
                "mitigation": "Validação humana em output crítico, anonimização, teto de custo",
            })

        return {
            "high_findings": high_findings,
            "structural_risks": structural,
            "source": "questionnaire_deterministic_fallback",
        }

    @staticmethod
    def _normalize_composite_score(raw, fallback_score: float, fallback_blocking: bool) -> dict:
        """Normaliza COMPOSITE_SCORE para dict — LLMs podem retornar float, dict ou None.

        DT-051: garante também `status` derivado das mesmas regras do
        `CONSOLIDATOR_SYSTEM_PROMPT` (READY ≥ 90, NEEDS_REVIEW ≥ 75,
        AT_RISK < 75, BLOCKED se is_blocking). Antes esse campo só era
        gravado na coluna `ocg.status` do DB; o JSON `ocg_data` ficava sem
        ele e o email do OCG renderizava `UNKNOWN`.
        """
        def _derive_status(score: float, blocking: bool) -> str:
            if blocking:
                return "BLOCKED"
            if score >= 90:
                return "READY"
            if score >= 75:
                return "NEEDS_REVIEW"
            return "AT_RISK"

        if isinstance(raw, dict) and raw:
            if 'overall' not in raw and 'value' in raw:
                raw['overall'] = raw['value']
            if 'overall' not in raw:
                raw['overall'] = fallback_score
            if 'is_blocking' not in raw:
                raw['is_blocking'] = fallback_blocking
            if 'status' not in raw or not raw.get('status'):
                raw['status'] = _derive_status(raw['overall'], raw['is_blocking'])
            return raw
        if isinstance(raw, (int, float)):
            return {
                "overall": raw,
                "is_blocking": fallback_blocking,
                "status": _derive_status(raw, fallback_blocking),
            }
        return {
            "overall": fallback_score,
            "is_blocking": fallback_blocking,
            "status": _derive_status(fallback_score, fallback_blocking),
        }

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

        DT-049: parsing progressivo + logging verboso.
        Estratégias (primeiro hit ganha):
        1. `json.loads` direto
        2. Extração de code fence markdown ```json ... ``` ou ``` ... ```
        3. Regex greedy `\\{.*\\}` para bloco JSON solto no texto
        4. Fallback `{}` com log de erro + preview de 500 chars + length total
        """
        text = text or ""

        # 1. Parse direto
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Code fence markdown (comportamento comum em Anthropic/OpenAI
        # quando o prompt pede JSON — eles embrulham em ```json ... ```)
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Bloco JSON solto no texto (greedy — pega o maior bloco)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as e:
                # Tentar versão mais enxuta: cortar trailing commas comuns
                cleaned = re.sub(r",(\s*[\]\}])", r"\1", match.group())
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    logger.warning(
                        "agent.json_extraction_match_invalid",
                        decode_error=str(e)[:200],
                    )

        # Fallback: log verboso pra destravar troubleshooting em produção
        logger.error(
            "agent.json_extraction_failed",
            raw_len=len(text),
            preview_head=text[:300] if text else "",
            preview_tail=text[-200:] if len(text) > 200 else "",
        )
        return {}
