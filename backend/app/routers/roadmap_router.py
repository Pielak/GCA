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
from app.dependencies.require_project_setup import require_project_setup_complete

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["roadmap"])


@router.get("/projects/{project_id}/roadmap")
async def get_roadmap(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """Roadmap dinâmico — módulos agrupados por fase e prioridade."""
    service = RoadmapService(db)
    return await service.get_roadmap(project_id)


@router.get("/projects/{project_id}/modules/{module_id}/details")
async def get_module_details(
    project_id: UUID,
    module_id: UUID,
    refresh: bool = False,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.2 — Detalhamento on-demand de um item do Roadmap.

    Retorna `what_it_is`, `prerequisites`, `missing_inputs`,
    `input_examples` e `suggested_template_sections` (insumo para Fase
    9.5.1). Gerado por Ollama do projeto na primeira chamada; cache
    persistido em `module_candidates.details_json`. `?refresh=true`
    força regeneração.

    Falha explícita quando Ollama não configurado — detalhamento é
    baixa criticidade (§6.2) e não justifica fallback pra premium.
    """
    from app.services.module_details_service import get_or_generate_details

    try:
        details = await get_or_generate_details(
            db, project_id, module_id, force_regenerate=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        # Ex: Ollama não configurado — devolve 503 com mensagem
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "module_details.unexpected_error",
            project_id=str(project_id),
            module_id=str(module_id),
            error_type=type(exc).__name__,
            error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar detalhamento ({type(exc).__name__}): {exc!r}",
        )

    return details


@router.put("/projects/{project_id}/modules/{module_id}/external-reference")
async def set_external_reference(
    project_id: UUID,
    module_id: UUID,
    payload: dict,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.2.ext — Define URL de doc externa do item.

    Body: `{"url": "https://..."}` ou `{"url": null}` pra remover.
    Não dispara fetch — só persiste. Use o endpoint `fetch-external`
    pra forçar download. Sem URL, GCA não navega autonomamente.
    """
    from app.models.base import ModuleCandidate as _MC
    from app.services.web_fetch_service import WebFetchError, validate_url

    mc = await db.get(_MC, module_id)
    if not mc or mc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    url_raw = payload.get("url") if isinstance(payload, dict) else None
    if url_raw is None or url_raw == "":
        mc.external_reference = None
        mc.external_reference_content = None
        mc.external_reference_fetched_at = None
        mc.external_reference_fetch_error = None
        await db.commit()
        return {"external_reference": None, "removed": True}

    try:
        canonical = validate_url(url_raw)
    except WebFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    mc.external_reference = canonical
    # Reseta cache — próximo fetch refaz
    mc.external_reference_content = None
    mc.external_reference_fetched_at = None
    mc.external_reference_fetch_error = None
    await db.commit()
    return {"external_reference": canonical, "fetched": False}


@router.post("/projects/{project_id}/modules/{module_id}/fetch-external")
async def fetch_external_reference(
    project_id: UUID,
    module_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.2.ext — Faz fetch da URL declarada e persiste o
    conteúdo extraído. Se URL não está declarada, retorna 400.
    """
    from datetime import datetime, timezone as _tz
    from app.models.base import ModuleCandidate as _MC
    from app.services.web_fetch_service import WebFetchError, fetch_and_extract

    mc = await db.get(_MC, module_id)
    if not mc or mc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    if not mc.external_reference:
        raise HTTPException(
            status_code=400,
            detail="Item não tem external_reference declarada. Defina via PUT antes.",
        )

    try:
        text, meta = await fetch_and_extract(mc.external_reference)
    except WebFetchError as exc:
        mc.external_reference_fetch_error = str(exc)
        mc.external_reference_fetched_at = datetime.now(_tz.utc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    mc.external_reference_content = text
    mc.external_reference_fetched_at = datetime.now(_tz.utc)
    mc.external_reference_fetch_error = None
    await db.commit()
    return {
        "external_reference": mc.external_reference,
        "fetched_at": mc.external_reference_fetched_at.isoformat(),
        "chars": len(text),
        "meta": meta,
    }


@router.get("/projects/{project_id}/roadmap/deploy-plan")
async def get_deploy_plan(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.4 — Plano de deploy sugerido (JSON).

    Ordena `module_candidates` por camada canônica
    (infrastructure → ... → deploy_pipeline) com sort topológico
    de dependencies_inferred (Fase 9.3) dentro de cada camada.
    Itens em ciclo aparecem com `cycle=true` na resposta.
    """
    from app.services.deploy_plan_service import build_deploy_plan
    return await build_deploy_plan(db, project_id)


@router.get("/projects/{project_id}/roadmap/deploy-plan.md")
async def get_deploy_plan_markdown(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.4 — Plano de deploy exportado como Markdown
    (attachment pra GP baixar/imprimir/compartilhar com a equipe)."""
    from fastapi.responses import Response
    from app.services.deploy_plan_service import build_deploy_plan, render_markdown
    from app.models.base import Project

    plan = await build_deploy_plan(db, project_id)

    project = await db.get(Project, project_id)
    project_name = project.name if project else None
    md = render_markdown(plan, project_name=project_name)

    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="gca-deploy-plan-{str(project_id)[:8]}.md"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/projects/{project_id}/modules/{module_id}/evaluate-readiness")
async def evaluate_module_readiness_endpoint(
    project_id: UUID,
    module_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.3 — Disparo manual da orquestração Premium.

    Avalia readiness_status do módulo (ready_for_codegen / partial /
    needs_input / unknown), gaps específicos e dependências inferidas.
    Persiste em `module_candidates`.

    Roda automaticamente após item virar `adicionado` (Fase 9.5.2);
    este endpoint serve pra GP forçar re-avaliação após enriquecer
    o OCG ou o detalhamento do item.

    503 se nenhum provider Premium configurado.
    """
    from app.services.module_orchestration_service import evaluate_module_readiness

    try:
        result = await evaluate_module_readiness(db, project_id, module_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "evaluate_readiness.unexpected_error",
            project_id=str(project_id), module_id=str(module_id),
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Erro: {exc!r}")

    return result


@router.get("/projects/{project_id}/modules/eligible-for-link")
async def list_modules_eligible_for_link(
    project_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.5.2 — Lista módulos do projeto que podem receber
    vínculo de upload (status `sugerido` ou `aguardando_resposta`).

    Frontend usa pra popular dropdown na tela de upload da Ingestão.
    Já vem ordenado por (priority desc, status asc, name) — itens de
    Fase 1 alta prioridade aparecem primeiro.
    """
    from app.models.base import ModuleCandidate as _MC

    rows = await db.execute(
        select(_MC)
        .where(_MC.project_id == project_id)
        .where(_MC.status.in_(["sugerido", "aguardando_resposta"]))
    )
    items = rows.scalars().all()

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    items_sorted = sorted(
        items,
        key=lambda m: (priority_rank.get(m.priority or "medium", 1), m.status, m.name or ""),
    )

    return [
        {
            "id": str(m.id),
            "name": m.name,
            "module_type": m.module_type,
            "priority": m.priority,
            "status": m.status,
            "source": m.source,
        }
        for m in items_sorted
    ]


@router.get("/projects/{project_id}/modules/{module_id}/template.pdf")
async def get_module_template_pdf(
    project_id: UUID,
    module_id: UUID,
    _perm: dict = Depends(require_action("project:view")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.5.1 — Template PDF AcroForm pra GP responder o item.

    Gera PDF com cabeçalho do item, descrição, detalhamento (Fase 9.2)
    e seções com fields editáveis amarelos (lacunas) ou verdes (já
    preenchidos pelo OCG). `module_id` embutido em hidden field +
    metadata pra detecção no upload (Fase 9.5.2).

    Se o item ainda não tem `details_json`, gera on-demand via Ollama
    do projeto antes de renderizar (custo: 1 chamada local). Sem
    Ollama configurado, falha 503.
    """
    from fastapi.responses import Response
    from app.services.template_pdf_service import generate_template_pdf

    try:
        pdf_bytes = await generate_template_pdf(db, project_id, module_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        import traceback
        logger.warning(
            "module_template_pdf.unexpected_error",
            project_id=str(project_id), module_id=str(module_id),
            error_type=type(exc).__name__, error=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar template ({type(exc).__name__}): {exc!r}",
        )

    safe_id = str(module_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="gca-template-{safe_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/projects/{project_id}/roadmap/foundation/sync")
async def sync_roadmap_foundation(
    project_id: UUID,
    _perm: dict = Depends(require_action("backlog:manage")),
    db: AsyncSession = Depends(get_db),
):
    """MVP 9 Fase 9.1.1 — Sincroniza Fase 1 (Fundação) a partir do OCG.

    Determinístico (não usa LLM): lê `STACK_RECOMMENDATION`,
    `ARCHITECTURE_OVERVIEW` e `PROJECT_PROFILE` do OCG mais recente e
    cria itens de fundação no Roadmap com `source='ocg_foundation'`,
    `priority='high'`, `status='sugerido'`. Idempotente — itens já
    existentes pelo nome não são recriados.

    Chamado:
      - automaticamente pelo `OCGUpdaterService` quando o OCG muda;
      - manualmente pelo GP via este endpoint (ex: quando o contrato
        deste módulo evoluir e quiser regerar).
    """
    from app.services.roadmap_foundation_service import RoadmapFoundationService
    result = await RoadmapFoundationService(db).sync_foundation(project_id)
    logger.info(
        "roadmap.foundation_sync_requested",
        project_id=str(project_id),
        created=result.get("created"),
        skipped=result.get("skipped"),
    )
    return result


# ============================================================================
# Backlog Vivo (spec seção 7.2)
# ============================================================================

@router.get("/projects/{project_id}/backlog")
async def get_backlog(
    project_id: UUID,
    category: str = None,
    _perm: dict = Depends(require_action("project:view")),
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
    perm: dict = Depends(require_action("backlog:manage")),
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
        actor_id=perm["user_id"],
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
    _setup: dict = Depends(require_project_setup_complete),
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
        provider_enum = LLMProvider(provider) if provider in [p.value for p in LLMProvider] else LLMProvider.DEEPSEEK
        client = LLMServiceFactory.create_client(provider_enum, api_key)
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
