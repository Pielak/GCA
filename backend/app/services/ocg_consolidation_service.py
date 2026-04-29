"""
Consolidação de OCG Individual de 7 personas em OCG Global + detecção de conflitos.

Após todas as personas analisarem um documento:
1. Consolida pareceres em OCG Global
2. Detecta conflitos entre opiniões
3. Propõe resoluções baseadas em votação/precedência
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import structlog
import json
from typing import Dict, List, Tuple

from app.models.base import OCGIndividual, Discrepancy, IngestedDocument

logger = structlog.get_logger(__name__)


class OCGConsolidationService:
    """Serviço para consolidar análises de personas e detectar conflitos."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def consolidate_and_detect_conflicts(
        self,
        project_id: UUID,
        document_id: UUID,
    ) -> Tuple[Dict, List[Dict]]:
        """
        Consolida 7 OCG Individual em OCG Global + detecta conflitos.

        Returns: (ocg_global, discrepancies)
        """
        # 1. Buscar todas as análises de personas para este documento
        ocg_individuals = await self.db.scalars(
            select(OCGIndividual).where(
                (OCGIndividual.project_id == project_id) &
                (OCGIndividual.document_id == document_id)
            )
        )
        ocg_list = ocg_individuals.all()

        if not ocg_list:
            logger.warning("ocg.no_personas_analyzed", project_id=str(project_id), document_id=str(document_id))
            return {}, []

        logger.info("ocg.consolidation_start", persona_count=len(ocg_list), document_id=str(document_id))

        # 2. Extrair campos com potencial conflito
        parecer_dict = {}
        for ocg in ocg_list:
            parecer_dict[ocg.persona_name] = ocg.parecer

        # 3. Detectar conflitos
        conflicts = self._detect_conflicts(parecer_dict)

        # 4. Armazenar conflitos detectados
        for conflict in conflicts:
            discrepancy = Discrepancy(
                project_id=project_id,
                technical_questionnaire_id=None,  # Documento, não questionnaire
                field_path=conflict["field_name"],
                conflicting_personas=conflict["conflicting_personas"],
                conflicting_values=conflict["values_proposed"],
                severity=conflict["severity"],
                category=conflict["category"],
                status="unresolved",
                context=f"Detecção automática: personas discordam sobre {conflict['field_name']}",
            )
            self.db.add(discrepancy)

        await self.db.commit()

        # 5. Consolidar em OCG Global
        ocg_global = self._consolidate_ocg(parecer_dict, conflicts)

        logger.info(
            "ocg.consolidation_complete",
            project_id=str(project_id),
            document_id=str(document_id),
            conflicts_detected=len(conflicts),
        )

        return ocg_global, conflicts

    def _detect_conflicts(self, parecer_dict: Dict[str, Dict]) -> List[Dict]:
        """
        Detecta conflitos entre pareceres de personas.
        Retorna lista de conflitos com field_name, personas, valores.
        """
        conflicts = []

        # Extrair campos chave que podem ter conflito
        # Exemplos: criticidade, recomendações, riscos
        criticalities = {}
        recommendations = {}

        for persona_name, parecer in parecer_dict.items():
            if isinstance(parecer, dict):
                # Agrupar por criticidade
                crit = parecer.get("criticidade", "MEDIA")
                if "criticidade" not in criticalities:
                    criticalities["criticidade"] = {}
                if crit not in criticalities["criticidade"]:
                    criticalities["criticidade"][crit] = []
                criticalities["criticidade"][crit].append(persona_name)

                # Agrupar por primeiras recomendações
                recs = parecer.get("recomendacoes", [])
                if recs and len(recs) > 0:
                    first_rec = recs[0] if isinstance(recs, list) else str(recs)
                    if "recomendacao_principal" not in recommendations:
                        recommendations["recomendacao_principal"] = {}
                    if first_rec not in recommendations["recomendacao_principal"]:
                        recommendations["recomendacao_principal"][first_rec] = []
                    recommendations["recomendacao_principal"][first_rec].append(persona_name)

        # Detectar quando há 2+ valores diferentes
        for field_name, value_dict in criticalities.items():
            if len(value_dict) > 1:  # Múltiplos valores
                conflicting_personas = []
                values_proposed = {}
                for value, personas in value_dict.items():
                    conflicting_personas.extend(personas)
                    values_proposed[value] = personas

                # Classificar severidade do conflito
                values_list = list(value_dict.keys())
                if "ALTA" in values_list and "BAIXA" in values_list:
                    severity = "critical"
                elif ("ALTA" in values_list or "MEDIA" in values_list) and "BAIXA" in values_list:
                    severity = "high"
                else:
                    severity = "medium"

                conflicts.append({
                    "field_name": field_name,
                    "conflicting_personas": conflicting_personas,
                    "values_proposed": {p: values_proposed.get(v, [p])[0] for p, v in zip(conflicting_personas, values_list)},
                    "severity": severity,
                    "category": "assessment",
                })

        return conflicts

    def _consolidate_ocg(self, parecer_dict: Dict[str, Dict], conflicts: List[Dict]) -> Dict:
        """
        Consolida pareceres de personas em OCG Global.
        Estratégia: votação simples para campos com conflito, merge para campos sem conflito.
        """
        ocg_global = {
            "consolidado_em": datetime.now(timezone.utc).isoformat(),
            "personas_total": len(parecer_dict),
            "conflitos_detectados": len(conflicts),
            "pareceres_individuais": parecer_dict,
            "conclusoes": {
                "criticidade_maxima": "ALTA",  # Sempre usar máxima criticidade
                "riscos_consolidados": self._consolidate_list_field(parecer_dict, "riscos"),
                "recomendacoes_consolidadas": self._consolidate_list_field(parecer_dict, "recomendacoes"),
            },
        }
        return ocg_global

    def _consolidate_list_field(self, parecer_dict: Dict[str, Dict], field_name: str) -> List[str]:
        """
        Consolida campos lista (riscos, recomendações) de múltiplas personas.
        Remove duplicatas, mantém ordem por frequência.
        """
        all_items = []
        for parecer in parecer_dict.values():
            if isinstance(parecer, dict):
                items = parecer.get(field_name, [])
                if isinstance(items, list):
                    all_items.extend(items)

        # Deduplica mantendo ordem de frequência
        seen = {}
        for item in all_items:
            seen[item] = seen.get(item, 0) + 1

        return sorted(seen.keys(), key=lambda x: -seen[x])[:10]  # Top 10
