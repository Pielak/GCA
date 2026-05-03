"""FASE 1 — OCG Consolidator Service.

Consolida análises das 7 personas em atualizações do OCG, detecta conflitos,
e arbitra sem acumular contradições. Segue regra do §2.4 contrato:
  - OCG só expande com informação de valor
  - Nunca contrai
  - Documentos com conflitos graves → quarentena, não afetam OCG
"""
import json
import statistics
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.base import OCG, ConflictPendingReview, Questionnaire
from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
from app.models.auditor_output import AuditorOutput

logger = structlog.get_logger(__name__)

# Persona → Pillar mapping (which persona validates which pillar)
PERSONA_TO_PILLAR = {
    "gp": "p1_business_score",     # Gerente: Business value
    "arq": "p5_architecture_score", # Arquiteto: Architecture
    "dba": "p6_data_score",         # DBA: Data/Schema
    "dev": "p5_architecture_score", # Dev: Implementation feasibility
    "qa": "p4_nfr_score",           # QA: NFR, test coverage
    "ux": "p3_features_score",      # UX: Feature completeness
    "ui": "p3_features_score",      # UI: Design system alignment
}

# Threshold for conflict: if variance in scores > this, flag as conflict
CONFLICT_VARIANCE_THRESHOLD = 15.0  # Points on 0-100 scale


