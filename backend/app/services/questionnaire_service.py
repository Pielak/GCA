"""Questionnaire Service for n8n Integration"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
import json
import asyncio

from app.models.base import Project, User, Questionnaire
from app.services.email_service import EmailService
from app.core.config import settings

logger = structlog.get_logger(__name__)


class QuestionnaireService:
    """Service for managing questionnaire submissions and n8n analysis"""

    @staticmethod
    async def submit_questionnaire(
        db: AsyncSession,
        project_id: Optional[UUID],
        gp_email: str,
        responses: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Submit technical questionnaire for n8n analysis.
        Returns (success, questionnaire_id, error_message)

        project_id pode ser None quando o questionário é submetido
        pelo fluxo externo (NovoProjetoPage) antes do projeto existir.
        """
        try:
            # Verify project exists (only if project_id provided)
            if project_id:
                result = await db.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                if not project:
                    logger.warning("questionnaire.project_not_found", project_id=str(project_id))
                    return False, None, "Projeto não encontrado"

            # Verify GP exists (optional — external flow may not have user yet)
            result = await db.execute(
                select(User).where(User.email == gp_email)
            )
            gp_user = result.scalar_one_or_none()
            if not gp_user and project_id:
                logger.warning("questionnaire.gp_not_found", email=gp_email)
                return False, None, "Gestor de Projeto não encontrado"

            # Generate questionnaire_id (would be database id in real implementation)
            import secrets
            questionnaire_id = secrets.token_hex(8)

            project_name = responses.get('1', 'Projeto sem nome')
            project_slug = responses.get('2', f'projeto-{secrets.token_hex(4)}')

            # Log questionnaire submission
            logger.info(
                "questionnaire.submitted",
                questionnaire_id=questionnaire_id,
                project_id=str(project_id) if project_id else "externo",
                gp_email=gp_email,
            )

            # Se fluxo externo (sem project_id), criar ProjectRequest para aprovação
            if not project_id:
                from app.models.onboarding import ProjectRequest, ProjectRequestStatus, DeliverableType

                # Criar user GP se não existir
                if not gp_user:
                    from app.core.security import hash_password
                    temp_pass = secrets.token_urlsafe(16)
                    gp_user = User(
                        id=uuid4(),
                        email=gp_email,
                        full_name=responses.get('gp_name', gp_email.split('@')[0]),
                        password_hash=hash_password(temp_pass),
                        is_admin=False,
                        is_active=True,
                        first_access_completed=False,
                    )
                    db.add(gp_user)
                    await db.flush()

                # Verificar se slug já existe
                existing_slug = await db.execute(
                    select(ProjectRequest).where(ProjectRequest.project_slug == project_slug)
                )
                if existing_slug.scalar_one_or_none():
                    project_slug = f"{project_slug}-{secrets.token_hex(3)}"

                # Mapear tipo de entregável do questionário para enum
                deliverable_type_map = {
                    'Sistema web novo': DeliverableType.NEW_SYSTEM,
                    'Aplicação mobile': DeliverableType.MOBILE_APP,
                    'Módulo funcional / Extensão de ecossistema': DeliverableType.MODULE,
                    'Melhoria em sistema existente': DeliverableType.ENHANCEMENT,
                    'Integração com sistema legado': DeliverableType.INTEGRATION,
                    'Modernização / Refatoração': DeliverableType.MODERNIZATION,
                    'ETL / ELT / Integração de dados': DeliverableType.ETL,
                    'Sustentação evolutiva': DeliverableType.MAINTENANCE,
                }
                raw_deliverable = responses.get('deliverable_type', 'Sistema web novo')
                deliverable_type = deliverable_type_map.get(raw_deliverable, DeliverableType.NEW_SYSTEM)

                # Criar solicitação de projeto
                proj_request = ProjectRequest(
                    gp_id=gp_user.id,
                    project_name=project_name,
                    project_slug=project_slug,
                    description=responses.get('description', ''),
                    deliverable_type=deliverable_type,
                    schema_name=f"proj_{project_slug.replace('-', '_')}",
                    status=ProjectRequestStatus.PENDING,
                )
                db.add(proj_request)
                await db.commit()

                logger.info(
                    "questionnaire.project_request_created",
                    project_request_id=str(proj_request.id),
                    project_name=project_name,
                    gp_email=gp_email,
                )

            # Notificar admin responsável (DT-038) ou fallback pra todos
            # admins se projeto não tiver responsible_admin_id definido.
            # Externo (sem project_id) sempre cai no fallback — ainda não há
            # relação admin-projeto antes da aprovação.
            asyncio.create_task(
                QuestionnaireService._notify_admins_questionnaire_submitted(
                    gp_email=gp_email,
                    project_name=project_name,
                    questionnaire_id=questionnaire_id,
                    project_id=project_id,
                )
            )

            # Opção A: Análise built-in (imediato)
            # Triggers: (1) Analyse questionnaire, (2) Save to DB, (3) Send email notification
            try:
                # Import here to avoid circular dependency
                from app.routers.webhooks import analyze_questionnaire

                # Run analysis
                result = analyze_questionnaire(responses)

                # Save questionnaire to database
                questionnaire = Questionnaire(
                    project_id=project_id,
                    gp_email=gp_email,
                    responses=json.dumps(responses),
                    adherence_score=result["adherenceScore"],
                    status=result["status"],
                    approved=result["approved"],
                    validations=json.dumps(result["validations"]),
                    observations=result["observations"],
                    restrictions=result["restrictions"],
                    highlighted_fields=json.dumps(result["highlightedFields"]),
                    submitted_at=datetime.now(timezone.utc),
                    analyzed_at=datetime.now(timezone.utc),
                )
                db.add(questionnaire)
                await db.commit()

                logger.info(
                    "questionnaire.saved_to_db",
                    questionnaire_id=str(questionnaire.id),
                    project_id=str(project_id),
                    adherence_score=result["adherenceScore"],
                )

                # Determine notification type based on approval status
                if result["approved"]:
                    notification_type = "approved"
                else:
                    notification_type = "revision_needed"

                # Trigger email asynchronously (non-blocking)
                asyncio.create_task(
                    QuestionnaireService._send_analysis_email(
                        gp_email=gp_email,
                        project_id=str(project_id),
                        questionnaire_id=str(questionnaire.id),
                        notification_type=notification_type,
                        analysis_result=result,
                    )
                )

                # OPTION C: Trigger n8n for enhanced analysis (asynchronous)
                asyncio.create_task(
                    QuestionnaireService._trigger_n8n_analysis(
                        questionnaire_id=str(questionnaire.id),
                        project_id=str(project_id),
                        gp_email=gp_email,
                        responses=responses,
                    )
                )

                # Se aprovado na verificação tecnológica, disparar geração do OCG
                # via pipeline de 8 agentes IA (assíncrono, não bloqueia a resposta)
                if result["approved"]:
                    asyncio.create_task(
                        QuestionnaireService._generate_ocg(
                            questionnaire_id=questionnaire.id,
                            project_id=project_id,
                            gp_email=gp_email,
                        )
                    )

                logger.info(
                    "questionnaire.analysis_triggered",
                    questionnaire_id=str(questionnaire.id),
                    adherence_score=result["adherenceScore"],
                    approved=result["approved"],
                    ocg_triggered=result["approved"],
                )

                # Use real DB UUID as the questionnaire_id
                questionnaire_id = str(questionnaire.id)

            except Exception as e:
                logger.warning(
                    "questionnaire.analysis_failed",
                    error=str(e),
                    questionnaire_id=questionnaire_id
                )
                # Análise falhou, mas ProjectRequest já foi criado (se fluxo externo)
                # Salvar questionário sem análise para não perder a submissão
                try:
                    await db.rollback()
                    questionnaire = Questionnaire(
                        project_id=project_id,
                        gp_email=gp_email,
                        responses=json.dumps(responses),
                        adherence_score=0,
                        status="pending_analysis",
                        approved=False,
                        submitted_at=datetime.now(timezone.utc),
                    )
                    db.add(questionnaire)
                    await db.commit()
                    questionnaire_id = str(questionnaire.id)
                    logger.info("questionnaire.saved_without_analysis", questionnaire_id=questionnaire_id)
                except Exception as save_err:
                    logger.error("questionnaire.save_fallback_failed", error=str(save_err))

            return True, questionnaire_id, None

        except Exception as e:
            await db.rollback()
            logger.error("questionnaire.submit_failed", error=str(e))
            return False, None, str(e)

    @staticmethod
    async def _notify_admins_questionnaire_submitted(
        gp_email: str,
        project_name: str,
        questionnaire_id: str,
        project_id: Optional[str] = None,
    ):
        """Notifica admin(s) por email quando um questionário é submetido.

        DT-038 — compartimentalização de notificações (contrato §2.2).
        Regra:
        1. Se `project_id` existe E `Project.responsible_admin_id` está
           setado → notifica **apenas** esse admin. É o caminho oficial
           pós-aprovação do projeto.
        2. Se `project_id` existe mas `responsible_admin_id` é NULL
           (projeto legado sem backfill) → fallback pra todos admins +
           log de warning pra alerta de gap arquitetural.
        3. Se `project_id` é None (fluxo externo `/solicitar-projeto`,
           projeto ainda não criado) → notifica todos admins ativos. Essa
           submissão é o pré-gate da criação do projeto — admin precisa
           decidir; não há relação admin-projeto ainda.
        """
        try:
            from app.db.database import AsyncSessionLocal
            from app.models.base import User, Project
            from app.services.email_service import EmailService

            async with AsyncSessionLocal() as db:
                admins: list = []
                notification_scope = "all_admins"

                if project_id:
                    project = await db.get(Project, project_id)
                    if project and project.responsible_admin_id:
                        responsible = await db.get(User, project.responsible_admin_id)
                        if responsible and responsible.is_active:
                            admins = [responsible]
                            notification_scope = "responsible_admin"
                        else:
                            logger.warning(
                                "questionnaire.responsible_admin_inactive",
                                project_id=str(project_id),
                                admin_id=str(project.responsible_admin_id),
                            )
                    else:
                        logger.warning(
                            "questionnaire.no_responsible_admin_fallback",
                            project_id=str(project_id),
                            reason="project_not_found" if not project else "responsible_admin_id_null",
                        )

                # Fallback: nenhum admin responsável resolvido → todos admins ativos.
                # (Fluxo externo sem project_id cai aqui; caminho legado também.)
                if not admins:
                    result = await db.execute(
                        select(User).where(User.is_admin == True, User.is_active == True)
                    )
                    admins = list(result.scalars().all())

                logger.info(
                    "questionnaire.notification_scope",
                    scope=notification_scope,
                    recipients=len(admins),
                    project_id=str(project_id) if project_id else None,
                )

            subject = f"GCA — Novo questionário submetido: {project_name}"
            body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #1e1b4b; padding: 20px; border-radius: 12px 12px 0 0;">
                    <h2 style="color: #c4b5fd; margin: 0;">GCA — Questionário Pendente de Aprovação</h2>
                </div>
                <div style="background: #1e293b; padding: 24px; border-radius: 0 0 12px 12px; color: #cbd5e1;">
                    <p>Um novo questionário técnico foi submetido e aguarda aprovação:</p>
                    <ul style="list-style: none; padding: 0;">
                        <li><strong>Projeto:</strong> {project_name}</li>
                        <li><strong>GP:</strong> {gp_email}</li>
                        <li><strong>ID:</strong> {questionnaire_id}</li>
                    </ul>
                    <p>Acesse a área de <strong>Administração → Projetos</strong> no GCA para revisar e aprovar:</p>
                    <p><a href="https://gca.code-auditor.com.br/login" style="color: #a78bfa; text-decoration: underline;">https://gca.code-auditor.com.br/login</a></p>
                    <hr style="border-color: #334155; margin: 20px 0;" />
                    <p style="color: #64748b; font-size: 12px;">GCA — Gestão de Codificação Assistida</p>
                </div>
            </div>
            """

            # DT-016: usa SMTP do projeto quando temos project_id (Contexto B
            # do contrato §6.6 — identidade do remetente é do cliente, não do
            # admin global). Fallback global automático no email_service quando
            # projeto não tem SMTP configurado.
            for admin in admins:
                try:
                    if project_id:
                        async with AsyncSessionLocal() as _email_db:
                            await EmailService.send_email_for_project(
                                db=_email_db,
                                project_id=project_id,
                                to_email=admin.email,
                                subject=subject,
                                html_content=body,
                            )
                    else:
                        EmailService.send_email(
                            to_email=admin.email,
                            subject=subject,
                            html_content=body,
                        )
                    logger.info("questionnaire.admin_notified", admin_email=admin.email, project=project_name)
                except Exception as e:
                    logger.warning("questionnaire.admin_notify_failed", admin_email=admin.email, error=str(e))

        except Exception as e:
            logger.error("questionnaire.admin_notification_error", error=str(e))

    @staticmethod
    async def _send_analysis_email(
        gp_email: str,
        project_id: str,
        questionnaire_id: str,
        notification_type: str,
        analysis_result: Dict[str, Any],
    ) -> None:
        """
        Send email notification after analysis.
        Runs asynchronously.
        """
        try:
            email_service = EmailService()

            project_name = analysis_result.get("projectName", "Projeto")
            gp_name = gp_email.split("@")[0]

            if notification_type == "approved":
                logger.info(
                    "questionnaire.sending_approval_email",
                    email=gp_email,
                    project_id=project_id,
                )
                email_service.send_questionnaire_approved_email(
                    to_email=gp_email,
                    gp_name=gp_name,
                    project_name=project_name,
                    suggested_stack=analysis_result.get("suggestedStack", "A definir"),
                    observations=analysis_result.get("observations", ""),
                    restrictions=analysis_result.get("restrictions", ""),
                    project_link=f"https://gca.code-auditor.com.br/projects/{project_id}" if project_id else "",
                )

                # Notificação in-app para o GP
                try:
                    from app.models.base import User as _User
                    from app.services.notification_inapp_service import InAppNotificationService
                    user_row = (await self.db.execute(select(_User).where(_User.email == gp_email))).scalar_one_or_none()
                    if user_row and project_id:
                        await InAppNotificationService(self.db).notify(
                            user_id=user_row.id,
                            event_type="questionnaire_approved",
                            title="Questionário aprovado",
                            message=f"O questionário de \"{project_name}\" foi aprovado. Você pode avançar para a ingestão.",
                            project_id=project_id,
                            resource_type="questionnaire",
                            link=f"/projects/{project_id}/ocg",
                            severity="success",
                        )
                except Exception as notif_err:
                    logger.warning("questionnaire.notify_failed", error=str(notif_err))

            elif notification_type == "revision_needed":
                logger.info(
                    "questionnaire.sending_revision_email",
                    email=gp_email,
                    project_id=project_id,
                )
                conflicts = analysis_result.get("validations", {}).get("logicConflicts", [])
                email_service.send_questionnaire_revision_needed_email(
                    to_email=gp_email,
                    gp_name=gp_name,
                    project_name=project_name,
                    conflicts=conflicts,
                    adherence_score=analysis_result.get("adherenceScore", 0),
                    revision_link=f"https://gca.code-auditor.com.br/novo-projeto?email={gp_email}",
                )

            logger.info(
                "questionnaire.email_sent",
                email=gp_email,
                notification_type=notification_type,
            )

        except Exception as e:
            logger.error(
                "questionnaire.email_failed",
                error=str(e),
                email=gp_email,
            )
            # Don't propagate email errors

    @staticmethod
    async def get_questionnaire_status(
        db: AsyncSession,
        questionnaire_id: str,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Get questionnaire status and n8n analysis results from database.
        Admin sees: adherence_score + gaps (hidden details)
        GP sees: only status + observations + restrictions
        """
        try:
            # Fetch questionnaire from database
            from uuid import UUID
            try:
                q_uuid = UUID(questionnaire_id)
            except ValueError:
                logger.warning("questionnaire.invalid_id", questionnaire_id=questionnaire_id)
                return {
                    "questionnaire_id": questionnaire_id,
                    "status": "pending",
                    "submission_date": datetime.now(timezone.utc).isoformat(),
                    "observations": "Questionnaire not found",
                    "restrictions": "",
                    "highlighted_fields": [],
                }

            result = await db.execute(
                select(Questionnaire).where(Questionnaire.id == q_uuid)
            )
            questionnaire = result.scalar_one_or_none()

            if not questionnaire:
                logger.warning("questionnaire.not_found", questionnaire_id=questionnaire_id)
                return {
                    "questionnaire_id": questionnaire_id,
                    "status": "pending",
                    "submission_date": datetime.now(timezone.utc).isoformat(),
                    "observations": "Questionnaire not found",
                    "restrictions": "",
                    "highlighted_fields": [],
                }

            # Parse highlighted_fields if available
            highlighted_fields = []
            try:
                if questionnaire.highlighted_fields:
                    highlighted_fields = json.loads(questionnaire.highlighted_fields)
            except (json.JSONDecodeError, TypeError):
                highlighted_fields = []

            # Deriva issues acionáveis para o GP a partir das validations
            # salvas (que hoje só admin vê). Aqui NÃO exponho categorias
            # internas nem contadores técnicos — só o que o GP precisa para
            # corrigir: título, perguntas afetadas, sugestão, severidade.
            blocking_issues: list[dict] = []
            try:
                if questionnaire.validations:
                    validations = json.loads(questionnaire.validations)
                    # `validations` tem 4 buckets (logicConflicts, gaps,
                    # incompatibilities, delivery_alignment) — cada um lista
                    # de findings completos. Vamos achatar.
                    all_findings = []
                    for bucket in ("logicConflicts", "gaps", "incompatibilities", "delivery_alignment"):
                        all_findings.extend(validations.get(bucket, []))
                    for f in all_findings:
                        sev = f.get("severity")
                        if sev in ("blocker", "critical", "warning"):
                            blocking_issues.append({
                                "severity": sev,
                                "rule_id": f.get("rule_id"),
                                "title": f.get("title", ""),
                                "description": f.get("description", ""),
                                "affected_questions": f.get("affected_questions", []),
                                "suggestion": f.get("suggestion", ""),
                                "pillar": f.get("pillar"),
                            })
                    # Ordena: blocker > critical > warning
                    order = {"blocker": 0, "critical": 1, "warning": 2}
                    blocking_issues.sort(key=lambda x: order.get(x["severity"], 99))
            except (json.JSONDecodeError, TypeError, AttributeError):
                blocking_issues = []

            response = {
                "questionnaire_id": str(questionnaire.id),
                "status": questionnaire.status,
                "approved": questionnaire.approved,
                "adherence_score": questionnaire.adherence_score,
                "submission_date": questionnaire.submitted_at.isoformat(),
                "analyzed_at": questionnaire.analyzed_at.isoformat() if questionnaire.analyzed_at else None,
                "observations": questionnaire.observations or "",
                "restrictions": questionnaire.restrictions or "",
                "highlighted_fields": highlighted_fields,
                "blocking_issues": blocking_issues,
            }

            # Add internal details for admin
            if is_admin:
                try:
                    validations = {}
                    if questionnaire.validations:
                        validations = json.loads(questionnaire.validations)
                except (json.JSONDecodeError, TypeError):
                    validations = {"logicConflicts": [], "gaps": [], "incompatibilities": []}

                response["internal"] = {
                    "adherence_score": questionnaire.adherence_score,
                    "approved": questionnaire.approved,
                    "gaps_count": len(validations.get("gaps", [])),
                    "conflicts_count": len(validations.get("logicConflicts", [])),
                    "analyzed_at": questionnaire.analyzed_at.isoformat() if questionnaire.analyzed_at else None,
                }

            return response

        except Exception as e:
            logger.error("questionnaire.status_fetch_failed", error=str(e), questionnaire_id=questionnaire_id)
            return {
                "questionnaire_id": questionnaire_id,
                "status": "pending",
                "submission_date": datetime.now(timezone.utc).isoformat(),
                "observations": "Error fetching questionnaire",
                "restrictions": "",
                "highlighted_fields": [],
            }

    @staticmethod
    async def _trigger_n8n_analysis(
        questionnaire_id: str,
        project_id: str,
        gp_email: str,
        responses: Dict[str, Any],
    ) -> None:
        """
        Trigger n8n workflow for enhanced analysis with Qwen AI (OPTION C).
        Runs asynchronously in background after initial submission.

        n8n will:
        1. Receive questionnaire data
        2. Run Qwen AI for deeper insights and recommendations
        3. Call back to /api/v1/webhooks/questionnaire-result with enhanced results
        """
        try:
            from app.services.n8n_service import N8nService

            success, error = await N8nService.trigger_questionnaire_analysis(
                questionnaire_id=questionnaire_id,
                project_id=project_id,
                gp_email=gp_email,
                responses=responses,
            )

            if success:
                logger.info(
                    "questionnaire.n8n_triggered",
                    questionnaire_id=questionnaire_id,
                )
            else:
                logger.warning(
                    "questionnaire.n8n_trigger_failed",
                    questionnaire_id=questionnaire_id,
                    error=error,
                )

        except Exception as e:
            logger.error(
                "questionnaire.n8n_dispatch_error",
                questionnaire_id=questionnaire_id,
                error=str(e),
            )
            # Don't propagate n8n errors - built-in analysis already completed

    @staticmethod
    async def _generate_ocg(
        questionnaire_id: UUID,
        project_id: UUID,
        gp_email: str,
    ) -> None:
        """
        Dispara geração do OCG via pipeline de 8 agentes IA.
        Executa assincronamente após verificação tecnológica aprovar o questionário.

        Pipeline:
        1. Agent 0 (Analyzer): classifica respostas por pilar
        2. Agents 1-7 (Pillar Specialists): analisam cada pilar em paralelo
        3. Agent 8 (Consolidator): consolida em OCG final e salva no banco
        """
        try:
            logger.info(
                "questionnaire.ocg_generation_starting",
                questionnaire_id=str(questionnaire_id),
                project_id=str(project_id),
            )

            # Criar nova sessão de banco (necessário pois estamos em task assíncrona)
            from app.db.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                from app.services.ocg_service import OCGService
                ocg_service = OCGService(db)

                ocg_response = await ocg_service.generate_ocg_from_questionnaire(
                    questionnaire_id=questionnaire_id,
                    project_id=project_id,
                )

                # Atualizar status do questionário para 'ocg_generated'
                from sqlalchemy import select
                from app.models.base import Questionnaire
                stmt = select(Questionnaire).where(Questionnaire.id == questionnaire_id)
                result = await db.execute(stmt)
                questionnaire = result.scalar_one_or_none()
                if questionnaire:
                    questionnaire.status = "ocg_generated"
                    await db.commit()

                logger.info(
                    "questionnaire.ocg_generation_complete",
                    questionnaire_id=str(questionnaire_id),
                    ocg_id=str(ocg_response.ocg_id),
                    overall_score=ocg_response.COMPOSITE_SCORE.get("overall", 0),
                    status=ocg_response.COMPOSITE_SCORE.get("status", "UNKNOWN"),
                )

                # Seed inicial do backlog + reavaliação do Gatekeeper com o OCG
                # recém-criado (MVP 2 §10: backlog consistente com o contexto).
                # Fire-and-forget: abre sessões próprias, não afeta a transação
                # que acabou de commitar o OCG.
                from app.services.ingestion_service import _fire_ocg_change_hooks
                ocg_version_new = getattr(ocg_response, "version", None) or 1
                await _fire_ocg_change_hooks(
                    project_id=project_id,
                    ocg_version=ocg_version_new,
                    trigger="questionnaire_approved",
                    changes=None,  # geração inicial: sem diff; regenera do zero
                )

                # Enviar email ao GP com resultado do OCG
                try:
                    from app.services.email_service import EmailService
                    from app.models.base import Project
                    proj_result = await db.execute(
                        select(Project).where(Project.id == project_id)
                    )
                    project = proj_result.scalar_one_or_none()
                    project_name = project.name if project else f"Projeto {project_id}"

                    EmailService.send_ocg_generated_email(
                        to_email=gp_email,
                        project_name=project_name,
                        ocg_data=ocg_response.dict() if hasattr(ocg_response, 'dict') else {},
                        project_id=str(project_id),
                    )
                except Exception as email_err:
                    logger.warning("questionnaire.ocg_email_failed", error=str(email_err))

        except Exception as e:
            logger.error(
                "questionnaire.ocg_generation_failed",
                questionnaire_id=str(questionnaire_id),
                error=str(e),
            )
            # Não propagar erro — a verificação tecnológica já foi concluída
            # O OCG pode ser regenerado manualmente depois
