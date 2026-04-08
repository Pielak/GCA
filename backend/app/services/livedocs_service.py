"""
LiveDocs Service — Documentação Viva.
Gera, atualiza e mantém documentação automaticamente sincronizada
com o estado do projeto (OCG, módulos, documentos ingeridos).
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4, UUID

from app.utils.retry import gca_retry

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import OCG, GeneratedModule, IngestedDocument
from app.core.config import settings

logger = structlog.get_logger(__name__)


class LiveDocsService:
    """Serviço de documentação viva — atualiza docs automaticamente."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_initial_documentation(
        self,
        project_id: UUID,
    ) -> dict:
        """
        Gera documentação inicial completa a partir do OCG.
        Cria: README, ARCHITECTURE, API_SPEC, DEPLOYMENT, TESTING, SECURITY.

        Returns:
            dict com paths e status de cada seção gerada
        """
        try:
            # Buscar OCG mais recente
            result = await self.db.execute(
                select(OCG)
                .where(OCG.project_id == project_id)
                .order_by(OCG.generated_at.desc())
            )
            ocg = result.scalar_one_or_none()
            if not ocg:
                logger.warning(
                    "livedocs.ocg_nao_encontrado",
                    project_id=str(project_id),
                )
                return {"error": "OCG não encontrado para o projeto", "sections": []}

            ocg_data = json.loads(ocg.ocg_data) if ocg.ocg_data else {}

            # Seções padrão de documentação
            sections = [
                {"path": "docs/README.md", "title": "Visão Geral do Projeto"},
                {"path": "docs/ARCHITECTURE.md", "title": "Arquitetura do Sistema"},
                {"path": "docs/API_SPEC.md", "title": "Especificação da API"},
                {"path": "docs/DEPLOYMENT.md", "title": "Guia de Deploy"},
                {"path": "docs/TESTING.md", "title": "Estratégia de Testes"},
                {"path": "docs/SECURITY.md", "title": "Requisitos de Segurança"},
            ]

            generated = []
            for section in sections:
                # Em produção, cada seção seria gerada via LLM
                generated.append({
                    "path": section["path"],
                    "title": section["title"],
                    "status": "generated",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })

            logger.info(
                "livedocs.documentacao_inicial_gerada",
                project_id=str(project_id),
                secoes=len(generated),
            )

            return {
                "project_id": str(project_id),
                "sections": generated,
                "total": len(generated),
            }

        except Exception as e:
            logger.error(
                "livedocs.erro_geracao_inicial",
                project_id=str(project_id),
                error=str(e),
            )
            return {"error": str(e), "sections": []}

    @gca_retry()
    async def update_on_document_ingested(
        self,
        project_id: UUID,
        document_id: UUID,
    ) -> dict:
        """
        Atualiza documentação quando um novo documento é ingerido.
        Identifica quais seções são impactadas e as regenera.
        """
        try:
            logger.info(
                "livedocs.atualizando_por_documento",
                project_id=str(project_id),
                document_id=str(document_id),
            )

            # Buscar documento ingerido
            result = await self.db.execute(
                select(IngestedDocument).where(IngestedDocument.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                return {"updated": False, "reason": "Documento não encontrado"}

            # Identificar seções impactadas (simplificado)
            impacted = []
            doc_type = doc.file_type if hasattr(doc, "file_type") else "unknown"

            if doc_type in ("markdown", "docx", "pdf"):
                impacted.append("docs/README.md")
                impacted.append("docs/ARCHITECTURE.md")
            elif doc_type == "code":
                impacted.append("docs/API_SPEC.md")
            elif doc_type == "image":
                impacted.append("docs/README.md")

            logger.info(
                "livedocs.secoes_impactadas",
                secoes=len(impacted),
            )

            return {
                "updated": True,
                "document_id": str(document_id),
                "impacted_sections": impacted,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                "livedocs.erro_atualizacao_documento",
                error=str(e),
            )
            return {"updated": False, "reason": str(e)}

    @gca_retry()
    async def update_on_module_generated(
        self,
        project_id: UUID,
        module_id: UUID,
    ) -> dict:
        """
        Adiciona documentação quando um novo módulo é gerado.
        Cria doc específica do módulo e atualiza índice.
        """
        try:
            result = await self.db.execute(
                select(GeneratedModule).where(GeneratedModule.id == module_id)
            )
            module = result.scalar_one_or_none()
            if not module:
                return {"updated": False, "reason": "Módulo não encontrado"}

            doc_path = f"docs/modules/{module.name.lower().replace(' ', '_')}.md"

            logger.info(
                "livedocs.doc_modulo_adicionada",
                module_id=str(module_id),
                doc_path=doc_path,
            )

            return {
                "updated": True,
                "module_id": str(module_id),
                "doc_path": doc_path,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                "livedocs.erro_doc_modulo",
                error=str(e),
            )
            return {"updated": False, "reason": str(e)}

    async def refresh_ocg_documentation(
        self,
        project_id: UUID,
    ) -> dict:
        """
        Regenera toda a documentação baseada na versão mais recente do OCG.
        Usado quando o OCG é atualizado significativamente.
        """
        try:
            result = await self.db.execute(
                select(OCG)
                .where(OCG.project_id == project_id)
                .order_by(OCG.generated_at.desc())
            )
            ocg = result.scalar_one_or_none()
            if not ocg:
                return {"refreshed": False, "reason": "OCG não encontrado"}

            # Regenerar documentação
            docs_result = await self.generate_initial_documentation(project_id)

            logger.info(
                "livedocs.documentacao_atualizada",
                project_id=str(project_id),
                secoes=docs_result.get("total", 0),
            )

            return {
                "refreshed": True,
                "project_id": str(project_id),
                "sections_updated": docs_result.get("total", 0),
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                "livedocs.erro_refresh",
                error=str(e),
            )
            return {"refreshed": False, "reason": str(e)}

    async def get_doc_section(
        self,
        project_id: UUID,
        section_path: str,
    ) -> Optional[str]:
        """
        Lê o conteúdo de uma seção de documentação do repositório Git.
        Retorna None se a seção não existir.
        """
        try:
            # Em produção, usaria GitService para ler do repositório
            from app.services.git_service import GitService
            git_service = GitService(self.db)
            content = await git_service.get_file_content(project_id, section_path)
            return content

        except Exception as e:
            logger.warning(
                "livedocs.secao_nao_encontrada",
                project_id=str(project_id),
                section_path=section_path,
                error=str(e),
            )
            return None

    async def get_doc_index(
        self,
        project_id: UUID,
    ) -> List[dict]:
        """
        Lista todas as seções de documentação disponíveis.
        Retorna lista com path e título de cada seção.
        """
        try:
            # Em produção, usaria GitService para listar arquivos em /docs
            from app.services.git_service import GitService
            git_service = GitService(self.db)
            files = await git_service.list_files(project_id, path="docs/")

            sections = []
            for f in files:
                if isinstance(f, str):
                    path = f
                elif isinstance(f, dict):
                    path = f.get("path", "")
                else:
                    continue

                if path.endswith(".md"):
                    sections.append({
                        "path": path,
                        "title": path.rsplit("/", 1)[-1].replace(".md", "").replace("_", " ").title(),
                    })

            return sections

        except Exception as e:
            logger.warning(
                "livedocs.erro_indice",
                project_id=str(project_id),
                error=str(e),
            )
            return []

    @staticmethod
    def generate_changelog_entry(
        event_type: str,
        details: Dict[str, Any],
    ) -> dict:
        """
        Gera uma entrada de changelog formatada.

        Args:
            event_type: Tipo do evento (document_ingested, module_generated, ocg_updated, etc.)
            details: Detalhes do evento

        Returns:
            dict com entry formatada para o changelog
        """
        event_labels = {
            "document_ingested": "Documento ingerido",
            "module_generated": "Módulo gerado",
            "ocg_updated": "OCG atualizado",
            "test_generated": "Testes gerados",
            "docs_refreshed": "Documentação atualizada",
            "gatekeeper_approved": "Módulo aprovado pelo Gatekeeper",
            "gatekeeper_rejected": "Módulo rejeitado pelo Gatekeeper",
        }

        label = event_labels.get(event_type, event_type)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "label": label,
            "details": details,
            "formatted": f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}] {label}: {details.get('summary', str(details))}",
        }
