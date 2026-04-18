"""DT-046: re-aplica fallback determinístico ao OCG real do projeto.

Sem gasto de LLM: lê o OCG atual, detecta STACK_RECOMMENDATION/
ARCHITECTURE_OVERVIEW vazios, reconstitui via helpers e grava delta.

Rodar dentro do container gca-backend:
    docker exec gca-backend python /host_scripts/dt046_reconsolidate_real_ocg.py <project_id>
"""
import sys
import json
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from app.db.database import AsyncSessionLocal
from app.services.agent_service import AgentService


async def main(project_id_str: str) -> None:
    project_id = UUID(project_id_str)

    async with AsyncSessionLocal() as db:
        # 1. Buscar OCG mais recente do projeto
        result = await db.execute(
            text("""
                SELECT id, ocg_data, version
                FROM ocg
                WHERE project_id = :pid
                ORDER BY version DESC
                LIMIT 1
            """),
            {"pid": project_id},
        )
        row = result.fetchone()
        if not row:
            print(f"[ERRO] Nenhum OCG encontrado para project {project_id}")
            return

        ocg_id, ocg_data_raw, version = row
        ocg_data = json.loads(ocg_data_raw)

        profile = ocg_data.get("PROJECT_PROFILE", {})
        print(f"[OCG] id={ocg_id} version={version}")

        # Campos com fallback DT-046 + DT-047
        fallbacks = [
            ("STACK_RECOMMENDATION", AgentService._stack_from_metadata, (profile,)),
            ("ARCHITECTURE_OVERVIEW", AgentService._architecture_from_metadata, (profile,)),
            ("TESTING_REQUIREMENTS", AgentService._testing_from_metadata, (profile,)),
            ("COMPLIANCE_CHECKLIST", AgentService._compliance_from_metadata, (profile,)),
            ("DELIVERABLES", AgentService._deliverables_from_metadata, (profile,)),
            ("RISK_ANALYSIS", AgentService._risk_from_metadata, (profile, None)),
        ]

        changed_fields = []
        for field, helper, args in fallbacks:
            current = ocg_data.get(field)
            is_empty = current in (None, {}, [])
            status = "<vazio>" if is_empty else "presente"
            print(f"[ANTES] {field}={status}")
            if is_empty:
                ocg_data[field] = helper(*args)
                changed_fields.append(field)
                print(f"[FIX]   {field} reconstituído via fallback")

        if not changed_fields:
            print("[NOOP] OCG já tem todos os campos populados; nada a fazer.")
            return

        # 2. Salvar o OCG atualizado + gravar delta DT-046
        await db.execute(
            text("""
                UPDATE ocg
                SET ocg_data = :data,
                    updated_at = :now
                WHERE id = :oid
            """),
            {
                "data": json.dumps(ocg_data, ensure_ascii=False),
                "now": datetime.now(timezone.utc),
                "oid": ocg_id,
            },
        )

        fields_updated = changed_fields

        await db.execute(
            text("""
                INSERT INTO ocg_delta_log (
                    id, project_id, ocg_version_from, ocg_version_to,
                    fields_changed, change_summary, trigger_source, created_at
                ) VALUES (
                    gen_random_uuid(), :pid, :fv, :tv,
                    :fields, :summary, 'dt046_deterministic_fallback', :now
                )
            """),
            {
                "pid": project_id,
                "fv": version,
                "tv": version,  # mesma versão; fallback apenas preenche campos vazios
                "fields": json.dumps(fields_updated, ensure_ascii=False),
                "summary": "DT-046: STACK_RECOMMENDATION/ARCHITECTURE_OVERVIEW reconstituídos a partir do PROJECT_PROFILE via fallback determinístico (contrato §5 — OCG não pode ter defaults invisíveis).",
                "now": datetime.now(timezone.utc),
            },
        )

        await db.commit()
        print(f"[OK] OCG {ocg_id} atualizado. Delta gravado em ocg_delta_log.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python dt046_reconsolidate_real_ocg.py <project_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
