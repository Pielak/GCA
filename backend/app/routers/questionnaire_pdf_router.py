"""
Endpoints para PDF editável do questionário técnico GCA.

GET  /projects/{id}/questionnaire/pdf — Gera PDF editável p/ download
POST /projects/{id}/questionnaire/upload-pdf — Upload do PDF preenchido → ingestão → OCG
"""
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import io

from app.db.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.base import Project, ProjectMember

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["questionnaire-pdf"])


@router.get("/{project_id}/questionnaire/pdf")
async def download_questionnaire_pdf(
    project_id: UUID,
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Gera e retorna o PDF editável do questionário técnico do projeto.

    O PDF tem campos AcroForm — o usuário preenche no seu leitor de PDF
    favorito, salva e depois faz upload de volta.
    """
    project = await _require_project_access(project_id, current_user_id, db)

    from app.services.questionnaire_pdf_service import generate_pdf

    pdf_bytes = generate_pdf(
        project_name=project.name,
        deliverable_type=project.deliverable_type or "",
        project_slug=project.short_slug or project.slug,
    )

    filename = f"Questionario_GCA_{project.short_slug or project.slug}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{project_id}/questionnaire/upload-pdf")
async def upload_questionnaire_pdf(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user_id: UUID = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Upload do PDF preenchido → extrai respostas → ingere como doc → seed OCG.

    Fluxo:
        1. Valida que é PDF.
        2. Tenta extrair respostas dos campos AcroForm (pypdf).
        3. Se AcroForm vazio, faz fallback: extrai texto e procura padrão Q1, Q2...
        4. Persiste as respostas no questionário do projeto (mesmo formato do form em tela).
        5. Ingere o PDF como documento de ingestão normal (categoria: "Questionário PDF").
        6. Retorna o número de perguntas respondidas.
    """
    project = await _require_project_access(project_id, current_user_id, db)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser PDF")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF excede 10MB")
    if len(pdf_bytes) < 100:
        raise HTTPException(status_code=400, detail="PDF vazio ou corrompido")

    # Pré-flight: detecta PDF flattened (sem AcroForm) antes de tentar extrair.
    # Leitores como Chrome "Salvar como PDF", certas versões de Evince/Preview
    # achatam o formulário ao salvar — checkboxes viram pixels e o
    # text_fallback não consegue ler seu estado. Sem esse guard, o GP recebia
    # "Incompleto" com blockers em Q40/Q41/Q43 sem entender que a causa era
    # o PDF, não as respostas (DT-018).
    import pypdf
    try:
        _preflight = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        _root_keys = list(_preflight.trailer["/Root"].keys()) if "/Root" in _preflight.trailer else []
        _has_acroform = "/AcroForm" in _root_keys
    except Exception as e:
        # Se o pré-flight falhou, deixa o extrator adiante dar o erro real.
        logger.warning("questionnaire_pdf.preflight_failed", error=str(e))
        _has_acroform = True

    if not _has_acroform:
        logger.warning(
            "questionnaire_pdf.flattened_rejected",
            project_id=str(project_id),
            filename=file.filename,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "O PDF enviado não contém campos editáveis (AcroForm). "
                "Seu leitor provavelmente achatou o formulário ao salvar — "
                "checkboxes viraram imagem e o sistema não consegue ler. "
                "Baixe o PDF novamente usando o botão 'Baixar PDF editável', "
                "abra-o em Adobe Reader, Foxit Reader ou Okular, preencha, "
                "e salve com Ctrl+S (não use 'Salvar como…' nem 'Imprimir → PDF'). "
                "Reenvie em seguida."
            ),
        )

    # 1. Extrair respostas dos campos AcroForm
    from app.services.questionnaire_pdf_service import extract_answers_from_pdf, extract_answers_from_text

    answers = {}
    try:
        answers = extract_answers_from_pdf(pdf_bytes)
        logger.info("questionnaire_pdf.acroform_extracted",
                     project_id=str(project_id), fields=len(answers))
    except Exception as e:
        logger.warning("questionnaire_pdf.acroform_failed", error=str(e))

    # 2. Fallback: text extraction
    if not answers:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
            answers = extract_answers_from_text(full_text)
            logger.info("questionnaire_pdf.text_fallback",
                         project_id=str(project_id), fields=len(answers))
        except Exception as e:
            logger.warning("questionnaire_pdf.text_extraction_failed", error=str(e))

    if not answers:
        raise HTTPException(
            status_code=422,
            detail=(
                "Não foi possível extrair respostas do PDF. Certifique-se de que "
                "preencheu os campos editáveis (AcroForm) e salvou o arquivo."
            ),
        )

    # 3. Unificar no fluxo oficial de submissão do questionário (estratégia B).
    # O PDF é transporte, não documento — não ingerir como `ingested_documents`
    # (evita falso-positivo de PII em dados naturais de stakeholders, DT-015).
    # As respostas são submetidas via `QuestionnaireService.submit_questionnaire`,
    # que roda o pipeline completo: TechnologyVerificationService (8 fases de
    # validação) → analise + salva Questionnaire → se aprovado, dispara
    # `_generate_ocg` (pipeline de 8 agentes IA) → `_fire_ocg_change_hooks`
    # (backlog + Gatekeeper reeval).
    from app.services.questionnaire_service import QuestionnaireService

    gp_email = await _get_user_email(current_user_id, db)
    success, questionnaire_id, error = await QuestionnaireService.submit_questionnaire(
        db=db,
        project_id=project_id,
        gp_email=gp_email,
        responses=answers,
    )

    answered_count = len(answers)
    total_questions = 49
    percentage = round(answered_count / total_questions * 100, 1)

    if not success:
        logger.warning(
            "questionnaire_pdf.submit_failed",
            project_id=str(project_id),
            error=error,
            answered=answered_count,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao processar questionário: {error or 'erro desconhecido'}",
        )

    logger.info(
        "questionnaire_pdf.processed",
        project_id=str(project_id),
        questionnaire_id=questionnaire_id,
        answered=answered_count,
        percentage=percentage,
    )

    return {
        "success": True,
        "questionnaire_id": questionnaire_id,
        "answered_questions": answered_count,
        "total_questions": total_questions,
        "completion_percentage": percentage,
        "message": (
            f"{answered_count} de {total_questions} perguntas extraídas "
            f"({percentage}%). Questionário submetido para análise — se aprovado, "
            f"o OCG será gerado automaticamente."
        ),
    }


# ── Helpers ──

async def _require_project_access(
    project_id: UUID, user_id: UUID, db: AsyncSession
) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    member = (await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.is_active == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if not member:
        from app.models.base import User
        user = await db.get(User, user_id)
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Sem acesso a este projeto")
    return project


async def _get_user_email(user_id: UUID, db: AsyncSession) -> str:
    from app.models.base import User
    user = await db.get(User, user_id)
    return user.email if user else "unknown@gca.local"
