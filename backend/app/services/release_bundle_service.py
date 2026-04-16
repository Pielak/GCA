"""ReleaseBundleService — gera handoff zip versionado de um projeto (Fase D).

Conteúdo do bundle (`/app/storage/releases/<pid>/v<N>.zip`):
    MANIFEST.json              — lista de deliverables, evidências, sha256
    RELEASE_NOTES.md           — diff humano do ocg_delta_log desde release anterior
    deliverables_status.json   — snapshot completo do registry no momento da release
    docs/                      — copy de docs/* do repo Git (ADRs, diagramas, compliance)

Pré-check obrigatório: readiness >= threshold (default 90%, configurável).
Falha → status='failed', error_message preenchido. Bundle não fica disponível.

Versionamento: incremental por projeto (UNIQUE constraint garante atomicidade
em race condition entre 2 generates simultâneos — o segundo recebe o
próximo número ou IntegrityError).

NÃO inclui código-fonte: o repo Git já É a fonte da verdade do código.
Bundle é a *trilha de release* (audit + handoff), não duplicata do Git.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.base import (
    OCG,
    OCGDeltaLog,
    Project,
    ProjectRelease,
)
from app.services.deliverable_registry import DeliverableRegistry

logger = structlog.get_logger(__name__)


RELEASES_BASE = Path("/app/storage/releases")
DEFAULT_READINESS_THRESHOLD = 90.0


class ReleaseBundleService:
    """Gera Release Bundles (zip + manifest + notes)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────── create ────────────────────────────

    async def create_bundle(
        self,
        project_id: UUID,
        actor_id: Optional[UUID] = None,
        threshold: float = DEFAULT_READINESS_THRESHOLD,
    ) -> Dict[str, Any]:
        """Cria um novo Release Bundle.

        Steps:
          1. Pre-check: readiness >= threshold. Se não, retorna 412-like.
          2. Determina próxima versão (max(version)+1 do projeto).
          3. INSERT row status='generating'.
          4. Coleta artefatos: deliverables snapshot + ocg_data + delta_log
             diff + arquivos do docs/ via Git.
          5. Monta zip in-memory; calcula sha256.
          6. Persiste em filesystem.
          7. UPDATE row status='ready' + file_path + sha256 + manifest_json.

        Em qualquer falha após step 3: row marcada 'failed' + error_message.

        Returns:
            ``{"id", "version", "status", "readiness_pct", "file_path",
               "sha256", "size_bytes"}`` ou ``{"error", "readiness_pct"}``
            se pre-check falhou.
        """
        # 1. Pre-check
        registry = DeliverableRegistry(self.db)
        export = await registry.export_status(project_id)
        readiness_pct = export["summary"]["readiness_pct"]

        if readiness_pct < threshold:
            return {
                "error": "readiness_below_threshold",
                "readiness_pct": readiness_pct,
                "threshold": threshold,
                "missing_count": export["summary"]["by_status"].get("missing", 0),
                "manual_only_count": export["summary"]["by_status"].get("manual_only", 0),
            }

        # 2. Próxima versão
        result = await self.db.execute(
            select(func.max(ProjectRelease.version)).where(ProjectRelease.project_id == project_id)
        )
        last_version = result.scalar() or 0
        next_version = last_version + 1

        # 3. INSERT generating (commit imediato para reservar a versão)
        release_row = ProjectRelease(
            project_id=project_id,
            version=next_version,
            status="generating",
            readiness_pct=readiness_pct,
            readiness_threshold=threshold,
            created_by=actor_id,
        )
        self.db.add(release_row)
        await self.db.commit()
        await self.db.refresh(release_row)

        try:
            # 4. Coletar artefatos
            project = await self.db.get(Project, project_id)
            project_name = project.name if project else "(projeto)"

            ocg_result = await self.db.execute(
                select(OCG).where(OCG.project_id == project_id).order_by(OCG.version.desc()).limit(1)
            )
            ocg = ocg_result.scalar_one_or_none()
            ocg_data = {}
            ocg_version = None
            if ocg and ocg.ocg_data:
                try:
                    ocg_data = json.loads(ocg.ocg_data) if isinstance(ocg.ocg_data, str) else ocg.ocg_data
                    ocg_version = ocg.version
                except (json.JSONDecodeError, TypeError):
                    ocg_data = {}

            # 5. Construir zip
            zip_bytes, manifest_dict = await self._build_zip(
                project_id=project_id,
                project_name=project_name,
                version=next_version,
                deliverables_export=export,
                ocg_data=ocg_data,
                ocg_version=ocg_version,
                last_version=last_version,
            )

            # 6. Persistir filesystem
            target_dir = RELEASES_BASE / str(project_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"v{next_version}.zip"
            target_path.write_bytes(zip_bytes)

            # 7. UPDATE ready
            sha256 = hashlib.sha256(zip_bytes).hexdigest()
            release_row.status = "ready"
            release_row.file_path = str(target_path)
            release_row.file_size_bytes = len(zip_bytes)
            release_row.sha256 = sha256
            release_row.manifest_json = json.dumps(manifest_dict, ensure_ascii=False)
            release_row.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info(
                "release_bundle.created",
                project_id=str(project_id),
                version=next_version,
                size_bytes=len(zip_bytes),
                sha256_prefix=sha256[:8],
                readiness_pct=readiness_pct,
            )

            return {
                "id": str(release_row.id),
                "version": next_version,
                "status": "ready",
                "readiness_pct": readiness_pct,
                "file_path": str(target_path),
                "sha256": sha256,
                "size_bytes": len(zip_bytes),
            }

        except Exception as exc:  # noqa: BLE001
            release_row.status = "failed"
            release_row.error_message = f"{type(exc).__name__}: {exc}"[:500]
            release_row.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            logger.error(
                "release_bundle.failed",
                project_id=str(project_id),
                version=next_version,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return {
                "error": "bundle_generation_failed",
                "version": next_version,
                "message": str(exc),
            }

    # ──────────────────────────── list/get ──────────────────────────

    async def list_releases(self, project_id: UUID) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(ProjectRelease)
            .where(ProjectRelease.project_id == project_id)
            .order_by(ProjectRelease.version.desc())
        )
        rows = list(result.scalars().all())
        return [
            {
                "id": str(r.id),
                "version": r.version,
                "status": r.status,
                "readiness_pct": r.readiness_pct,
                "size_bytes": r.file_size_bytes,
                "sha256": r.sha256,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "error_message": r.error_message,
            }
            for r in rows
        ]

    async def get_release_path(self, project_id: UUID, version: int) -> Optional[str]:
        """Caminho do zip no filesystem (ou None). Retorna apenas se status='ready'
        e arquivo existe."""
        result = await self.db.execute(
            select(ProjectRelease).where(
                ProjectRelease.project_id == project_id,
                ProjectRelease.version == version,
            )
        )
        r = result.scalar_one_or_none()
        if not r or r.status != "ready" or not r.file_path:
            return None
        if not Path(r.file_path).exists():
            return None
        return r.file_path

    # ──────────────────────────── helpers de build ──────────────────

    async def _build_zip(
        self,
        project_id: UUID,
        project_name: str,
        version: int,
        deliverables_export: Dict[str, Any],
        ocg_data: Dict[str, Any],
        ocg_version: Optional[int],
        last_version: int,
    ) -> tuple[bytes, Dict[str, Any]]:
        """Monta o zip em memória e devolve (bytes, manifest_dict)."""
        manifest = self._build_manifest(
            project_name=project_name,
            version=version,
            deliverables_export=deliverables_export,
            ocg_version=ocg_version,
        )
        release_notes = await self._build_release_notes(
            project_id=project_id,
            project_name=project_name,
            version=version,
            last_version=last_version,
            ocg_version=ocg_version,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("RELEASE_NOTES.md", release_notes)
            zf.writestr(
                "deliverables_status.json",
                json.dumps(deliverables_export, ensure_ascii=False, indent=2),
            )
            if ocg_data:
                zf.writestr("ocg.json", json.dumps(ocg_data, ensure_ascii=False, indent=2))

            # docs/ do repo Git (best-effort — projetos sem Git config skipam)
            await self._add_git_docs(zf, project_id)

        return buf.getvalue(), manifest

    def _build_manifest(
        self,
        *,
        project_name: str,
        version: int,
        deliverables_export: Dict[str, Any],
        ocg_version: Optional[int],
    ) -> Dict[str, Any]:
        """Manifest estruturado: dados machine-readable da release."""
        deliverables = deliverables_export.get("deliverables", [])
        return {
            "project": project_name,
            "release_version": f"v{version}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ocg_version": ocg_version,
            "readiness_pct": deliverables_export["summary"]["readiness_pct"],
            "readiness_threshold": deliverables_export["summary"].get("readiness_threshold"),
            "summary": deliverables_export["summary"],
            "deliverables": [
                {
                    "name": d["name"],
                    "kind": d["kind"],
                    "category": d["category"],
                    "status": d["status"],
                    "evidence_type": d.get("evidence_type"),
                    "evidence_ref": d.get("evidence_ref"),
                    "verification_method": d.get("verification_method"),
                    "last_verified_at": d.get("last_verified_at"),
                }
                for d in deliverables
                if d["status"] != "waived"
            ],
        }

    async def _build_release_notes(
        self,
        *,
        project_id: UUID,
        project_name: str,
        version: int,
        last_version: int,
        ocg_version: Optional[int],
    ) -> str:
        """Gera RELEASE_NOTES.md a partir do diff de ocg_delta_log entre
        a release anterior e esta. Para v1, lista todas as mudanças do OCG.
        """
        # Busca delta_log entries desde última release (ou todas se v1)
        # Heurística: usar timestamp da última release como cutoff
        cutoff_at = None
        if last_version > 0:
            prev_result = await self.db.execute(
                select(ProjectRelease.created_at).where(
                    ProjectRelease.project_id == project_id,
                    ProjectRelease.version == last_version,
                ).limit(1)
            )
            cutoff_at = prev_result.scalar_one_or_none()

        delta_query = (
            select(OCGDeltaLog)
            .where(OCGDeltaLog.project_id == project_id)
            .order_by(OCGDeltaLog.created_at)
        )
        if cutoff_at:
            delta_query = delta_query.where(OCGDeltaLog.created_at > cutoff_at)
        deltas_res = await self.db.execute(delta_query)
        deltas = list(deltas_res.scalars().all())

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: List[str] = [
            f"# Release Notes — {project_name} v{version}",
            "",
            f"_Gerado em {now_iso}._",
            f"OCG version no momento da release: **{ocg_version or 'N/A'}**",
            "",
        ]
        if last_version > 0:
            lines.append(f"Mudanças desde release v{last_version}.")
        else:
            lines.append("Primeira release deste projeto.")
        lines.append("")

        if not deltas:
            lines.append("_Nenhuma mudança registrada no OCG no período._")
            return "\n".join(lines) + "\n"

        # Agrupa por trigger_source para visão executiva
        by_trigger: Dict[str, List[OCGDeltaLog]] = {}
        for d in deltas:
            by_trigger.setdefault(d.trigger_source or "unknown", []).append(d)

        lines.append(f"**Total de eventos**: {len(deltas)} ({len(by_trigger)} fontes distintas)")
        lines.append("")

        for trigger, group in by_trigger.items():
            lines.append(f"## {trigger.replace('_', ' ').title()} ({len(group)} eventos)")
            lines.append("")
            for d in group[:20]:  # limita pra não explodir o markdown
                ts = d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "?"
                summary = (d.change_summary or "")[:200]
                lines.append(f"- `{ts}` v{d.ocg_version_from} → v{d.ocg_version_to}: {summary}")
            if len(group) > 20:
                lines.append(f"- _(... e mais {len(group) - 20} eventos)_")
            lines.append("")

        return "\n".join(lines) + "\n"

    async def _add_git_docs(self, zf: zipfile.ZipFile, project_id: UUID) -> None:
        """Lê docs/* do repo Git e adiciona ao zip (best-effort).

        Falha de Git → log warning, segue sem docs (bundle ainda válido).
        """
        try:
            from app.services.git_service import GitService
            gs = GitService(project_id=None)  # type: ignore[arg-type]
            # GitService espera db; constrói correto:
            gs = GitService(self.db)
            items = await gs.list_files(project_id, "docs")
            if not items:
                return
            for item in items:
                if item.get("type") != "file":
                    continue
                path = item.get("path")  # docs/foo.md
                if not path:
                    continue
                content = await gs.get_file_content(project_id, path)
                if content is None:
                    continue
                zf.writestr(path, content)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "release_bundle.git_docs_skipped",
                project_id=str(project_id),
                error=str(exc),
            )
