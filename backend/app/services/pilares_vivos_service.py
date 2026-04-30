"""
Pilares Vivos Service — Orquestrador de análise das 7 personas

Substitui documentos estáticos por análise dinâmica regenerável.
Cada ingestão dispara regeneração do documento com análises das 7 personas.

Fluxo:
1. resumir_gatekeeper_items() — transforma 87 items em summary
2. chamar_persona_opus() — chama Opus 4.7 para cada persona (em paralelo)
3. consolidar_documento() — mescla os 7 resultados
4. salvar_pilares() — persiste no BD + histórico
"""
import json
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone
import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.base import (
    PilaresVivos,
    PilaresVivosHistory,
    GatekeeperItem,
    TechnicalQuestionnaire,
    User,
)
from app.services.ai_service import AIService, AIProvider
from app.prompts.pilares_vivos_prompts import (
    PROMPT_ARQUITETO,
    PROMPT_DBA,
    PROMPT_COMPLIANCE,
    PROMPT_SEGURANCA,
    PROMPT_DEV,
    PROMPT_TESTER,
    PROMPT_QA,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


class PilaresVivosService:
    """Serviço de orquestração de Pilares Vivos"""

    # Mapping de personas para prompts
    PERSONAS = {
        "P4_Arquiteto": PROMPT_ARQUITETO,
        "P1_DBA": PROMPT_DBA,
        "P2_Compliance": PROMPT_COMPLIANCE,
        "P3_Seguranca": PROMPT_SEGURANCA,
        "P5_Dev": PROMPT_DEV,
        "P6_Tester": PROMPT_TESTER,
        "P7_QA": PROMPT_QA,
    }

    # Ordem de execução (Arquiteto primeiro, depois os 6 em paralelo)
    PERSONAS_ORDEM = ["P4_Arquiteto"]
    PERSONAS_PARALELO = ["P1_DBA", "P2_Compliance", "P3_Seguranca", "P5_Dev", "P6_Tester", "P7_QA"]

    @staticmethod
    async def resumir_gatekeeper_items(db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
        """Transforma 87 Gatekeeper items em summary estruturado.

        Returns:
            {
              "total": 87,
              "por_categoria": {"show_stopper": 12, "gap": 23, ...},
              "items_resumo": [
                {"id": "...", "categoria": "...", "titulo": "...", "impacto": "..."}
              ]
            }
        """
        result = await db.execute(
            select(GatekeeperItem).where(GatekeeperItem.project_id == project_id)
        )
        items = result.scalars().all()

        if not items:
            return {
                "total": 0,
                "por_categoria": {},
                "items_resumo": [],
            }

        # Agrupar por categoria
        por_categoria = {}
        items_resumo = []

        for item in items:
            categoria = item.category or "indefinida"
            por_categoria[categoria] = por_categoria.get(categoria, 0) + 1

            items_resumo.append({
                "id": str(item.id),
                "categoria": categoria,
                "titulo": item.title,
                "descricao": item.description,
                "impacto": item.impact or "não especificado",
                "pilares": item.linked_pillars or [],
            })

        return {
            "total": len(items),
            "por_categoria": por_categoria,
            "items_resumo": items_resumo,
        }

    @staticmethod
    async def obter_questionnaire_responses(db: AsyncSession, project_id: UUID) -> Dict[str, Any]:
        """Obtém respostas do Questionário Técnico.

        Returns:
            {
              "total_questoes": 49,
              "respondidas": 35,
              "progresso": "71%",
              "respostas": {...}  # Respostas estruturadas por questão
            }
        """
        result = await db.execute(
            select(TechnicalQuestionnaire)
            .where(TechnicalQuestionnaire.project_id == project_id)
            .order_by(TechnicalQuestionnaire.status.desc())  # submitted first
            .limit(1)
        )
        questionnaire = result.scalar_one_or_none()

        if not questionnaire:
            return {
                "total_questoes": 0,
                "respondidas": 0,
                "progresso": "0%",
                "respostas": {},
            }

        responses = questionnaire.responses or {}
        respondidas = len([v for v in responses.values() if v])

        return {
            "total_questoes": 49,
            "respondidas": respondidas,
            "progresso": f"{(respondidas / 49 * 100):.0f}%",
            "status": questionnaire.status,
            "respostas": responses,
        }

    @staticmethod
    async def chamar_persona_opus(
        persona_name: str,
        prompt_template: str,
        contexto: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Chama Opus 4.7 para análise de uma persona.

        Args:
            persona_name: Nome da persona (ex: "P1_DBA")
            prompt_template: Template do prompt (constante do pilares_vivos_prompts.py)
            contexto: Dados de contexto (gatekeeper_summary, questionnaire, etc)

        Returns:
            {
              "persona": "P1_DBA",
              "status": "completo",
              "parecer": {...},  # JSON estruturado com análise
              "dts": [...],  # Discovery Tasks
              "ai_model": "claude-opus-4-6",
            }
        """
        try:
            # Montar prompt com contexto
            prompt_final = prompt_template.format(
                gatekeeper_summary=json.dumps(contexto.get("gatekeeper_summary", {}), ensure_ascii=False, indent=2),
                questionnaire=json.dumps(contexto.get("questionnaire", {}), ensure_ascii=False, indent=2),
                sub_tasks=contexto.get("sub_tasks", ""),
                arquiteto_resultado=json.dumps(contexto.get("arquiteto_resultado", {}), ensure_ascii=False, indent=2),
            )

            # Chamar Opus 4.7
            success, response, error = await AIService.query(
                prompt=prompt_final,
                provider=AIProvider.ANTHROPIC,
                model="claude-opus-4-6",
                system_prompt="Você é um especialista em análise de requisitos e arquitetura de software. Retorne respostas estruturadas em JSON válido.",
                temperature=0.5,
                max_tokens=8000,
            )

            if not success:
                logger.error(f"pilares_vivos.persona_call_failed", persona=persona_name, error=error)
                return {
                    "persona": persona_name,
                    "status": "erro",
                    "erro": error,
                    "ai_model": "claude-opus-4-6",
                }

            # Parse resposta como JSON
            try:
                parecer = json.loads(response)
            except json.JSONDecodeError:
                # Se não for JSON válido, encapsule em estrutura padrão
                parecer = {
                    "analise_texto": response,
                    "status": "parseado_como_texto",
                }

            return {
                "persona": persona_name,
                "status": "completo",
                "parecer": parecer,
                "dts": parecer.get("dts", []),
                "ai_model": "claude-opus-4-6",
            }

        except Exception as e:
            logger.error(f"pilares_vivos.persona_call_exception", persona=persona_name, error=str(e))
            return {
                "persona": persona_name,
                "status": "erro",
                "erro": str(e),
                "ai_model": "claude-opus-4-6",
            }

    @staticmethod
    async def consolidar_documento(
        arquiteto_result: Dict[str, Any],
        personas_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mescla análises das 7 personas em documento consolidado.

        Args:
            arquiteto_result: Resultado da análise do Arquiteto
            personas_results: {"P1_DBA": {...}, "P2_Compliance": {...}, ...}

        Returns:
            {
              "P4_Arquiteto": {...},
              "P1_DBA": {...},
              ...
              "consolidado_em": "2026-04-29T21:45:00Z",
              "versao": 1,
            }
        """
        documento = {
            "P4_Arquiteto": arquiteto_result,
            **personas_results,
            "consolidado_em": datetime.now(timezone.utc).isoformat(),
            "versao": 1,
        }

        return documento

    @staticmethod
    async def salvar_pilares(
        db: AsyncSession,
        project_id: UUID,
        documento: Dict[str, Any],
        gatekeeper_summary: Dict[str, Any],
        questionnaire_responses: Dict[str, Any],
        user_id: UUID,
    ) -> PilaresVivos:
        """Salva Pilares Vivos no BD.

        Se já existir, move versão anterior para histórico.
        """
        # Buscar Pilares Vivos existente
        result = await db.execute(
            select(PilaresVivos).where(PilaresVivos.project_id == project_id)
        )
        pilares_atual = result.scalar_one_or_none()

        # Se existe, move para histórico
        if pilares_atual:
            historia = PilaresVivosHistory(
                project_id=project_id,
                pilares_vivos_id=pilares_atual.id,
                documento=pilares_atual.documento,
                gatekeeper_summary=pilares_atual.gatekeeper_summary,
                questionnaire_responses=pilares_atual.questionnaire_responses,
                gerado_por=pilares_atual.gerado_por,
                gerado_em=pilares_atual.gerado_em,
                personas_modificadas=PilaresVivosService._detectar_mudancas(
                    pilares_atual.documento,
                    documento,
                ),
            )
            db.add(historia)

            # Atualizar Pilares Vivos
            pilares_atual.documento = documento
            pilares_atual.gatekeeper_summary = gatekeeper_summary
            pilares_atual.questionnaire_responses = questionnaire_responses
            pilares_atual.gerado_por = user_id
            pilares_atual.regenerado_em = datetime.now(timezone.utc)
            pilares_atual.updated_at = datetime.now(timezone.utc)
        else:
            # Criar novo
            pilares_atual = PilaresVivos(
                project_id=project_id,
                documento=documento,
                gatekeeper_summary=gatekeeper_summary,
                questionnaire_responses=questionnaire_responses,
                gerado_por=user_id,
            )
            db.add(pilares_atual)

        await db.commit()
        logger.info(f"pilares_vivos.saved", project_id=str(project_id), user_id=str(user_id))

        return pilares_atual

    @staticmethod
    def _detectar_mudancas(
        documento_antigo: Dict[str, Any],
        documento_novo: Dict[str, Any],
    ) -> List[str]:
        """Detecta quais personas mudaram entre versões."""
        mudancas = []

        for persona in ["P4_Arquiteto", "P1_DBA", "P2_Compliance", "P3_Seguranca", "P5_Dev", "P6_Tester", "P7_QA"]:
            if documento_antigo.get(persona) != documento_novo.get(persona):
                mudancas.append(persona)

        return mudancas

    @staticmethod
    async def regenerar_pilares(
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Orquestra regeneração completa de Pilares Vivos.

        Fluxo:
        1. Resumir Gatekeeper items
        2. Obter respostas Questionário
        3. Chamar Arquiteto (hub central)
        4. Chamar 6 personas em paralelo (com sub-tasks do Arquiteto)
        5. Consolidar documento
        6. Salvar BD + histórico

        Returns:
            {
              "sucesso": True,
              "documento": {...},
              "tempo_total": 45.2,
              "erros": [],
            }
        """
        import time
        tempo_inicio = time.time()

        logger.info(f"pilares_vivos.regeneracao_iniciada", project_id=str(project_id))

        try:
            # Step 1: Resumir Gatekeeper items
            logger.info(f"pilares_vivos.step1_resumindo_items", project_id=str(project_id))
            gatekeeper_summary = await PilaresVivosService.resumir_gatekeeper_items(db, project_id)

            # Step 2: Obter Questionário
            logger.info(f"pilares_vivos.step2_obtendo_questionnaire", project_id=str(project_id))
            questionnaire = await PilaresVivosService.obter_questionnaire_responses(db, project_id)

            contexto_base = {
                "gatekeeper_summary": gatekeeper_summary,
                "questionnaire": questionnaire,
            }

            # Step 3: Chamar Arquiteto (PRIMEIRO, sequencial)
            logger.info(f"pilares_vivos.step3_chamando_arquiteto", project_id=str(project_id))
            arquiteto_result = await PilaresVivosService.chamar_persona_opus(
                "P4_Arquiteto",
                PROMPT_ARQUITETO,
                contexto_base,
            )

            if arquiteto_result["status"] == "erro":
                logger.error(f"pilares_vivos.arquiteto_failed", project_id=str(project_id), erro=arquiteto_result["erro"])
                return {
                    "sucesso": False,
                    "erro": f"Arquiteto falhou: {arquiteto_result['erro']}",
                    "tempo_total": time.time() - tempo_inicio,
                }

            # Step 4: Chamar 6 personas em paralelo
            logger.info(f"pilares_vivos.step4_chamando_personas_paralelo", project_id=str(project_id))
            tasks = []

            for persona_name in PilaresVivosService.PERSONAS_PARALELO:
                contexto = contexto_base.copy()
                contexto["arquiteto_resultado"] = arquiteto_result
                contexto["sub_tasks"] = arquiteto_result.get("parecer", {}).get("distribuir_para", {}).get(persona_name, "")

                task = PilaresVivosService.chamar_persona_opus(
                    persona_name,
                    PilaresVivosService.PERSONAS[persona_name],
                    contexto,
                )
                tasks.append(task)

            personas_results = await asyncio.gather(*tasks)

            # Converter lista em dict
            personas_dict = {result["persona"]: result for result in personas_results}

            # Step 5: Consolidar
            logger.info(f"pilares_vivos.step5_consolidando", project_id=str(project_id))
            documento = await PilaresVivosService.consolidar_documento(
                arquiteto_result,
                personas_dict,
            )

            # Step 6: Salvar
            logger.info(f"pilares_vivos.step6_salvando", project_id=str(project_id))
            pilares = await PilaresVivosService.salvar_pilares(
                db,
                project_id,
                documento,
                gatekeeper_summary,
                questionnaire,
                user_id,
            )

            tempo_total = time.time() - tempo_inicio
            logger.info(f"pilares_vivos.regeneracao_concluida", project_id=str(project_id), tempo=tempo_total)

            return {
                "sucesso": True,
                "documento": documento,
                "tempo_total": tempo_total,
                "pilares_id": str(pilares.id),
            }

        except Exception as e:
            tempo_total = time.time() - tempo_inicio
            logger.error(f"pilares_vivos.regeneracao_falhou", project_id=str(project_id), erro=str(e), tempo=tempo_total)
            return {
                "sucesso": False,
                "erro": str(e),
                "tempo_total": tempo_total,
            }
