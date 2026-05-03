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
    async def resolve_project_provider_chain(
        db: AsyncSession,
        project_id: UUID,
        include_api_key: bool = False,
    ) -> list[dict]:
        """DT-064 — Retorna a cadeia de providers configurados no projeto
        em ordem de preferência (default primeiro, depois os outros
        validados mais recentemente). Cada entrada tem:

            {"provider": "openai", "model": "...", "base_url": "..."|None, "api_key": "..."|None}

        Se include_api_key=True (padrão False para segurança), também retorna
        a chave do vault para cada provider. Usado internamente por ingestion_router
        para passar ao n8n com o payload criptografado via HMAC.

        Uso: caller tenta cada provider em sequência quando encontra
        erro transiente (rate limit, quota esgotada, 503). Implementa
        fallback automático de IA que antes exigia intervenção manual.
        """
        from sqlalchemy import text
        import json
        from app.services.vault_service import VaultService

        result = await db.execute(
            text(
                "SELECT settings_json FROM project_settings "
                "WHERE project_id=:pid AND setting_type='llm'"
            ),
            {"pid": str(project_id)},
        )
        row = result.fetchone()
        if not row or not row[0]:
            return []
        try:
            data = json.loads(row[0])
        except (ValueError, TypeError):
            return []

        providers = data.get("providers") or []
        if not providers:
            # Formato legado single-provider
            if data.get("provider"):
                chain_item = {
                    "provider": data["provider"],
                    "model": data.get("model_preference"),
                    "base_url": data.get("base_url"),
                }
                if include_api_key:
                    vault = VaultService()
                    api_key = await vault.get_secret(db, project_id, "llm_api_key", data["provider"])
                    chain_item["api_key"] = api_key or ""
                return [chain_item]
            return []

        # Default primeiro, depois os demais. Dentro de cada grupo, os
        # mais recentemente validados com sucesso aparecem antes.
        default_name = data.get("default_provider")
        if not default_name:
            for p in providers:
                if p.get("is_default"):
                    default_name = p.get("provider")
                    break

        def sort_key(p):
            # Tuple: (not is_default, not last_validation_ok, -last_validated_at)
            is_def = p.get("provider") == default_name
            ok = bool(p.get("last_validation_ok"))
            ts = p.get("last_validated_at") or ""
            return (0 if is_def else 1, 0 if ok else 1, "9" + ts if ok else ts)

        chain = sorted(providers, key=sort_key)
        result_chain = []
        vault = VaultService() if include_api_key else None

        for p in chain:
            if not p.get("provider"):
                continue
            chain_item = {
                "provider": p.get("provider"),
                "model": p.get("model"),
                "base_url": p.get("base_url"),
            }
            if include_api_key and vault:
                api_key = await vault.get_secret(db, project_id, "llm_api_key", p.get("provider"))
                chain_item["api_key"] = api_key or ""
            result_chain.append(chain_item)

        return result_chain

    @staticmethod
    def should_fallback_to_next_provider(error_message: str) -> bool:
        """DT-064 — Decide se um erro ao falar com provider IA justifica
        tentar o próximo da cadeia (tipicamente, premium remoto → local).

        Lógica invertida (ampla por default): QUALQUER falha de
        comunicação/infraestrutura cai pro fallback. Só NÃO faz fallback
        quando é erro específico de configuração do provider atual que o
        fallback não resolveria:

          - **401/403**: chave inválida. Problema de configuração.
            Admin precisa corrigir, não tem como outro provider ajudar
            com a mesma chave errada (cada provider tem chave própria, mas
            se a cadeia inteira foi validada antes, 401 no primeiro
            provider indica problema específico dele — outros podem estar
            OK. Mas o fallback ainda faz sentido pra que, se os outros
            tiverem chave boa, o pipeline continue).
          - **400 com 'malformed'/'invalid model'/'schema'**: prompt mal
            construído. Falha do código do GCA, não do provider — não
            adianta tentar outro.

        Para tudo o mais — rate limit, quota, timeout, 5xx, erro de DNS,
        conexão recusada, EOF, SSL, socket — faz fallback. A heurística
        privilegia UX do usuário final: mesmo em erros ambíguos, tentar
        o provider seguinte é melhor que quebrar.
        """
        if not error_message:
            # Sem erro não faz sentido fazer fallback
            return False
        msg = error_message.lower()

        # Markers que indicam erro de parâmetro/prompt — caller bugado;
        # outro provider não resolve.
        no_fallback_markers = [
            "invalid model",
            "model not found",
            "unknown model",
            "schema validation",
            "malformed request",
            "invalid request body",
            "invalid argument",
            "parameter out of range",
        ]
        if any(m in msg for m in no_fallback_markers):
            return False

        # Erro de autenticação EM UM provider específico — o próximo
        # provider da cadeia tem outra chave, pode funcionar. Então
        # CAI NO FALLBACK. (Exceção: se todos os providers da cadeia
        # derem 401, o loop itera até esgotá-los e o erro final sobe
        # pro user, que é o comportamento correto.)
        # Portanto: 401/403 caem no fallback sim.

        # Default: fallback pra qualquer outra coisa.
        return True

    @staticmethod
    def is_transient_ai_error(error_message: str) -> bool:
        """Mantido para compatibilidade com callers antigos da DT-064
        inicial. Agora delega para should_fallback_to_next_provider que
        implementa lógica mais ampla."""
        return AIKeyResolver.should_fallback_to_next_provider(error_message)

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
    async def get_project_base_url(
        db: AsyncSession,
        project_id: UUID,
        provider: str,
    ) -> Optional[str]:
        """DT-023: lê `base_url` do provider record no settings_json.

        Apenas Ollama persiste base_url (ver settings_router); demais
        retornam None aqui. Caller usa pra montar o endpoint HTTP do
        Ollama do GP (ex: http://host.docker.internal:11434).
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
        import json as _json
        try:
            data = _json.loads(row[0])
        except (ValueError, TypeError):
            return None
        if isinstance(data.get("providers"), list):
            for p in data["providers"]:
                if p.get("provider") == provider:
                    bu = p.get("base_url")
                    if isinstance(bu, str) and bu.strip():
                        return bu.strip().rstrip("/")
                    return None
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
