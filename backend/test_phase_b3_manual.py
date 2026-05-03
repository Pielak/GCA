#!/usr/bin/env python3
"""Manual integration test for Phase B.3 — API endpoints."""
import asyncio
import requests
import json
from uuid import uuid4

BASE_URL = "http://localhost:8000/api/v1"

async def test_api_endpoints():
    """Test all Phase B.3 API endpoints."""
    print("=" * 60)
    print("PHASE B.3 INTEGRATION TEST — API Endpoints")
    print("=" * 60)

    # Test 1: Error handling — missing route_map
    print("\n[TEST 1] Error handling — missing route_map")
    fake_uuid = str(uuid4())
    response = requests.post(
        f"{BASE_URL}/gatekeeper/passada-1",
        json={"route_map_id": fake_uuid, "execute_now": True},
    )
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "DocumentRouteMap não encontrado" in response.text
    print("✓ PASS: 404 returned with correct error message")

    # Test 2: Error handling — get non-existent board
    print("\n[TEST 2] Error handling — get non-existent board")
    response = requests.get(
        f"{BASE_URL}/gatekeeper/personas-board/{fake_uuid}?passada=1"
    )
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "Nenhuma resposta de persona encontrada" in response.text
    print("✓ PASS: 404 returned with correct error message")

    # Test 3: Verify router is registered
    print("\n[TEST 3] Verify router is registered")
    response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/openapi.json")
    assert response.status_code == 200, f"OpenAPI endpoint returned {response.status_code}"
    api_spec = response.json()

    has_passada_1 = any("/gatekeeper/passada-1" in path for path in api_spec.get("paths", {}))
    has_board = any("/gatekeeper/personas-board/{route_map_id}" in path for path in api_spec.get("paths", {}))
    has_answers = any("/gatekeeper/human-answers" in path for path in api_spec.get("paths", {}))

    assert has_passada_1, "Endpoint POST /gatekeeper/passada-1 not found in OpenAPI spec"
    assert has_board, "Endpoint GET /gatekeeper/personas-board not found in OpenAPI spec"
    assert has_answers, "Endpoint POST /gatekeeper/human-answers not found in OpenAPI spec"

    print("✓ PASS: All 3 Gatekeeper endpoints registered")

    # Test 4: Verify models are created
    print("\n[TEST 4] Verify models exist")
    try:
        from app.models.gatekeeper_persona_response import GatekeeperPersonaResponse
        from app.models.human_answer import HumanAnswer
        print("✓ PASS: GatekeeperPersonaResponse model exists")
        print("✓ PASS: HumanAnswer model exists")
    except ImportError as e:
        print(f"✗ FAIL: {e}")
        return False

    # Test 5: Verify services exist
    print("\n[TEST 5] Verify services exist")
    try:
        from app.services.parallel_evaluator import ParallelEvaluator
        from app.services.personas.gp import GPPersona
        from app.services.personas.arq import ArchitectPersona
        from app.services.personas.dba import DBAPersona
        from app.services.personas.dev import DevPersona
        from app.services.personas.qa import QAPersona
        from app.services.personas.ux import UXPersona
        from app.services.personas.ui import UIPersona

        print("✓ PASS: ParallelEvaluator exists")
        print("✓ PASS: All 7 persona classes exist (gp, arq, dba, dev, qa, ux, ui)")
    except ImportError as e:
        print(f"✗ FAIL: {e}")
        return False

    # Test 6: Verify dataclasses
    print("\n[TEST 6] Verify dataclasses")
    try:
        from app.services.personas.base import PersonaScore, PersonaIssue, PersonaQuestion, PersonaOutput

        # Test PersonaScore
        score = PersonaScore(escopo=85, stack=72, dados=90)
        assert score.escopo == 85
        assert score.stack == 72
        assert score.dados == 90
        print("✓ PASS: PersonaScore dataclass works correctly")

        # Test PersonaOutput
        output = PersonaOutput(
            persona_tag="gp",
            passada=1,
            scores=score,
            approved=True,
            tentative=True,
        )
        assert output.persona_tag == "gp"
        assert output.passada == 1
        print("✓ PASS: PersonaOutput dataclass works correctly")
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False

    # Test 7: Test database schema
    print("\n[TEST 7] Test database schema")
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import text

        # Create async session for database check
        async with AsyncSessionLocal() as db:
            # Test GatekeeperPersonaResponse table
            result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'gatekeeper_persona_responses'"))
            if result.fetchone():
                print("✓ PASS: gatekeeper_persona_responses table exists")
            else:
                print("✗ FAIL: gatekeeper_persona_responses table not found")
                return False

            # Test HumanAnswer table
            result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'human_answers'"))
            if result.fetchone():
                print("✓ PASS: human_answers table exists")
            else:
                print("✗ FAIL: human_answers table not found")
                return False
    except Exception as e:
        print(f"✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_api_endpoints())
        exit(0 if success else 1)
    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
        exit(1)
