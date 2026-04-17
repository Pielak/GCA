"""
AI Key Resolver — resolução compartimentalizada de API keys.

Fonte soberana: `GCA_CANONICAL_CONTRACT.md §6` (Política canônica de IA).

DUAS CAMADAS:
  1. **Camada GCA (Admin):** chaves globais do admin da instância.
     Uso exclusivo: pipeline de pré-OCG (avaliação do questionário antes da
     aprovação do projeto, quando ainda não há GP dono da chave).
     Única consumidora legítima: `agent_service.py` (8 agentes OCG).
  2. **Camada Projeto (GP):** chaves por projeto via vault criptografado.
     Uso: Arguidor, CodeGen, QA, LiveDocs e qualquer operação pós-aprovação.

REGRAS DURAS (contrato §6.4):
- Nunca misturar chave global do admin com chave de projeto sem regra explícita.
- Se o projeto não configurou chave, falhar explicitamente em tarefas de alta
  criticidade (contrato §6.2). Não cair silenciosamente em chave de outro
  provedor ou na chave global.
- Cada chamada de IA deve registrar provedor, modelo, motivo e criticidade.

CRITICIDADE DA TAREFA (contrato §6.2):
- **baixa:** classificação simples, extração, sumarização curta, normalização,
  pré-processamento, enriquecimento leve. Pode usar modelo local/Ollama.
- **média:** perguntas dirigidas preliminares, propostas iniciais de backlog,
  pré-análise de artefatos, insumos para OCG/Gatekeeper/Arguidor. Local ou
  remoto com validação.
- **alta:** consolidação final do OCG, arbitragem de conflitos, decisões
  arquiteturais, compliance/segurança críticos, liberação/bloqueio de pipeline,
  backlog oficial, codegen crítico, síntese executiva. **Modelo premium
  obrigatório.**

O GP configura chaves via `/settings/llm` do projeto.
O Admin configura chaves globais via `/admin/gca/ai-providers`.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class AIKeyResolver:
    """Resolve API key conforme a camada de uso."""

    @staticmethod
    async def get_gca_key(provider: str = None) -> Optional[str]:
        """Camada GCA Admin — chave global para OCG pipeline.
        Usada APENAS em: agent_service.py (8 agentes OCG), ocg_service.py
        """
        provider = provider or settings.DEFAULT_AI_PROVIDER

        # Primeiro: chaves configuradas pelo admin (system_settings via runtime)
        key_attr = f"{provider.upper()}_API_KEY"
        key = getattr(settings, key_attr, None)

        if key:
            logger.debug("ai_key.gca_resolved", provider=provider, source="global_config")
        else:
            logger.warning("ai_key.gca_not_found", provider=provider)

        return key

    @staticmethod
    async def get_project_key(
        db: AsyncSession,
        project_id: UUID,
        provider: str = None,
    ) -> Optional[str]:
        """Camada Projeto — chave do GP via vault (criptografada).
        Usada em: arguider_service, code_generation_service, livedocs_service, etc.
        Fallback: NÃO usa chave global. Retorna None se GP não configurou.
        """
        from app.services.vault_service import VaultService

        provider = provider or "anthropic"

        try:
            vault = VaultService()
            key = await vault.get_secret(db, project_id, "llm_api_key", provider)

            if key:
                logger.debug("ai_key.project_resolved",
                            project_id=str(project_id),
                            provider=provider,
                            source="vault")
                return key

            # Tentar provider alternativo APENAS se compatível com o solicitado
            from sqlalchemy import select, text
            result = await db.execute(
                text("""
                    SELECT settings_json FROM project_settings
                    WHERE project_id = :pid AND setting_type = 'llm'
                """),
                {"pid": str(project_id)},
            )
            row = result.fetchone()
            if row and row[0]:
                import json
                llm_config = json.loads(row[0])
                alt_provider = llm_config.get("provider")
                # Só retorna key alternativa se for do MESMO provider solicitado
                if alt_provider and alt_provider == provider:
                    key = await vault.get_secret(db, project_id, "llm_api_key", alt_provider)
                    if key:
                        logger.debug("ai_key.project_resolved_alt",
                                    project_id=str(project_id),
                                    provider=alt_provider,
                                    source="vault")
                        return key

            logger.warning("ai_key.project_not_configured",
                          project_id=str(project_id),
                          provider=provider,
                          message="GP deve configurar chave IA nas Settings do projeto")
            return None

        except Exception as e:
            logger.error("ai_key.project_resolve_error",
                        project_id=str(project_id),
                        error=str(e))
            return None

    @staticmethod
    async def get_project_key_or_fail(
        db: AsyncSession,
        project_id: UUID,
        provider: str = None,
    ) -> str:
        """Como get_project_key mas levanta exceção se não configurada."""
        key = await AIKeyResolver.get_project_key(db, project_id, provider)
        if not key:
            raise ValueError(
                f"Chave de IA não configurada para este projeto. "
                f"O Gerente de Projeto deve configurar em Settings > Provedor IA."
            )
        return key
