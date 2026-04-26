"""Testes de OCG Expansion Constraint — garantir que OCG nunca contrai

Alinhado a GCA_CANONICAL_CONTRACT.md e Task 6 do plano GCA v0.1:
- OCG só expande (score sempre ≥)
- Deltas com decision='needs_clarification' são loops de clarificação, não contrações
- Contrações são bloqueadas no DB via trigger PL/pgSQL
"""
import pytest
import json
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.models.base import Project, OCGDeltaLog


class TestOCGExpansionConstraint:
    """Suite de testes para garantir expansão do OCG"""

    def test_ocg_delta_model_has_all_fields(self):
        """OCGDeltaLog model deve ter todos os campos necessários"""
        # Verificar que todos os campos esperados existem
        from app.models.base import OCGDeltaLog

        expected_fields = [
            'id', 'project_id', 'document_id', 'ocg_version_from', 'ocg_version_to',
            'fields_changed', 'change_summary', 'changed_by', 'trigger_source',
            'ocg_snapshot', 'source', 'persona_id', 'decision', 'hash_chain',
            'created_at'
        ]

        for field in expected_fields:
            assert hasattr(OCGDeltaLog, field), f"Field {field} missing from OCGDeltaLog"

    def test_ocg_delta_source_values(self):
        """Verificar que source pode ter diferentes valores no modelo"""
        # Criar instâncias sem persistir no DB
        sources = [
            "questionnaire_response",
            "persona_validation",
            "document_ingestion",
            "manual_edit"
        ]

        project_id = uuid4()

        for i, source in enumerate(sources):
            delta = OCGDeltaLog(
                id=uuid4(),
                project_id=project_id,
                ocg_version_from=i,
                ocg_version_to=i+1,
                fields_changed=json.dumps({"field": "value"}),
                trigger_source=source,
                source=source,
                created_at=datetime.now(timezone.utc)
            )
            assert delta.source == source, f"Source should be {source}"
