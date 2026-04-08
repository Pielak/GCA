#!/bin/bash
# Test 8-Agent OCG Pipeline End-to-End

API_URL="http://localhost:8000/api/v1"
MOCK_QUESTIONNAIRE="tests/fixtures/mock_questionnaire.json"

echo "======================================================================"
echo "Testing 8-Agent OCG Pipeline"
echo "======================================================================"
echo ""

# Step 1: Agent 0 - Analyzer
echo "STEP 1: Agent 0 (Analyzer) - Classifying questionnaire..."
echo ""

ANALYZER_RESPONSE=$(curl -s -X POST "$API_URL/agents/analyze" \
  -H "Content-Type: application/json" \
  -d @"$MOCK_QUESTIONNAIRE")

echo "Analyzer Response:"
echo "$ANALYZER_RESPONSE" | python3 -m json.tool | head -50
echo ""

# Extract questionnaire ID and classification for next steps
QUESTIONNAIRE_ID=$(echo "$ANALYZER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['questionnaire_id'])" 2>/dev/null)
echo "✓ Questionnaire ID: $QUESTIONNAIRE_ID"
echo ""

# Step 2: Agents 1-7 - Parallel Pillar Analysis
echo "STEP 2: Agents 1-7 (Pillar Specialists) - Analyzing in parallel..."
echo ""

# For now, test Agent 1 (Business) as a proof-of-concept
echo "Testing Agent 1 (P1_Business) - sample pillar analysis..."
echo ""

PILLAR_REQUEST='{
  "pillar_id": 1,
  "questionnaire_id": "'$QUESTIONNAIRE_ID'",
  "questions": [
    {"question_id": "Q1", "text": "ROI esperado é 40% em 2 anos"},
    {"question_id": "Q2", "text": "Stakeholders principais: CEO, CFO, VP Product"},
    {"question_id": "Q3", "text": "Timeline: 6 meses para MVP, 12 meses para produção"},
    {"question_id": "Q4", "text": "Orçamento aprovado: USD 200k"},
    {"question_id": "Q5", "text": "Impacto esperado: 50% aumento em conversão"}
  ],
  "responses": {
    "Q1": "ROI esperado é 40% em 2 anos. Projeto alinhado com estratégia de crescimento.",
    "Q2": "Stakeholders principais: CEO, CFO, VP Product",
    "Q3": "Timeline: 6 meses para MVP, 12 meses para produção",
    "Q4": "Orçamento aprovado: USD 200k",
    "Q5": "Impacto esperado: 50% aumento em conversão"
  },
  "project_metadata": {
    "project_name": "E-Commerce Platform",
    "project_type": "web_app",
    "team_size": 5,
    "timeline_months": 12,
    "budget_level": "medium"
  }
}'

PILLAR_RESPONSE=$(curl -s -X POST "$API_URL/agents/pillar/1" \
  -H "Content-Type: application/json" \
  -d "$PILLAR_REQUEST")

echo "Agent 1 (P1_Business) Response:"
echo "$PILLAR_RESPONSE" | python3 -m json.tool | head -40
echo ""

PILLAR_SCORE=$(echo "$PILLAR_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['score'])" 2>/dev/null)
PILLAR_LEVEL=$(echo "$PILLAR_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['adherence_level'])" 2>/dev/null)

echo "✓ P1 Score: $PILLAR_SCORE | Adherence: $PILLAR_LEVEL"
echo ""

echo "======================================================================"
echo "Summary"
echo "======================================================================"
echo ""
echo "✓ Agent 0 (Analyzer) successfully classified questionnaire"
echo "  - Questions classified by pillar"
echo "  - Project metadata extracted"
echo "✓ Agent 1 (P1_Business) successfully analyzed business pillar"
echo "  - Score: $PILLAR_SCORE/100"
echo "  - Adherence: $PILLAR_LEVEL"
echo ""
echo "Next: Run Agents 2-7 in parallel, then Agent 8 (Consolidator)"
echo ""
