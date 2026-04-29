"""
OCG Consolidation Service

Consolida as 7 análises individuais (OCG Individual) em uma única análise global (OCG Global).
Detecta consenso, conflitos e aplica votação para campos divergentes.

Estratégia:
1. Buscar todas as 7 OCG Individual para um documento
2. Extrair campos comuns e detectar consenso
3. Para campos divergentes: contar frequências e aplicar votação
4. Armazenar resultado em OCG Global com metadados de consolidação
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import structlog
import json
from collections import Counter
from typing import Dict, List, Any

from app.models.base import OCGIndividual, OCGGlobal, IngestedDocument

logger = structlog.get_logger(__name__)


class OCGConsolidationService:
    """Serviço de consolidação de OCG"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def consolidate_document(
        self,
        project_id: UUID,
        document_id: UUID,
    ) -> OCGGlobal | None:
        """
        Consolida todas as análises de um documento em OCG Global.

        Retorna OCGGlobal criado ou None se falhar.
        """
        try:
            # 1. Buscar todas as OCG Individual
            ocg_individuals = await self.db.scalars(
                select(OCGIndividual).where(
                    (OCGIndividual.project_id == project_id) &
                    (OCGIndividual.document_id == document_id)
                )
            )
            individuals = ocg_individuals.all()

            if not individuals:
                logger.warning(
                    "ocg_consolidation.no_analyses",
                    project_id=str(project_id),
                    document_id=str(document_id),
                )
                return None

            if len(individuals) != 7:
                logger.warning(
                    "ocg_consolidation.incomplete_analyses",
                    project_id=str(project_id),
                    document_id=str(document_id),
                    count=len(individuals),
                )

            # 2. Detectar consenso e conflitos
            consensus_fields, conflicting_fields, voting_results = self._analyze_pareceres(individuals)

            # 3. Montar parecer consolidado
            consolidated = self._merge_pareceres(
                individuals,
                consensus_fields,
                conflicting_fields,
                voting_results,
            )

            # 4. Armazenar OCG Global
            ocg_global = OCGGlobal(
                project_id=project_id,
                document_id=document_id,
                parecer_consolidated=consolidated,
                consensus_fields=consensus_fields,
                conflicting_fields=conflicting_fields,
                voting_results=voting_results,
                consolidated_at=datetime.now(timezone.utc),
            )
            self.db.add(ocg_global)
            await self.db.commit()
            await self.db.refresh(ocg_global)

            logger.info(
                "ocg_consolidation.complete",
                project_id=str(project_id),
                document_id=str(document_id),
                consensus_count=len(consensus_fields),
                conflicting_count=len(conflicting_fields),
            )

            return ocg_global

        except Exception as e:
            logger.error(
                "ocg_consolidation.failed",
                project_id=str(project_id),
                document_id=str(document_id),
                error=str(e),
            )
            await self.db.rollback()
            return None

    def _analyze_pareceres(self, individuals: List[OCGIndividual]) -> tuple:
        """
        Analisa pareceres para detectar consenso e conflitos.

        Retorna: (consensus_fields, conflicting_fields, voting_results)
        """
        consensus_fields = []
        conflicting_fields = {}
        voting_results = {}

        # Coletar todos os campos únicos
        all_keys = set()
        for ocg in individuals:
            if ocg.parecer:
                all_keys.update(ocg.parecer.keys())

        # Analisar cada campo
        for field in all_keys:
            values = [ocg.parecer.get(field) if ocg.parecer else None for ocg in individuals]

            # Converter para string para comparação (lidar com arrays e objetos)
            str_values = [json.dumps(v, sort_keys=True) if v else "null" for v in values]

            # Contar frequências
            freq = Counter(str_values)

            if len(freq) == 1:
                # Consenso: todos têm o mesmo valor
                consensus_fields.append(field)
            else:
                # Conflito: valores diferentes
                conflicting_fields[field] = {
                    ocg.persona_name: ocg.parecer.get(field) if ocg.parecer else None
                    for ocg in individuals
                }

                # Votação: qual valor apareceu mais
                voting_results[field] = {
                    v: count for v, count in sorted(freq.items(), key=lambda x: x[1], reverse=True)
                }

        return consensus_fields, conflicting_fields, voting_results

    def _merge_pareceres(
        self,
        individuals: List[OCGIndividual],
        consensus_fields: List[str],
        conflicting_fields: Dict,
        voting_results: Dict,
    ) -> Dict[str, Any]:
        """
        Mescla as 7 análises em uma única consolidada.

        Estratégia:
        - Campos em consenso: usa o valor unânime
        - Campos em conflito: usa o valor que apareceu mais (votação)
        - Campos adicionais: descrição do conflito
        """
        consolidated = {}

        # Base: tomar do primeiro parecer
        if individuals and individuals[0].parecer:
            consolidated = individuals[0].parecer.copy()

        # Campos em consenso: manter como está
        for field in consensus_fields:
            if field in consolidated:
                continue
            # Buscar valor do consenso
            for ocg in individuals:
                if ocg.parecer and field in ocg.parecer:
                    consolidated[field] = ocg.parecer[field]
                    break

        # Campos em conflito: usar votação
        for field, votes in voting_results.items():
            if votes:
                # Pegar valor mais votado
                most_voted_json = max(votes, key=votes.get)
                try:
                    most_voted = json.loads(most_voted_json)
                except:
                    most_voted = most_voted_json

                consolidated[f"{field}_consolidated"] = most_voted
                consolidated[f"{field}_consensus"] = False
                consolidated[f"{field}_votes"] = {
                    v: count for v, count in votes.items()
                }

        # Metadados de consolidação
        consolidated["_consolidation_metadata"] = {
            "consensus_fields": consensus_fields,
            "conflicting_fields": list(conflicting_fields.keys()),
            "consolidated_at": datetime.now(timezone.utc).isoformat(),
        }

        return consolidated
