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
    async def _resolve_project_provider(
        db: AsyncSession,
        project_id: UUID,
    ) -> Optional[str]:
        """Lê o provedor configurado pelo GP em `project_settings` (setting_type='llm').

        Retorna a string do provedor (anthropic|openai|gemini|deepseek|grok|ollama|...)
        ou None se o GP ainda não configurou. Não faz fallback — chamador decide.
        """
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT settings_json FROM project_settings
                WHERE project_id = :pid AND setting_type = 'llm'
            """),
            {"pid": str(project_id)},
        )
        row = result.fetchone()
        if not row or not row[0]:
            return None
        import json
        try:
            data = json.loads(row[0])
        except (ValueError, TypeError):
            return None

        # Formato novo multi-provider: {providers:[...], default_provider:"..."}
        # Preferir o default_provider salvo; se ausente, o primeiro marcado
        # is_default; se ninguém, o primeiro da lista.
        if isinstance(data.get("providers"), list):
            if data.get("default_provider"):
                return data["default_provider"]
            for p in data["providers"]:
                if p.get("is_default"):
                    return p.get("provider")
            if data["providers"]:
                return data["providers"][0].get("provider")
            return None

        # Formato legado single-provider.
        return data.get("provider")

    @staticmethod
    async def get_project_key(
        db: AsyncSession,
        project_id: UUID,
        provider: str = None,
    ) -> Optional[str]:
        """Camada Projeto — chave do GP via vault (criptografada).

        Usada em: arguider_service, code_generation_service, livedocs_service etc.

        - Se `provider` for passado explicitamente: tenta retornar a chave desse
          provedor específico (mantido para casos onde o caller precisa de um
          provedor determinado).
        - Se `provider=None`: **lê o provedor configurado pelo GP** em
          `project_settings` e retorna a chave correspondente. Sem hardcode
          para "anthropic".

        Fallback: NUNCA usa chave global do admin (contrato §6.4). Retorna
        None se o GP não configurou provedor ou chave.
        """
        from app.services.vault_service import VaultService

        try:
            # Descobrir o provedor a usar
            if provider is None:
                provider = await AIKeyResolver._resolve_project_provider(db, project_id)
                if not provider:
                    logger.warning(
                        "ai_key.project_not_configured",
                        project_id=str(project_id),
                        message="GP não configurou provedor de IA em Settings > LLM",
                    )
                    return None

            vault = VaultService()
            key = await vault.get_secret(db, project_id, "llm_api_key", provider)

            if key:
                logger.debug(
                    "ai_key.project_resolved",
                    project_id=str(project_id),
                    provider=provider,
                    source="vault",
                )
                return key

            logger.warning(
                "ai_key.project_key_missing",
                project_id=str(project_id),
                provider=provider,
                message="GP configurou provedor mas chave ausente no vault",
            )
            return None

        except Exception as e:
            logger.error(
                "ai_key.project_resolve_error",
                project_id=str(project_id),
                error=str(e),
            )
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
