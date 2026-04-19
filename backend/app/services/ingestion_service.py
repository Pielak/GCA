"""
Ingestion Service — Upload, deduplicação e gestão de documentos por projeto.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import IngestedDocument, ArguiderAnalysis, ModuleCandidate, OCG, OCGDeltaLog
from app.services.arguider_service import ArguiderService, DocumentExtractor

logger = structlog.get_logger(__name__)

# Tipos de arquivo aceitos → file_type
EXTENSION_MAP = {
    "pdf": "pdf", "docx": "docx", "doc": "docx",
    "md": "markdown", "txt": "markdown",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image", "webp": "image",
    "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
    "py": "code", "ts": "code", "js": "code", "java": "code",
    "cs": "code", "go": "code", "rs": "code",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def _propagate_async(
    project_id: UUID,
    changes: list[dict],
    ocg_version: Optional[int],
) -> None:
    """Roda PropagationService em sessão própria, fire-and-forget.

    Isolamento: se a propagação falhar (ex: backlog regen quebra), o erro
    NÃO afeta a transação do OCG (já commitada). Apenas loga.

    Sessão dedicada: não compartilha com a sessão da ingestão (que pode
    estar fechando). Cada propagation tem seu próprio ciclo de vida.
    """
    try:
        from app.db.database import AsyncSessionLocal
        from app.services.propagation_service import PropagationService

        async with AsyncSessionLocal() as db:
            propagator = PropagationService(db)
            await propagator.propagate(
                project_id=project_id,
                changes=changes,
                ocg_version=ocg_version,
            )
    except Exception as exc:  # noqa: BLE001
        import traceback
        logger.warning(
            "ingestion.propagate_async_failed",
            project_id=str(project_id),
            error=str(exc) or repr(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )


async def _reevaluate_gatekeeper_for_audit(
    db: AsyncSession,
    project_id: UUID,
    ocg_version: Optional[int],
    trigger: str,
) -> None:
    """Recomputa Gatekeeper com o OCG atual e grava evento no audit_log.

    Gatekeeper é consolidação read-only em tempo real: aplica thresholds no
    momento da leitura usando o OCG mais recente. Esta função força essa
    recomputação após uma mudança relevante de OCG (contrato §5) e deixa
    trilha auditável do estado resultante.

    - Se o projeto não tem OCG, é no-op silencioso (nada a reavaliar).
    - Não muta `GatekeeperItem` nem `ModuleCandidate` (permanecem como os
      Arguiders anteriores os gravaram).
    - Idempotente do ponto de vista de dados; cada chamada gera um novo
      evento de audit (trilha cronológica).
    """
    from app.services.gatekeeper_service import GatekeeperService
    from app.services.audit_service import AuditService

    ocg_check = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    if ocg_check.scalar_one_or_none() is None:
        logger.info(
            "ingestion.gatekeeper_reeval_noop_no_ocg",
            project_id=str(project_id),
            trigger=trigger,
        )
        return

    gatekeeper = GatekeeperService(db)
    state = await gatekeeper.get_project_gatekeeper(project_id)
    ocg_section = state.get("ocg", {}) or {}
    summary = state.get("summary", {}) or {}

    audit = AuditService(db)
    await audit.log_event(
        event_type="GATEKEEPER_REEVALUATED",
        resource_type="project",
        resource_id=project_id,
        details={
            "trigger": trigger,
            "ocg_version": ocg_version,
            "blocking_pillars": ocg_section.get("blocking_pillars", []),
            "derived_status": ocg_section.get("derived_status"),
            "overall_score": (ocg_section.get("status") or {}).get("overall_score"),
            "has_blockers": summary.get("has_blockers"),
            "open_gaps": summary.get("open_gaps"),
            "open_show_stoppers": summary.get("open_show_stoppers"),
        },
    )


async def _reevaluate_gatekeeper_async(
    project_id: UUID,
    ocg_version: Optional[int],
    trigger: str = "document_ingestion",
) -> None:
    """Wrapper fire-and-forget de `_reevaluate_gatekeeper_for_audit`.

    Abre sessão própria, commita o evento de audit. Isolado: se falhar, não
    afeta a transação de OCG/ingestão (já commitadas).
    """
    try:
        from app.db.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await _reevaluate_gatekeeper_for_audit(
                db, project_id, ocg_version=ocg_version, trigger=trigger,
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        import traceback
        logger.warning(
            "ingestion.gatekeeper_reeval_failed",
            project_id=str(project_id),
            error=str(exc) or repr(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )


async def _regenerate_backlog_for_audit(
    db: AsyncSession,
    project_id: UUID,
    ocg_version: Optional[int],
    trigger: str,
) -> None:
    """Regenera backlog do OCG atual e grava evento BACKLOG_REGENERATED.

    Usado em dois cenários sem `changes` estruturados:
    - **Geração inicial** do OCG a partir do questionário aprovado (não há
      diff; o backlog precisa ser populado do zero).
    - **Contração** no delete de documento (itens de versões obsoletas
      precisam ser substituídos pelo estado atual do OCG).

    Preserva items com `source="manual"`. No-op silencioso se o projeto não
    tem OCG. Não comita — caller decide.
    """
    from app.services.backlog_service import BacklogService
    from app.services.audit_service import AuditService

    ocg_check = await db.execute(
        select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
    )
    if ocg_check.scalar_one_or_none() is None:
        logger.info(
            "ingestion.backlog_regen_noop_no_ocg",
            project_id=str(project_id),
            trigger=trigger,
        )
        return

    backlog_svc = BacklogService(db)
    result = await backlog_svc.regenerate_from_ocg(project_id, ocg_version)

    audit = AuditService(db)
    await audit.log_event(
        event_type="BACKLOG_REGENERATED",
        resource_type="backlog",
        resource_id=project_id,
        details={
            "trigger": trigger,
            "ocg_version": ocg_version,
            "regenerated": result.get("regenerated", 0),
        },
    )


async def _regenerate_backlog_async(
    project_id: UUID,
    ocg_version: Optional[int],
    trigger: str,
) -> None:
    """Wrapper fire-and-forget de `_regenerate_backlog_for_audit`.

    Abre sessão própria, commita o resultado. Isolado: se falhar, não afeta
    a transação de OCG (já commitada).
    """
    try:
        from app.db.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await _regenerate_backlog_for_audit(
                db, project_id, ocg_version=ocg_version, trigger=trigger,
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        import traceback
        logger.warning(
            "ingestion.backlog_regen_failed",
            project_id=str(project_id),
            error=str(exc) or repr(exc),
            error_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )


async def _fire_ocg_change_hooks(
    project_id: UUID,
    ocg_version: Optional[int],
    trigger: str,
    changes: Optional[list[dict]] = None,
) -> None:
    """Dispara hooks de consistência downstream após uma mudança de OCG.

    Unifica os 3 pontos onde OCG pode mudar:
    - Ingestão de documento: passa `changes` do `OCGUpdaterService`
      (roteia via PropagationService para categorias afetadas).
    - Contração no delete: passa `changes` dos campos revertidos.
    - Geração inicial via questionário: passa `changes=None` (não há diff;
      regenera backlog do zero).

    Todos os hooks são fire-and-forget com sessão própria e erros isolados.
    """
    if changes:
        asyncio.create_task(
            _propagate_async(
                project_id=project_id,
                changes=changes,
                ocg_version=ocg_version,
            )
        )
    else:
        asyncio.create_task(
            _regenerate_backlog_async(
                project_id=project_id,
                ocg_version=ocg_version,
                trigger=trigger,
            )
        )

    asyncio.create_task(
        _reevaluate_gatekeeper_async(
            project_id=project_id,
            ocg_version=ocg_version,
            trigger=trigger,
        )
    )


class IngestionService:
    """Serviço de ingestão de documentos por projeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_document(
        self,
        project_id: UUID,
        uploaded_by: UUID,
        file_bytes: bytes,
        original_filename: str,
        content_type: str = "",
        category: str | None = None,
    ) -> dict:
        """Upload e análise assíncrona de documento."""
        # Validar tamanho
        if len(file_bytes) > MAX_FILE_SIZE:
            return {"error": "Arquivo excede o tamanho máximo de 50MB", "status_code": 413}

        # Determinar tipo
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        file_type = EXTENSION_MAP.get(ext)
        if not file_type:
            return {"error": f"Tipo de arquivo '.{ext}' não suportado", "status_code": 400}

        # SHA256 para deduplicação
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Verificar duplicata
        existing = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.project_id == project_id,
                IngestedDocument.file_hash == file_hash,
            )
        )
        dup = existing.scalar_one_or_none()
        if dup:
            return {
                "duplicate": True,
                "existing_document_id": str(dup.id),
                "message": "Documento já ingerido neste projeto.",
                "status_code": 409,
            }

        # Gerar filename único
        filename = f"{uuid4()}.{ext}"

        # Persistir bytes em storage para abertura read-only posterior
        from app.utils.ingested_storage import write_ingested
        write_ingested(project_id, filename, file_bytes)

        # PII detection — triagem básica no conteúdo textual
        pii_detected, pii_fields = self._detect_pii(file_bytes, file_type)
        quarantine_status = "quarantined" if pii_detected else "none"

        # Criar registro
        document = IngestedDocument(
            project_id=project_id,
            filename=filename,
            original_filename=original_filename,
            file_type=file_type,
            document_category=category,
            file_hash=file_hash,
            file_size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
            quarantine_status=quarantine_status,
            pii_detected=pii_detected,
            pii_fields=json.dumps(pii_fields) if pii_fields else None,
            arguider_status="pending" if not pii_detected else "quarantined",
            git_file_path=f"docs/ingested/uncategorized/{filename}",
        )
        self.db.add(document)
        await self.db.commit()

        doc_id = document.id

        if pii_detected:
            logger.warning(
                "ingestion.pii_detected_quarantined",
                document_id=str(doc_id),
                pii_fields=pii_fields,
            )
            return {
                "document_id": str(doc_id),
                "quarantined": True,
                "pii_fields": pii_fields,
                "message": "Documento em quarentena — PII detectado. Requer decisão explícita.",
                "status_code": 200,
            }

        # Disparar análise assíncrona (somente se não quarentenado)
        asyncio.create_task(
            self._analyze_async(doc_id, project_id, file_bytes, file_type)
        )

        logger.info(
            "ingestion.document_uploaded",
            document_id=str(doc_id),
            project_id=str(project_id),
            filename=original_filename,
            file_type=file_type,
            size=len(file_bytes),
        )

        return {
            "document_id": str(doc_id),
            "status": "pending",
            "message": "Documento recebido. Análise iniciada.",
        }

    @staticmethod
    def _valid_cpf(digits: str) -> bool:
        if len(digits) != 11 or digits == digits[0] * 11:
            return False
        s1 = sum(int(digits[i]) * (10 - i) for i in range(9))
        r1 = (s1 * 10) % 11
        d1 = 0 if r1 == 10 else r1
        if d1 != int(digits[9]):
            return False
        s2 = sum(int(digits[i]) * (11 - i) for i in range(10))
        r2 = (s2 * 10) % 11
        d2 = 0 if r2 == 10 else r2
        return d2 == int(digits[10])

    @staticmethod
    def _valid_cnpj(digits: str) -> bool:
        if len(digits) != 14 or digits == digits[0] * 14:
            return False
        w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        s1 = sum(int(digits[i]) * w1[i] for i in range(12))
        r1 = s1 % 11
        d1 = 0 if r1 < 2 else 11 - r1
        if d1 != int(digits[12]):
            return False
        s2 = sum(int(digits[i]) * w2[i] for i in range(13))
        r2 = s2 % 11
        d2 = 0 if r2 < 2 else 11 - r2
        return d2 == int(digits[13])

    @staticmethod
    def _valid_luhn(digits: str) -> bool:
        if len(digits) < 13 or len(digits) > 19:
            return False
        if digits == digits[0] * len(digits):
            return False  # todos-iguais (ex: "0000...") — Luhn aceita mas não é cartão real
        total = 0
        for i, ch in enumerate(reversed(digits)):
            n = int(ch)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @staticmethod
    def _detect_pii(file_bytes: bytes, file_type: str) -> tuple[bool, list[str]]:
        """Triagem básica de PII em conteúdo textual.

        Para CPF/CNPJ/cartão: exige que o valor passe pelo dígito verificador real
        (mod-11 / Luhn) — regex puro dá falso-positivo em PDFs/binários que têm
        runs de 14 dígitos em xref tables, IDs de objetos etc.
        """
        import re

        # Só analisa tipos textuais
        if file_type in ("image", "spreadsheet"):
            return False, []

        try:
            text = file_bytes.decode("utf-8", errors="ignore")[:100_000]  # primeiros 100KB
        except Exception:
            return False, []

        only_digits = re.compile(r"\D")
        detected: list[str] = []

        # CPF: 11 dígitos, opcional formatação, valida mod-11
        for m in re.finditer(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text):
            if IngestionService._valid_cpf(only_digits.sub("", m.group(0))):
                detected.append("cpf")
                break

        # CNPJ: 14 dígitos, opcional formatação, valida mod-11
        for m in re.finditer(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", text):
            if IngestionService._valid_cnpj(only_digits.sub("", m.group(0))):
                detected.append("cnpj")
                break

        # Cartão de crédito: 13-19 dígitos, valida Luhn
        for m in re.finditer(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", text):
            if IngestionService._valid_luhn(only_digits.sub("", m.group(0))):
                detected.append("cartao_credito")
                break

        # Email pessoal: regex é suficiente (formato é discriminante)
        if re.search(r"\b[a-zA-Z0-9._%+-]+@(gmail|hotmail|yahoo|outlook)\.[a-zA-Z]{2,}\b", text):
            detected.append("email_pessoal")

        # Telefone BR: regex antigo (`\b\(?\d{2}\)?\s?\d{4,5}-?\d{4}\b`)
        # era promíscuo — matchava qualquer sequência 2+4-5+4 dígitos sem
        # contexto, dando falso-positivo em PDFs com métricas, IDs,
        # coordenadas, timestamps. DT-028 quitada: agora exige padrão
        # formatado inequívoco OU contexto explícito ("tel"/"fone"/
        # "whatsapp" nas proximidades), e valida DDD como 11-99.
        if IngestionService._has_br_phone(text):
            detected.append("telefone_br")

        return len(detected) > 0, detected

    @staticmethod
    def _has_br_phone(text: str) -> bool:
        """Detecção estrita de telefone BR.

        Aceita apenas padrões inequívocos:
          (a) "(DD) 9NNNN-NNNN" ou "(DD) NNNN-NNNN"  — parênteses no DDD
          (b) "+55 DD 9NNNN-NNNN"                    — E.164
          (c) "DD 9NNNN-NNNN" / "DD NNNN-NNNN"       — hífen obrigatório
          (d) qualquer match acima com contexto "tel"/"fone"/"telefone"/
              "whatsapp"/"celular"/"cel." numa janela de 40 chars antes.

        Rejeita:
          - sequências sem hífen nem parênteses (lookout de PDF binário);
          - DDs fora de 11-99 (faixa válida dos DDDs no Brasil);
          - números com todos dígitos iguais (1111111111) ou sentinelas.
        """
        import re as _re

        # Padrões inequívocos — exige pelo menos 1 separador (parêntese
        # ou hífen) no formato esperado do Brasil.
        patterns = [
            # (DD) NNNNN-NNNN ou (DD) NNNN-NNNN — parênteses obrigatórios
            r"\((\d{2})\)\s?9?\d{4}-\d{4}\b",
            # +55 DD NNNNN-NNNN — E.164
            r"\+55\s?(\d{2})\s?9?\d{4}-?\d{4}\b",
            # DD NNNNN-NNNN — hífen final obrigatório (elimina runs crus)
            r"\b(\d{2})\s\d{4,5}-\d{4}\b",
        ]

        def _valid_ddd(ddd_str: str) -> bool:
            try:
                ddd = int(ddd_str)
                return 11 <= ddd <= 99
            except ValueError:
                return False

        def _not_sentinel(raw: str) -> bool:
            digits = _re.sub(r"\D", "", raw)
            # Rejeita só "todos iguais" (1111111111, 0000000000).
            # Ter 2 dígitos distintos (ex.: "1199999999") é normal em
            # telefone real.
            if len(set(digits)) < 2:
                return False
            return True

        for pat in patterns:
            for m in _re.finditer(pat, text):
                if _valid_ddd(m.group(1)) and _not_sentinel(m.group(0)):
                    return True

        # Fallback com contexto: se o texto tem "tel"/"fone"/"celular"/
        # "whatsapp" próximo a uma sequência plausível, também conta.
        ctx_re = _re.compile(
            r"(?:tel|telefone|fone|cel(?:ular)?|whats?app|contato)"
            r"[^\n]{0,40}?(\d{2}[\s().-]{0,3}9?\d{4}[\s.-]?\d{4})",
            _re.IGNORECASE,
        )
        for m in ctx_re.finditer(text):
            digits = _re.sub(r"\D", "", m.group(1))
            if len(digits) in (10, 11) and _not_sentinel(digits):
                return True

        return False

    # MVP 8 Fase 1 — Mapa canônico de estágio → porcentagem.
    # Ordem: queued(0) → extracting_text(10) → analyzing(40) →
    # updating_ocg(70) → regenerating_backlog(90) → completed(100).
    _STAGE_PERCENTS: dict[str, int] = {
        "queued": 0,
        "extracting_text": 10,
        "analyzing": 40,
        "updating_ocg": 70,
        "regenerating_backlog": 90,
        "completed": 100,
        "failed": 0,  # percent não regride; frontend mostra último valor
    }

    @classmethod
    async def _update_stage(
        cls,
        db,
        document_id: UUID,
        stage: str,
        *,
        percent: int | None = None,
    ) -> None:
        """MVP 8 Fase 1 — atualiza arguider_stage + porcentagem do documento.

        Commit dedicado para que o frontend (polling) enxergue o estágio
        mesmo que o resto do pipeline demore. Se `percent` não vem, usa
        o default do mapa. Nunca regride porcentagem exceto quando
        explicitamente passado (ex: reset pra 0 em reanalyze).
        """
        from datetime import datetime as _dt, timezone as _tz
        from app.models.base import IngestedDocument as _Doc
        doc = await db.get(_Doc, document_id)
        if not doc:
            return
        doc.arguider_stage = stage
        if percent is None:
            percent = cls._STAGE_PERCENTS.get(stage, doc.arguider_progress_percent)
        # Não regride (exceto se caller explicitamente passar valor menor)
        if percent >= doc.arguider_progress_percent or stage == "failed":
            doc.arguider_progress_percent = percent
        doc.arguider_stage_updated_at = _dt.now(_tz.utc)
        await db.commit()

    async def _notify_provider_fallback(
        self,
        db,
        *,
        project_id: UUID,
        primary_provider: str,
        fallback_provider: str,
        document_id: UUID,
    ) -> None:
        """DT-064 — Avisa GPs + Admins do projeto que o provider IA
        primário falhou e o sistema fez fallback automático para o
        próximo da cadeia. Inclui aviso sobre possível aumento de tempo
        de processamento quando o fallback é provider local (Ollama)."""
        from sqlalchemy import select as _select, or_ as _or
        from app.models.base import ProjectMember, User
        from app.services.notification_inapp_service import InAppNotificationService

        # Labels amigáveis + aviso sobre tempo
        _names = {
            "anthropic": "Anthropic (Claude)",
            "openai": "OpenAI (GPT)",
            "gemini": "Google (Gemini)",
            "deepseek": "DeepSeek",
            "grok": "Grok",
            "ollama": "Ollama (IA local)",
        }
        primary_name = _names.get(primary_provider, primary_provider)
        fallback_name = _names.get(fallback_provider, fallback_provider)

        is_local_fallback = (fallback_provider == "ollama")
        if is_local_fallback:
            time_hint = (
                " O processamento pode ficar mais lento que o habitual, pois a "
                "IA local tem latência maior que os provedores remotos."
            )
        else:
            time_hint = (
                " O tempo de processamento pode variar conforme o provedor de "
                "fallback."
            )

        title = f"Fallback de IA ativado: usando {fallback_name}"
        message = (
            f"O provedor principal ({primary_name}) não respondeu com sucesso "
            f"na análise do documento. O sistema trocou automaticamente para "
            f"{fallback_name} para não travar o fluxo.{time_hint} "
            f"Se o problema persistir, verifique credenciais e cotas em "
            f"Configurações do projeto → IA."
        )

        # Destinatários: GPs do projeto + Admins ativos
        members_q = _select(ProjectMember.user_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "gp",
            ProjectMember.accepted_at.isnot(None),
            ProjectMember.is_active.is_(True),
        )
        admins_q = _select(User.id).where(
            User.is_admin.is_(True), User.is_active.is_(True),
        )
        gp_ids = list((await db.execute(members_q)).scalars().all())
        admin_ids = list((await db.execute(admins_q)).scalars().all())
        recipients = list({*gp_ids, *admin_ids})

        notif = InAppNotificationService(db)
        for uid in recipients:
            try:
                await notif.notify(
                    user_id=uid,
                    event_type="ai.provider_fallback",
                    title=title,
                    message=message,
                    project_id=project_id,
                    resource_type="ingested_document",
                    resource_id=document_id,
                    link=f"/projects/{project_id}/ingestion",
                    severity="warning",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("ingestion.fallback_notification_failed",
                               user_id=str(uid), error=str(e))

        logger.info(
            "ingestion.provider_fallback_notified",
            project_id=str(project_id),
            document_id=str(document_id),
            primary=primary_provider,
            fallback=fallback_provider,
            recipients=len(recipients),
        )

    async def _analyze_async(
        self,
        document_id: UUID,
        project_id: UUID,
        file_bytes: bytes,
        file_type: str,
    ):
        """Executa análise do Arguidor em background.

        DT-064 — Fallback automático entre providers IA: se o provider
        default falhar (rate limit, quota, 5xx, timeout, erro de rede
        em geral), tenta o próximo provider configurado no projeto em
        cascata. Notifica GPs + Admins quando o fallback é acionado,
        avisando sobre possível aumento de tempo se cair em IA local.
        """
        try:
            from app.db.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                # DT-064: resolver toda a cadeia de providers configurados
                # (default primeiro + demais validados). Loop vai tentar em
                # sequência se o primeiro falhar com erro transiente.
                from app.services.ai_key_resolver import AIKeyResolver
                provider_chain = await AIKeyResolver.resolve_project_provider_chain(db, project_id)

                if not provider_chain:
                    raise RuntimeError(
                        "Nenhum provedor de IA configurado no projeto. "
                        "GP deve configurar provedor e chave em Settings > IA."
                    )

                extractor = DocumentExtractor()

                # MVP 8 Fase 1 — marcar estágio "extracting_text"
                await IngestionService._update_stage(db, document_id, "extracting_text")

                # Extrair texto (fora do loop — não depende do provider)
                doc_text = await extractor.extract_text(file_bytes, file_type)

                # MVP 8 Fase 1 — texto extraído, próximo estágio será "analyzing"
                # (a atualização real acontece dentro do loop, antes do
                # arguider.analyze_document)

                # Buscar OCG + análises prévias (fora do loop também)
                ocg_result = await db.execute(
                    select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
                )
                _ocg = ocg_result.scalar_one_or_none()
                _current_ocg = json.loads(_ocg.ocg_data) if _ocg and _ocg.ocg_data else {}
                _prev_analyses_raw = await db.execute(
                    select(ArguiderAnalysis).where(ArguiderAnalysis.project_id == project_id)
                )
                _prev_analyses = []
                for a in _prev_analyses_raw.scalars().all():
                    try:
                        _prev_analyses.append({
                            "document_classification": json.loads(a.document_classification),
                            "gaps": json.loads(a.gaps),
                            "module_candidates": json.loads(a.module_candidates),
                        })
                    except json.JSONDecodeError:
                        pass

                # ═══ DT-064: Loop de fallback entre providers ═══
                last_error = None
                successful_provider = None
                for idx, pcfg in enumerate(provider_chain):
                    provider = pcfg["provider"]
                    model = pcfg.get("model")
                    base_url = pcfg.get("base_url") if provider == "ollama" else None

                    try:
                        project_api_key = await AIKeyResolver.get_project_key(
                            db, project_id, provider=provider,
                        )
                    except Exception as e:
                        logger.warning("ingestion.key_resolve_failed",
                                       provider=provider, error=str(e))
                        last_error = f"Chave do provider {provider} indisponível: {e}"
                        continue

                    logger.info("ingestion.provider_attempt",
                                document_id=str(document_id),
                                attempt=idx + 1,
                                total=len(provider_chain),
                                provider=provider,
                                model=model or "(default)")

                    try:
                        arguider = ArguiderService(
                            db,
                            project_api_key=project_api_key,
                            provider=provider,
                            model=model,
                            base_url=base_url,
                        )
                        # MVP 8 Fase 1 — marcar estágio "analyzing"
                        await IngestionService._update_stage(db, document_id, "analyzing")
                        await arguider.analyze_document(
                            document_id=document_id,
                            project_id=project_id,
                            document_text=doc_text,
                            current_ocg=_current_ocg,
                            previous_analyses=_prev_analyses,
                        )
                        successful_provider = provider
                        if idx > 0:
                            logger.warning(
                                "ingestion.provider_fallback_succeeded",
                                document_id=str(document_id),
                                primary_provider=provider_chain[0]["provider"],
                                fallback_provider=provider,
                                providers_tried=idx + 1,
                            )
                            # DT-064: notificar GPs + admins do projeto que o
                            # fallback aconteceu e que o processamento pode
                            # estar mais lento se o fallback for provider local.
                            await self._notify_provider_fallback(
                                db,
                                project_id=project_id,
                                primary_provider=provider_chain[0]["provider"],
                                fallback_provider=provider,
                                document_id=document_id,
                            )
                        break  # sucesso — sai do loop
                    except Exception as e:
                        err_msg = str(e)
                        last_error = err_msg
                        should_fallback = AIKeyResolver.should_fallback_to_next_provider(err_msg)
                        logger.warning(
                            "ingestion.provider_failed",
                            document_id=str(document_id),
                            provider=provider,
                            should_fallback=should_fallback,
                            remaining_providers=len(provider_chain) - idx - 1,
                            error=err_msg[:200],
                        )
                        if not should_fallback:
                            # Erro de parâmetro/schema — fallback não resolve.
                            # Aborta cascata e propaga.
                            raise
                        # Reset do status do documento para próxima tentativa
                        from app.models.base import IngestedDocument as _IngDoc
                        _doc = await db.get(_IngDoc, document_id)
                        if _doc:
                            _doc.arguider_status = "pending"
                            _doc.arguider_error_message = None
                            await db.commit()
                        continue  # tenta próximo provider

                if not successful_provider:
                    # Todos os providers falharam com erro transiente.
                    # Propaga para o caller ser marcado como erro.
                    raise RuntimeError(
                        f"Todos os {len(provider_chain)} providers configurados "
                        f"retornaram erro transiente. Último erro: {last_error[:300] if last_error else 'desconhecido'}"
                    )

                # Marcar documento como analisado com OCG atualizado
                doc = await db.get(IngestedDocument, document_id)
                if doc and doc.arguider_status == "completed":
                    doc.ocg_updated = True
                    await db.commit()

                    # Registrar evento DOCUMENT_INGESTED
                    from app.services.audit_service import AuditService
                    audit = AuditService(db)
                    await audit.log_event(
                        event_type="DOCUMENT_INGESTED",
                        resource_type="ingested_document",
                        resource_id=document_id,
                        details={
                            "project_id": str(project_id),
                            "filename": doc.original_filename,
                            "file_type": doc.file_type,
                            "ocg_updated": True,
                        },
                    )
                    await db.commit()

                    logger.info("ingestion.analysis_complete_ocg_updated",
                               document_id=str(document_id),
                               project_id=str(project_id))

                    # === OCG REATIVO: Atualizar OCG via IA ===
                    try:
                        from app.services.ocg_updater_service import OCGUpdaterService
                        import json as _json

                        # Carregar análise do Arguidor
                        arguider_result = await db.execute(
                            select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == document_id)
                        )
                        analysis = arguider_result.scalar_one_or_none()
                        analysis_data = {}
                        if analysis:
                            try:
                                analysis_data = {
                                    "classification": _json.loads(analysis.document_classification) if analysis.document_classification else {},
                                    "gaps": _json.loads(analysis.gaps) if analysis.gaps else [],
                                    "module_candidates": _json.loads(analysis.module_candidates) if analysis.module_candidates else [],
                                }
                            except _json.JSONDecodeError:
                                pass

                        # MVP 8 Fase 1 — estágio "updating_ocg"
                        await IngestionService._update_stage(db, document_id, "updating_ocg")

                        # Atualizar OCG via IA
                        updater = OCGUpdaterService(db)
                        update_result = await updater.update_ocg_from_arguider(
                            project_id=project_id,
                            arguider_analysis=analysis_data,
                            document_id=document_id,
                            actor_id=doc.uploaded_by if doc else None,
                            trigger_source="document_ingestion",
                        )

                        # Propagar se houve mudanças — fire-and-forget em
                        # task separada com SUA PRÓPRIA sessão. Isola falhas
                        # de propagação do commit do OCG (que já aconteceu)
                        # e libera o caller para retornar imediatamente.
                        if update_result and update_result.get("changes"):
                            # MVP 8 Fase 1 — estágio "regenerating_backlog"
                            await IngestionService._update_stage(db, document_id, "regenerating_backlog")
                            asyncio.create_task(
                                _propagate_async(
                                    project_id=project_id,
                                    changes=update_result["changes"],
                                    ocg_version=update_result.get("version_to"),
                                )
                            )
                            # Reavaliar Gatekeeper com o OCG novo (MVP 2 §10).
                            # Também fire-and-forget: grava evento
                            # GATEKEEPER_REEVALUATED no audit_log com
                            # blocking_pillars/derived_status resultantes.
                            asyncio.create_task(
                                _reevaluate_gatekeeper_async(
                                    project_id=project_id,
                                    ocg_version=update_result.get("version_to"),
                                    trigger="document_ingestion",
                                )
                            )

                        logger.info("ingestion.ocg_reactive_complete",
                                   document_id=str(document_id),
                                   ocg_updated=bool(update_result))

                        # MVP 8 Fase 1 — marcar estágio "completed" após
                        # sucesso completo do pipeline (arguider + ocg + propagação disparada).
                        await IngestionService._update_stage(db, document_id, "completed", percent=100)

                    except Exception as e:
                        import traceback
                        logger.warning(
                            "ingestion.ocg_reactive_error",
                            document_id=str(document_id),
                            error=str(e) or repr(e),
                            error_type=type(e).__name__,
                            traceback=traceback.format_exc(),
                        )
                        # Mesmo com falha no OCG reativo, o Arguidor já
                        # completou — marcamos completed mas com porcentagem
                        # ligeiramente menor pro frontend mostrar o alerta
                        # via arguider_error_message (que vem do caller).
                        await IngestionService._update_stage(db, document_id, "completed", percent=95)

        except Exception as e:
            logger.error("ingestion.analysis_async_error", document_id=str(document_id), error=str(e))
            # MVP 8 Fase 1 — marcar estágio "failed" para frontend parar o polling
            try:
                from app.db.database import AsyncSessionLocal as _ASL
                async with _ASL() as _db:
                    await IngestionService._update_stage(_db, document_id, "failed")
            except Exception:
                pass

    async def list_documents(self, project_id: UUID) -> list[dict]:
        """Lista documentos do projeto."""
        result = await self.db.execute(
            select(IngestedDocument)
            .where(IngestedDocument.project_id == project_id)
            .order_by(IngestedDocument.created_at.desc())
        )
        docs = result.scalars().all()
        return [
            {
                "id": str(d.id),
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "document_category": d.document_category,
                "arguider_status": d.arguider_status,
                # DT-022: expõe mensagem de erro na listagem para a UI mostrar
                # o motivo direto no row (sem precisar clicar pra ver detalhe).
                # Só é preenchida quando arguider_status='error'.
                "arguider_error_message": d.arguider_error_message,
                # DT-029: expõe motivo da quarentena na listagem (tipos PII
                # detectados) para o GP poder decidir se é falso-positivo
                # e liberar via botão.
                "quarantine_status": getattr(d, "quarantine_status", "none"),
                "pii_fields": (json.loads(d.pii_fields) if d.pii_fields else []) if getattr(d, "pii_detected", False) else [],
                "ocg_updated": d.ocg_updated,
                "file_size_bytes": d.file_size_bytes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "source_type": getattr(d, "source_type", None),
                "source_url": getattr(d, "source_url", None),
                "source_repo_id": str(d.source_repo_id) if getattr(d, "source_repo_id", None) else None,
                "content_status": getattr(d, "content_status", "available"),
                # MVP 8 Fase 1 — feedback de progresso (expostos na listagem
                # pra barra renderizar sem depender de chamada extra ao /status)
                "arguider_stage": getattr(d, "arguider_stage", None),
                "arguider_progress_percent": getattr(d, "arguider_progress_percent", 0),
                "arguider_stage_updated_at": (
                    d.arguider_stage_updated_at.isoformat()
                    if getattr(d, "arguider_stage_updated_at", None) else None
                ),
            }
            for d in docs
        ]

    async def get_document_detail(self, project_id: UUID, document_id: UUID) -> dict | None:
        """Documento completo + análise do Arguidor."""
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None

        detail = {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "file_type": doc.file_type,
            "document_category": doc.document_category,
            "arguider_status": doc.arguider_status,
            "arguider_error_message": doc.arguider_error_message,
            "ocg_updated": doc.ocg_updated,
            "file_size_bytes": doc.file_size_bytes,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        # Buscar análise
        analysis_result = await self.db.execute(
            select(ArguiderAnalysis).where(ArguiderAnalysis.document_id == document_id)
        )
        analysis = analysis_result.scalar_one_or_none()
        if analysis:
            detail["analysis"] = {
                "classification": json.loads(analysis.document_classification) if analysis.document_classification else {},
                "gaps": json.loads(analysis.gaps) if analysis.gaps else [],
                "show_stoppers": json.loads(analysis.show_stoppers) if analysis.show_stoppers else [],
                "poor_definitions": json.loads(analysis.poor_definitions) if analysis.poor_definitions else [],
                "improvement_suggestions": json.loads(analysis.improvement_suggestions) if analysis.improvement_suggestions else [],
                "module_candidates": json.loads(analysis.module_candidates) if analysis.module_candidates else [],
                "ocg_fields_to_update": json.loads(analysis.ocg_fields_to_update) if analysis.ocg_fields_to_update else [],
                "tokens_used": analysis.tokens_used,
                "latency_ms": analysis.latency_ms,
            }

        return detail

    async def get_document_status(self, project_id: UUID, document_id: UUID) -> dict | None:
        """Status para polling."""
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        return {
            "document_id": str(doc.id),
            "arguider_status": doc.arguider_status,
            "arguider_started_at": doc.arguider_started_at.isoformat() if doc.arguider_started_at else None,
            "arguider_completed_at": doc.arguider_completed_at.isoformat() if doc.arguider_completed_at else None,
            "ocg_updated": doc.ocg_updated,
            # MVP 8 Fase 1 — feedback de progresso
            "arguider_stage": doc.arguider_stage,
            "arguider_progress_percent": doc.arguider_progress_percent,
            "arguider_stage_updated_at": doc.arguider_stage_updated_at.isoformat() if doc.arguider_stage_updated_at else None,
        }

    async def delete_document(self, project_id: UUID, document_id: UUID) -> dict:
        """Remove documento se não tem módulos aprovados.

        Se o documento deixou deltas no OCG (`ocg_delta_log`), faz contração
        segura antes de deletar: reverte os campos que este doc alterou ao
        valor anterior, exceto aqueles que foram posteriormente modificados
        por outros deltas. Registra um delta com `trigger_source=
        'document_removal'` para auditoria e rollback (contrato §5).
        """
        result = await self.db.execute(
            select(IngestedDocument).where(
                IngestedDocument.id == document_id,
                IngestedDocument.project_id == project_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return {"success": False, "error": "Documento não encontrado", "status_code": 404}

        if doc.arguider_status == "processing":
            return {"success": False, "error": "Documento em análise, aguarde conclusão", "status_code": 409}

        # Verificar módulos aprovados
        mc_result = await self.db.execute(
            select(func.count(ModuleCandidate.id)).where(
                ModuleCandidate.project_id == project_id,
                ModuleCandidate.status == "approved",
                ModuleCandidate.source_document_ids.contains(str(document_id)),
            )
        )
        approved_count = mc_result.scalar() or 0
        if approved_count > 0:
            return {"success": False, "error": "Módulos aprovados dependem deste documento", "status_code": 409}

        # Contração de OCG antes do delete (contrato §5: OCG contrai com
        # ingestão ruim ou conflitante; aqui, com remoção explícita).
        contraction_info = await self._contract_ocg_for_deleted_document(project_id, document_id)

        await self.db.delete(doc)
        await self.db.commit()
        logger.info(
            "ingestion.document_deleted",
            document_id=str(document_id),
            contracted_fields=contraction_info.get("fields_reverted", []),
            skipped_fields=contraction_info.get("fields_skipped", []),
        )

        # Disparar hooks de consistência se a contração efetivamente mudou
        # o OCG. Sem fields_reverted, não há delta a propagar (skipped-only).
        fields_reverted = contraction_info.get("fields_reverted", [])
        if fields_reverted:
            changes = [{"field": f} for f in fields_reverted]
            await _fire_ocg_change_hooks(
                project_id=project_id,
                ocg_version=contraction_info.get("version_to"),
                trigger="document_removal",
                changes=changes,
            )

        return {"success": True, "ocg_contraction": contraction_info}

    async def _contract_ocg_for_deleted_document(
        self, project_id: UUID, document_id: UUID
    ) -> dict:
        """Reverte no OCG os campos alterados pelo doc, exceto os que foram
        tocados por deltas posteriores (evita perder contribuições de outros
        documentos).

        Retorna dict com `fields_reverted` e `fields_skipped`. Se o doc não
        teve deltas, retorna `{"fields_reverted": [], "fields_skipped": []}`.
        """
        # 1. Buscar deltas deste doc em ordem cronológica (mais antigo primeiro).
        doc_deltas_q = await self.db.execute(
            select(OCGDeltaLog).where(
                OCGDeltaLog.project_id == project_id,
                OCGDeltaLog.document_id == document_id,
            ).order_by(OCGDeltaLog.created_at.asc())
        )
        doc_deltas = list(doc_deltas_q.scalars().all())
        if not doc_deltas:
            return {"fields_reverted": [], "fields_skipped": []}

        # 2. Para cada campo tocado por este doc, descobrir o valor "antes"
        #    do primeiro delta que o tocou. O delta mais antigo guarda o `old`
        #    em `fields_changed[field].old` — essa é a origem da reversão.
        first_old: dict[str, any] = {}
        for delta in doc_deltas:
            try:
                changes = json.loads(delta.fields_changed) if delta.fields_changed else {}
            except (ValueError, TypeError):
                changes = {}
            for field, change in changes.items():
                if field not in first_old and isinstance(change, dict) and "old" in change:
                    first_old[field] = change["old"]

        if not first_old:
            return {"fields_reverted": [], "fields_skipped": []}

        touched_fields = set(first_old.keys())
        doc_delta_ids = {d.id for d in doc_deltas}

        # 3. Verificar deltas posteriores (de outros docs ou de propagação) que
        #    tocaram os mesmos campos. Para cada campo com delta posterior,
        #    NÃO reverte — apenas registra no fields_skipped.
        later_q = await self.db.execute(
            select(OCGDeltaLog).where(
                OCGDeltaLog.project_id == project_id,
                OCGDeltaLog.created_at > doc_deltas[0].created_at,
            ).order_by(OCGDeltaLog.created_at.asc())
        )
        later_deltas = [d for d in later_q.scalars().all() if d.id not in doc_delta_ids]

        fields_blocked = set()
        for later in later_deltas:
            try:
                later_changes = json.loads(later.fields_changed) if later.fields_changed else {}
            except (ValueError, TypeError):
                later_changes = {}
            for field in later_changes:
                if field in touched_fields:
                    fields_blocked.add(field)

        fields_to_revert = touched_fields - fields_blocked

        # 4. Carregar OCG atual; se nenhum campo a reverter, só registra delta
        #    documental sem alterar OCG.
        ocg_q = await self.db.execute(
            select(OCG).where(OCG.project_id == project_id).order_by(OCG.created_at.desc()).limit(1)
        )
        ocg = ocg_q.scalar_one_or_none()
        if not ocg:
            return {
                "fields_reverted": [],
                "fields_skipped": sorted(fields_blocked),
                "note": "OCG inexistente; nada a contrair",
            }

        try:
            ocg_current = json.loads(ocg.ocg_data) if ocg.ocg_data else {}
        except (ValueError, TypeError):
            ocg_current = {}

        reverted_changes = {}
        for field in fields_to_revert:
            old_value = first_old[field]
            current_value = ocg_current.get(field)
            ocg_current[field] = old_value
            reverted_changes[field] = {
                "old": current_value,
                "new": old_value,
                "reasoning": f"Revertido por remoção do documento {document_id}",
            }

        # 5. Se houve reversão, incrementar versão + gravar OCG novo + delta.
        version_from = ocg.version
        version_to = version_from + (1 if reverted_changes else 0)

        if reverted_changes:
            ocg.ocg_data = json.dumps(ocg_current, ensure_ascii=False)
            ocg.version = version_to
            ocg.updated_at = datetime.now(timezone.utc)

        # Sempre grava delta de removal (mesmo que fields_to_revert vazio) —
        # audit trail de que o doc foi removido e quais campos ficaram presos.
        summary_parts = []
        if reverted_changes:
            summary_parts.append(
                f"Contraídos {len(reverted_changes)} campo(s): {sorted(reverted_changes)}"
            )
        if fields_blocked:
            summary_parts.append(
                f"Não contraídos (tocados por deltas posteriores): {sorted(fields_blocked)}"
            )
        change_summary = " | ".join(summary_parts) if summary_parts else "Remoção sem impacto no OCG"

        delta = OCGDeltaLog(
            project_id=project_id,
            document_id=None,  # doc está sendo deletado; FK seria inválida
            ocg_version_from=version_from,
            ocg_version_to=version_to,
            fields_changed=json.dumps(reverted_changes, ensure_ascii=False),
            change_summary=change_summary,
            trigger_source="document_removal",
            ocg_snapshot=json.dumps(ocg_current, ensure_ascii=False) if reverted_changes else None,
        )
        self.db.add(delta)

        return {
            "fields_reverted": sorted(reverted_changes.keys()),
            "fields_skipped": sorted(fields_blocked),
            "version_from": version_from,
            "version_to": version_to,
        }
