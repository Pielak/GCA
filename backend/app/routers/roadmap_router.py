"""
Roadmap Router — Endpoint de roadmap dinâmico do projeto.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import structlog

from app.db.database import get_db
from app.services.roadmap_service import RoadmapService
from app.middleware.auth import get_current_user_from_token
from app.dependencies.require_action import require_action

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["roadmap"])


@router.get("/projects/{project_id}/roadmap")
async def get_roadmap(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Roadmap dinâmico — módulos agrupados por fase e prioridade."""
    service = RoadmapService(db)
    return await service.get_roadmap(project_id)


# ============================================================================
# Backlog Vivo (spec seção 7.2)
# ============================================================================

@router.get("/projects/{project_id}/backlog")
async def get_backlog(
    project_id: UUID,
    category: str = None,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Lista o backlog vivo do projeto, opcionalmente filtrado por categoria."""
    from app.services.backlog_service import BacklogService
    service = BacklogService(db)
    items = await service.list_backlog(project_id, category=category)
    return {"items": items, "count": len(items)}


@router.post("/projects/{project_id}/backlog/regenerate")
async def regenerate_backlog(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Regenera o backlog a partir do OCG atual (spec seção 7.2).
    Remove itens auto-gerados e recria. Itens manuais são preservados."""
    from app.services.backlog_service import BacklogService
    from app.services.audit_service import AuditService, AuditEvents

    service = BacklogService(db)
    result = await service.regenerate_from_ocg(project_id)

    # Registrar evento
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEvents.BACKLOG_REGENERATED,
        resource_type="backlog",
        actor_id=current_user_id,
        resource_id=project_id,
        details=result,
    )
    await db.commit()

    return result


@router.post("/projects/{project_id}/backlog/generate")
async def generate_backlog(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Gera backlog inteligente: OCG + Arguider module_candidates + verificacao de artefatos."""
    from app.services.backlog_service import BacklogService
    from app.services.artifact_verification_service import ArtifactVerificationService

    service = BacklogService(db)

    # 1. Regenerar do OCG
    ocg_result = await service.regenerate_from_ocg(project_id)

    # 2. Ingerir module_candidates do Arguider
    arguider_result = await service.ingest_module_candidates(project_id)

    # 3. Verificar artefatos de todos os itens
    verifier = ArtifactVerificationService()
    verifications = await verifier.verify_all_items(db, project_id)

    return {
        "ocg_items": ocg_result.get("total", 0),
        "arguider_items": arguider_result.get("created", 0),
        "verified": len(verifications),
        "ready": sum(1 for v in verifications if v["status"] == "ready"),
        "blocked": sum(1 for v in verifications if v["status"] == "blocked"),
    }


@router.post("/projects/{project_id}/backlog/verify")
async def verify_backlog_artifacts(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Reverifica artefatos de todos os itens pendentes/bloqueados."""
    from app.services.artifact_verification_service import ArtifactVerificationService

    verifier = ArtifactVerificationService()
    results = await verifier.verify_all_items(db, project_id)
    return {
        "verified": len(results),
        "ready": sum(1 for v in results if v["status"] == "ready"),
        "blocked": sum(1 for v in results if v["status"] == "blocked"),
        "items": results,
    }


@router.post("/projects/{project_id}/backlog/ingest-arguider")
async def ingest_arguider_candidates(
    project_id: UUID,
    permissions: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Converte ModuleCandidates do Arguider em itens do backlog."""
    from app.services.backlog_service import BacklogService

    service = BacklogService(db)
    result = await service.ingest_module_candidates(project_id)
    return result


@router.post("/projects/{project_id}/backlog/{item_id}/generate-code")
async def generate_code_from_backlog(
    project_id: UUID,
    item_id: UUID,
    permissions: dict = Depends(require_action("code:write")),
    db: AsyncSession = Depends(get_db),
):
    """Gera codigo para um item do backlog usando LLM com contexto OCG."""
    from app.models.base import BacklogItem, OCG, ProjectSettings
    from app.services.vault_service import VaultService
    from app.services.llm_service import LLMServiceFactory, LLMProvider
    import json

    # Buscar item
    item = await db.get(BacklogItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Item nao encontrado")

    if item.status not in ("ready", "pending"):
        raise HTTPException(status_code=400, detail=f"Item com status '{item.status}' nao pode gerar codigo. Precisa estar 'ready' ou 'pending'.")

    # Buscar OCG
    ocg_result = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc())
    )
    ocg = ocg_result.scalars().first()
    ocg_data = json.loads(ocg.ocg_data) if ocg and ocg.ocg_data else {}

    # Buscar config LLM do projeto
    settings_result = await db.execute(
        select(ProjectSettings).where(
            ProjectSettings.project_id == project_id,
            ProjectSettings.setting_type == "llm",
        )
    )
    llm_settings = settings_result.scalar_one_or_none()
    if not llm_settings:
        raise HTTPException(status_code=400, detail="Chaves de IA nao configuradas para este projeto")

    llm_config = json.loads(llm_settings.settings_json)
    provider = llm_config.get("provider", "deepseek")
    model = llm_config.get("model_preference", "deepseek-chat")

    # Buscar API key do vault
    vault = VaultService()
    api_key = await vault.get_secret(db, project_id, "llm_api_key", provider)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"API key nao encontrada para provider {provider}")

    # Construir prompt
    stack = ocg_data.get("STACK_RECOMMENDATION", {})
    compliance = json.loads(item.compliance_iso27001) if item.compliance_iso27001 else []
    artifacts = json.loads(item.present_artifacts) if item.present_artifacts else []

    prompt = f"""Voce e um desenvolvedor senior gerando codigo para o modulo: {item.title}

## Descricao
{item.description or 'Sem descricao detalhada'}

## Tipo de Modulo
{item.module_type or 'service'}

## Stack do Projeto
{json.dumps(stack, indent=2, ensure_ascii=False)}

## Artefatos Disponiveis
{json.dumps(artifacts, indent=2, ensure_ascii=False)}

## Compliance ISO 27001
{chr(10).join(f'- {c}' for c in compliance)}

## Requisitos
- Codigo limpo, bem documentado, seguindo boas praticas
- Testes unitarios incluidos
- Tratamento de erros adequado
- Logging estruturado
- Conformidade com ISO 27001 e LGPD quando aplicavel

Gere o codigo completo do modulo, pronto para commit."""

    # Chamar LLM
    try:
        provider_enum = LLMProvider(provider.upper()) if provider.upper() in LLMProvider.__members__ else LLMProvider.DEEPSEEK
        client = LLMServiceFactory.create(provider_enum, api_key)
        generated_code = await client.generate(
            prompt=prompt,
            max_tokens=4096,
            temperature=0.3,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao chamar LLM: {str(e)}")

    # Atualizar item
    item.status = "generating"
    await db.commit()

    return {
        "item_id": str(item.id),
        "title": item.title,
        "module_type": item.module_type,
        "generated_code": generated_code,
        "provider": provider,
        "model": model,
        "status": "generating",
    }
