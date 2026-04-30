"""
Pilares Vivos Service — Orquestrador de análise das 7 personas

Substitui documentos estáticos por análise dinâmica regenerável.
Cada ingestão dispara regeneração do documento com análises das 7 personas.

Fluxo:
1. resumir_gatekeeper_items() — transforma 87 items em summary
2. chamar_persona() — chama LLM para cada persona (em paralelo)
3. consolidar_documento() — mescla os 7 resultados
4. salvar_pilares() — persiste no BD + histórico
"""
import json
import time
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
from app.services.ai_key_resolver import AIKeyResolver
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

    # 2026-05-01: Todas as 7 personas rodam em paralelo.
    # A dependência do Arquiteto (sub_tasks) foi removida para eliminar
    # o gargalo de 5min de chamadas LLM sequenciais.
    PERSONAS_ORDER = ["P4_Arquiteto", "P1_DBA", "P2_Compliance", "P3_Seguranca", "P5_Dev", "P6_Tester", "P7_QA"]

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
            categoria = item.item_type or "indefinida"
            por_categoria[categoria] = por_categoria.get(categoria, 0) + 1

            # item_data é JSON — extrair campos disponíveis
            dados = {}
            if item.item_data:
                try:
                    dados = json.loads(item.item_data)
                except (json.JSONDecodeError, TypeError):
                    dados = {}

            items_resumo.append({
                "id": str(item.id),
                "categoria": categoria,
                "titulo": dados.get("text", dados.get("title", "sem título")),
                "descricao": dados.get("text", dados.get("description", "")),
                "impacto": dados.get("impacto", dados.get("severity", "não especificado")),
                "pilares": dados.get("linked_pillars", dados.get("pillars", [])),
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
    async def chamar_persona(
        persona_name: str,
        prompt_template: str,
        contexto: Dict[str, Any],
        provider_name: str = "deepseek",
        model_name: str = "deepseek-chat",
    ) -> Dict[str, Any]:
        """Chama IA para análise de uma persona.

        Args:
            persona_name: Nome da persona (ex: "P1_DBA")
            prompt_template: Template do prompt
            contexto: Dados de contexto
            provider_name: Provider LLM (do projeto)
            model_name: Modelo específico

        Returns:
            {
              "persona": "P1_DBA",
              "status": "completo",
              "parecer": {...},
              "dts": [...],
              "ai_model": model_name,
            }
        """
        try:
            gk = contexto.get("gatekeeper_summary", {})
            qr = contexto.get("questionnaire", {})
            por_cat = gk.get("por_categoria", {})

            kwargs = {
                "projeto_nome": qr.get("projeto_nome", contexto.get("project_name", "Projeto")),
                "total_items": str(gk.get("total", 0)),
                "visao_gp": qr.get("respostas", {}).get("visao_geral", qr.get("visao_gp", "Não informada")),
                "show_stoppers_count": str(por_cat.get("show_stopper", 0)),
                "show_stoppers_por_pillar": str(por_cat.get("show_stopper_por_pillar", "")),
                "gaps_count": str(por_cat.get("gap", 0)),
                "gaps_por_pillar": str(por_cat.get("gap_por_pillar", "")),
                "poor_definitions_count": str(por_cat.get("poor_definition", 0)),
                "poor_definitions_por_pillar": str(por_cat.get("poor_definition_por_pillar", "")),
                "improvements_count": str(por_cat.get("improvement", 0)),
                "improvements_por_pillar": str(por_cat.get("improvement_por_pillar", "")),
                "decisao_arquiteto": contexto.get("decisao_arquiteto", "Pendente de definição arquitetural"),
                "dominios": contexto.get("dominios", "Pendente de mapeamento de domínios"),
                "fluxos_integracao": contexto.get("fluxos_integracao", "Pendente de definição de fluxos"),
                "componentes_criticos": contexto.get("componentes_criticos", "Pendente"),
                "dados_sensiveis": contexto.get("dados_sensiveis", "Pendente"),
                # items_p1-p6 referenciados nos prompts das personas
                "items_p1": gk.get("P1_Dados", ""),
                "items_p2": gk.get("P2_Compliance", ""),
                "items_p3": gk.get("P3_Seguranca", ""),
                "items_p5": gk.get("P5_Dev", ""),
                "items_p6": gk.get("P6_Tester", ""),
                "subtarefa_dba": contexto.get("subtarefa_dba", ""),
                "subtarefa_compliance": contexto.get("subtarefa_compliance", ""),
                "subtarefa_seguranca": contexto.get("subtarefa_seguranca", ""),
                "subtarefa_dev": contexto.get("subtarefa_dev", ""),
                "subtarefa_tester": contexto.get("subtarefa_tester", ""),
            }

            prompt_final = prompt_template.format(**kwargs)

            provider_enum = AIProvider(provider_name)
            success, response, error = await asyncio.wait_for(
                AIService.query(
                    prompt=prompt_final,
                    provider=provider_enum,
                    model=model_name,
                    system_prompt="Você é um especialista em análise de requisitos e arquitetura de software. Retorne respostas estruturadas em JSON válido.",
                    temperature=0.3,
                    max_tokens=5000,
                ),
                timeout=120.0,
            )

            if not success:
                logger.error(f"pilares_vivos.persona_call_failed", persona=persona_name, error=error)
                return {
                    "persona": persona_name,
                    "status": "erro",
                    "erro": error,
                    "ai_model": model_name,
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
                "ai_model": model_name,
            }

        except Exception as e:
            logger.error(f"pilares_vivos.persona_call_exception", persona=persona_name, error=str(e))
            return {
                "persona": persona_name,
                "status": "erro",
                "erro": str(e),
                "ai_model": model_name,
            }

    @staticmethod
    async def consolidar_documento(
        todos_resultados: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mescla análises das 7 personas em documento consolidado.

        Args:
            todos_resultados: {"P4_Arquiteto": {...}, "P1_DBA": {...}, ...}

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
            **todos_resultados,
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

        for persona in PilaresVivosService.PERSONAS_ORDER:
            if documento_antigo.get(persona) != documento_novo.get(persona):
                mudancas.append(persona)

        return mudancas

    @staticmethod
    async def regenerar_pilares(
        db: AsyncSession,
        project_id: UUID,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Orquestra regeneração completa de Pilares Vivos (paralelizado).

        Fluxo:
        1. Resumir Gatekeeper items
        2. Obter respostas Questionário
        3. Chamar 7 personas EM PARALELO (sem dependência do Arquiteto)
        4. Consolidar documento
        5. Salvar BD + histórico

        Returns:
            {
              "sucesso": True,
              "documento": {...},
              "tempo_total": 45.2,
              "erros": [],
            }
        """
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

            # Resolver provider do projeto (ex: deepseek, configurado pelo GP)
            provider_chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)
            if provider_chain and isinstance(provider_chain[0], dict):
                provider_name = provider_chain[0].get("provider", settings.DEFAULT_AI_PROVIDER)
                model_name = provider_chain[0].get("model") or (
                    "deepseek-chat" if provider_name == "deepseek" else f"{provider_name}-chat"
                )
            else:
                provider_name = provider_chain[0] if provider_chain else settings.DEFAULT_AI_PROVIDER
                model_name = "deepseek-chat" if provider_name == "deepseek" else f"{provider_name}-chat"

            logger.info(
                "pilares_vivos.provider_resolved",
                project_id=str(project_id),
                provider=provider_name,
                model_name=model_name,
            )

            # Step 3: Chamar TODAS as 7 personas em paralelo
            logger.info(f"pilares_vivos.step3_chamando_7_personas_paralelo", project_id=str(project_id))
            tasks = [
                PilaresVivosService.chamar_persona(
                    persona_name,
                    PilaresVivosService.PERSONAS[persona_name],
                    contexto_base,
                    provider_name=provider_name,
                    model_name=model_name,
                )
                for persona_name in PilaresVivosService.PERSONAS_ORDER
            ]

            resultados = await asyncio.gather(*tasks, return_exceptions=True)

            # Log cada resultado
            for r in resultados:
                if isinstance(r, Exception):
                    logger.error(f"pilares_vivos.persona_exception", erro=str(r))
                else:
                    logger.info(f"pilares_vivos.persona_concluida", persona=r.get("persona"), status=r.get("status"))

            # Converter lista em dict (ignorando exceções)
            personas_dict = {}
            for r in resultados:
                if isinstance(r, Exception):
                    continue
                personas_dict[r["persona"]] = r

            # Step 4: Consolidar
            logger.info(f"pilares_vivos.step4_consolidando", project_id=str(project_id))
            documento = await PilaresVivosService.consolidar_documento(personas_dict)

            # Step 5: Salvar
            logger.info(f"pilares_vivos.step5_salvando", project_id=str(project_id))
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