class OCGConsolidatorService:
    """Consolida análises de personas em OCG, detecta/arbitra conflitos."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def consolidate_from_personas(
        self,
        project_id: UUID,
        personas_responses: dict[str, GatekeeperPersonaResponse],
        auditor_output: AuditorOutput,
    ) -> dict:
        """
        Consolida análises de 7 personas em OCG, detecta conflitos.

        Args:
            project_id: UUID do projeto
            personas_responses: dict[persona_tag] → GatekeeperPersonaResponse
            auditor_output: AuditorOutput da Fase 2

        Returns:
        {
            'ocg_updates': {field: value, ...},
            'conflicts_pending': [ConflictPendingReview, ...],
            'strategic_questions': [question, ...],
        }
        """
        try:
            logger.info(
                "consolidator.start",
                project_id=str(project_id),
                personas_count=len(personas_responses),
            )

            # 1️⃣ Carregar ou criar OCG
            questionnaire = await self._get_or_create_questionnaire(project_id)
            ocg = await self._load_or_create_ocg(questionnaire.id, project_id)

            # 2️⃣ Consolidar pillar scores
            pillar_updates = await self._consolidate_pillar_scores(
                ocg, personas_responses, auditor_output
            )

            # 3️⃣ Detectar conflitos
            conflicts_pending = await self._detect_and_persist_conflicts(
                project_id=project_id,
                personas_responses=personas_responses,
                auditor_output=auditor_output,
                route_map_id=auditor_output.route_map_id,
            )

            # 4️⃣ Coletar questões estratégicas
            strategic_questions = self._extract_strategic_questions(
                auditor_output, personas_responses
            )

            # 5️⃣ Atualizar OCG no DB (se há consenso)
            ocg_updates = await self._apply_ocg_updates(
                ocg, pillar_updates, project_id
            )

            logger.info(
                "consolidator.complete",
                project_id=str(project_id),
                fields_updated=len(ocg_updates),
                conflicts_pending=len(conflicts_pending),
                questions=len(strategic_questions),
            )

            return {
                'ocg_updates': ocg_updates,
                'conflicts_pending': conflicts_pending,
                'strategic_questions': strategic_questions,
            }

        except Exception as e:
            logger.error(
                "consolidator.failed",
                project_id=str(project_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def _get_or_create_questionnaire(self, project_id: UUID):
        """Busca questionário do projeto: primeiro questionnaires, depois technical_questionnaires."""
        from sqlalchemy import text
        stmt = select(Questionnaire).where(
            Questionnaire.project_id == project_id
        ).order_by(Questionnaire.created_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        questionnaire = result.scalars().first()

        if questionnaire:
            return questionnaire

        # Fallback: technical_questionnaires com status 'submitted'
        stmt2 = text(
            "SELECT id, project_id, status, created_at FROM technical_questionnaires "
            "WHERE project_id = :pid AND status = 'submitted' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        result2 = await self.db.execute(stmt2, {"pid": str(project_id)})
        tech_row = result2.first()
        if tech_row:
            logger.info(
                "ocg_consolidator.using_technical_questionnaire",
                tech_id=str(tech_row[0]),
                project_id=str(project_id),
            )
            # Retorna objeto compatível (duck typing: .id é o que importa)
            class _TQ:
                def __init__(self, row):
                    self.id = row[0]
                    self.project_id = row[1]
                    self.status = row[2]
                    self.created_at = row[3]
            return _TQ(tech_row)

        # FASE 1: Se não há questionário, criar placeholder para permitir
        # que o OCG seja gerado a partir da ingestão de documentos (Phase B).
        # Isso evita que o pipeline fique preso em "awaiting_ocg" para sempre.
        logger.info(
            "ocg_consolidator.creating_placeholder",
            project_id=str(project_id),
        )
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz

        placeholder = Questionnaire(
            id=_uuid.uuid4(),
            project_id=project_id,
            gp_email="placeholder@gca.internal",
            responses=json.dumps({}),
            status="placeholder",
            approved=False,
            submitted_at=_dt.now(_tz.utc),
            created_at=_dt.now(_tz.utc),
        )
        self.db.add(placeholder)
        await self.db.flush()
        return placeholder

    async def _load_or_create_ocg(
        self, questionnaire_id: UUID, project_id: UUID
    ) -> OCG:
        """Carrega OCG existente ou cria novo."""
        stmt = select(OCG).where(
            OCG.questionnaire_id == questionnaire_id
        ).order_by(OCG.version.desc()).limit(1)
        result = await self.db.execute(stmt)
        ocg = result.scalars().first()

        if not ocg:
            # Criar OCG novo (versão 1)
            ocg = OCG(
                questionnaire_id=questionnaire_id,
                project_id=project_id,
                version=1,
                schema_version="1.0.0",
                status="READY",
                is_blocking=False,
                change_type="INITIAL",
                ocg_data=json.dumps({}),
                generated_at=datetime.now(timezone.utc),
            )
            self.db.add(ocg)
            await self.db.flush()

        return ocg

    async def _consolidate_pillar_scores(
        self,
        ocg: OCG,
        personas_responses: dict[str, GatekeeperPersonaResponse],
        auditor_output: AuditorOutput,
    ) -> dict[str, float]:
        """
        Consolida scores de pillares a partir de personas.

        Lógica:
        - Para cada pillar, coletar scores das personas responsáveis
        - Se variância > threshold: registrar como conflito (não aplicar)
        - Se consenso: calcular média e aplicar ao OCG
        """
        updates = {}

        # Agrupar personas por pillar
        pillar_to_personas = {}
        for persona_tag, response in personas_responses.items():
            if persona_tag not in PERSONA_TO_PILLAR:
                continue
            pillar = PERSONA_TO_PILLAR[persona_tag]
            if pillar not in pillar_to_personas:
                pillar_to_personas[pillar] = []
            pillar_to_personas[pillar].append((persona_tag, response))

        # Consolidar cada pillar
        for pillar, persona_list in pillar_to_personas.items():
            scores = [
                resp.scores.get("overall", 50) if isinstance(resp.scores, dict)
                else 50
                for _, resp in persona_list
            ]

            if not scores:
                continue

            # Calcular variância
            variance = max(scores) - min(scores) if scores else 0

            if variance > CONFLICT_VARIANCE_THRESHOLD:
                # Conflito: não aplicar neste momento, será tratado por HITL
                logger.warning(
                    "consolidator.pillar_conflict",
                    pillar=pillar,
                    variance=variance,
                    scores=scores,
                )
                continue

            # Consenso: calcular média e aplicar
            avg_score = statistics.mean(scores) if scores else 50
            updates[pillar] = min(100, max(0, avg_score))

        return updates

    async def _detect_and_persist_conflicts(
        self,
        project_id: UUID,
        personas_responses: dict[str, GatekeeperPersonaResponse],
        auditor_output: AuditorOutput,
        route_map_id: UUID,
    ) -> list[dict]:
        """Detecta conflitos entre personas e persiste no DB."""
        conflicts = []

        # Agrupar personas por pillar novamente
        pillar_to_personas = {}
        for persona_tag, response in personas_responses.items():
            if persona_tag not in PERSONA_TO_PILLAR:
                continue
            pillar = PERSONA_TO_PILLAR[persona_tag]
            if pillar not in pillar_to_personas:
                pillar_to_personas[pillar] = {}
            pillar_to_personas[pillar][persona_tag] = response

        # Detectar conflitos de pillar scores
        for pillar, persona_dict in pillar_to_personas.items():
            scores = {}
            for persona_tag, response in persona_dict.items():
                score = response.scores.get("overall", 50) if isinstance(response.scores, dict) else 50
                scores[persona_tag] = score

            # Checkar variância
            variance = max(scores.values()) - min(scores.values()) if scores else 0
            if variance > CONFLICT_VARIANCE_THRESHOLD:
                # Criar ConflictPendingReview
                conflict = ConflictPendingReview(
                    project_id=project_id,
                    document_id=auditor_output.route_map.document_id,
                    route_map_id=route_map_id,
                    field_name=pillar,
                    personas_involved=list(scores.keys()),
                    values_by_persona=scores,
                    conflict_reason=f"Personas discordam sobre {pillar}: variância de {variance:.1f} pontos",
                    status="pending",
                )
                self.db.add(conflict)
                conflicts.append({
                    "conflict_id": str(conflict.id),
                    "field": pillar,
                    "personas_involved": list(scores.keys()),
                    "values": scores,
                })

        await self.db.flush()

        logger.info(
            "consolidator.conflicts_detected",
            count=len(conflicts),
        )

        return conflicts

    def _extract_strategic_questions(
        self,
        auditor_output: AuditorOutput,
        personas_responses: dict[str, GatekeeperPersonaResponse],
    ) -> list[dict]:
        """Extrai questões estratégicas para o usuário."""
        questions = []

        # Questões do Auditor
        if auditor_output.questionnaire_to_human:
            for q in auditor_output.questionnaire_to_human:
                questions.append({
                    "source": "auditor",
                    "question": q.get("question") if isinstance(q, dict) else str(q),
                    "priority": q.get("priority", "normal") if isinstance(q, dict) else "normal",
                })

        # Questões das personas (passada 1 é tentativa)
        for persona_tag, response in personas_responses.items():
            if response.questions:
                for q in response.questions:
                    questions.append({
                        "source": persona_tag,
                        "question": q.get("question") if isinstance(q, dict) else str(q),
                        "priority": q.get("priority", "normal") if isinstance(q, dict) else "normal",
                    })

        logger.info(
            "consolidator.strategic_questions",
            count=len(questions),
        )

        return questions

    async def _apply_ocg_updates(
        self,
        ocg: OCG,
        updates: dict[str, float],
        project_id: UUID,
    ) -> dict:
        """Aplica updates ao OCG no DB."""
        if not updates:
            return {}

        # Atualizar campos individuais
        for field, value in updates.items():
            if hasattr(ocg, field):
                setattr(ocg, field, value)

        # Recalcular overall_score
        scores = [
            getattr(ocg, f"p{i}_score", None)
            for i in range(1, 8)
        ]
        scores = [s for s in scores if s is not None]
        if scores:
            ocg.overall_score = statistics.mean(scores)

        # Atualizar versionamento
        ocg.version += 1
        ocg.updated_at = datetime.now(timezone.utc)
        ocg.change_type = "EXPAND"

        self.db.add(ocg)
        await self.db.flush()

        return {field: value for field, value in updates.items()}
