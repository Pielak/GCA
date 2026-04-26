"""
M01 Service — Questionnaire Generator from Requirements Document
Reads requirements document, extracts context, generates dynamic 30-50 questions to fill gaps
"""

from typing import List, Dict, Optional
import json
from dataclasses import dataclass
from anthropic import Anthropic

# ============================================================================
# SCHEMAS
# ============================================================================

@dataclass
class Question:
    """Individual question in generated questionnaire"""
    id: str  # "M01_Q1", "M01_Q2", etc
    text: str
    tipo: str  # "aberta" (open) | "escolha" (choice) | "multipla" (multiple)
    opcoes: Optional[List[str]] = None  # If tipo is "escolha" or "multipla"
    obrigatoria: bool = True
    dica: Optional[str] = None


@dataclass
class GeneratedQuestionnaire:
    """Complete questionnaire output from M01"""
    questions: List[Question]
    count: int
    iteration_id: str  # Unique ID to track this questionnaire generation
    document_domain: str  # e.g., "software", "juridico", "financeiro"
    extracted_concepts: List[str]  # Key concepts extracted from document
    gaps_identified: List[str]  # Gaps/ambiguities M01 detected


# ============================================================================
# M01 PROMPTS
# ============================================================================

M01_SYSTEM_PROMPT = """You are M01 (Questionnaire Generator) for the GCA system.

CRITICAL: ALL output (descriptions, question texts, options) MUST be in Brazilian Portuguese (pt-BR).
JSON keys remain in English.

Your role:
1. Read a requirements document (project spec, RFP, architecture doc, etc)
2. Extract domain, context, technology hints
3. Identify GAPS and AMBIGUITIES (things not clearly defined)
4. Generate 30-50 targeted questions to fill those gaps

QUESTION QUALITY RULES:
- Each question addresses ONE specific gap
- Open questions (aberta) for context/strategy/risk
- Choice questions (escolha) for standard options (stack, architecture pattern, etc)
- Multiple questions (multipla) for features, integrations, requirements
- Every question must be answerable from project context OR require expert judgment

OUTPUT FORMAT (valid JSON):
{
  "questions": [
    {
      "id": "M01_Q1",
      "text": "Qual é o objetivo principal do projeto?",
      "tipo": "aberta",
      "opcoes": null,
      "obrigatoria": true,
      "dica": "Descreva em 1-2 frases o problema que o projeto resolve"
    },
    {
      "id": "M01_Q2",
      "text": "Qual é a criticidade do projeto?",
      "tipo": "escolha",
      "opcoes": ["Baixa (prototipo, MVP)", "Média (produção, <= 1000 users)", "Alta (produção, >1000 users, compliance crítico)"],
      "obrigatoria": true,
      "dica": null
    }
  ],
  "extracted_concepts": ["concept1", "concept2", ...],
  "gaps_identified": ["gap1", "gap2", ...],
  "total_questions": 42
}
"""

M01_USER_PROMPT_TEMPLATE = """You are analyzing a requirements document for project/initiative. Extract context and generate targeted questions.

**DOCUMENT METADATA**
- Domain: {domain}
- Document type: {doc_type}
- Length: {word_count} words

**DOCUMENT CONTENT**
{document_text}

**YOUR TASK**
1. Summarize the 3-5 main topics in this document
2. Identify 8-12 GAPS/AMBIGUITIES (things NOT clearly specified)
3. Generate 30-50 questions that:
   - Fill the identified gaps
   - Clarify assumptions
   - Validate architecture/design decisions
   - Probe compliance, security, scalability needs
   - Are answerable by technical/business stakeholders

**QUESTION DISTRIBUTION GUIDANCE**
- 5-7 questions: Business & Scope (project goal, criticality, timeline, budget)
- 5-7 questions: Architecture & Stack (technology choices, patterns, integrations)
- 5-7 questions: Data & Persistence (databases, caching, messaging, replication)
- 5-7 questions: Security & Compliance (auth, encryption, LGPD, certifications)
- 5-7 questions: Non-Functional (performance, availability, scalability, observability)
- 5-7 questions: Team & Process (team size, experience, tools, CI/CD, testing)
- Optional 0-5 questions: Domain-specific (e.g., for legal: jurisdiction, contracts; for finance: regulations, audit)

**RESPONSE** (must be valid JSON, no markdown code fence):"""

# ============================================================================
# M01SERVICE
# ============================================================================

class M01Service:
    """Questionnaire Generator from Requirements Documents"""

    def __init__(self, anthropic_client: Anthropic = None):
        """
        Initialize M01 service

        Args:
            anthropic_client: Anthropic client instance. If None, creates new instance.
        """
        self.client = anthropic_client or Anthropic()
        self.model = "claude-sonnet-4-6-20250514"  # Use Sonnet 4.6 as per decision

    def generate_questionnaire(
        self,
        document_text: str,
        domain: str = "software",
        doc_type: str = "requirements",
        iteration_id: str = None
    ) -> GeneratedQuestionnaire:
        """
        Read requirements document and generate dynamic questionnaire

        Args:
            document_text: Full text content of requirements document
            domain: Domain context (software, juridico, financeiro, etc)
            doc_type: Type of document (requirements, RFP, spec, proposal, etc)
            iteration_id: Optional unique ID for this questionnaire. If not provided, generates one.

        Returns:
            GeneratedQuestionnaire with 30-50 questions

        Raises:
            ValueError: If document is too short or invalid
            anthropic.APIError: If API call fails
        """

        # Validate input
        if not document_text or len(document_text.strip()) < 200:
            raise ValueError("Document must be at least 200 characters")

        # Generate iteration ID if not provided
        if not iteration_id:
            import uuid
            iteration_id = f"m01_{uuid.uuid4().hex[:8]}"

        # Truncate to ~10K chars if too long (save tokens)
        if len(document_text) > 10000:
            document_text = document_text[:10000] + "\n\n[... documento truncado ...]"

        word_count = len(document_text.split())

        # Build user prompt
        user_prompt = M01_USER_PROMPT_TEMPLATE.format(
            domain=domain,
            doc_type=doc_type,
            word_count=word_count,
            document_text=document_text
        )

        # Call Claude to generate questionnaire
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=M01_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response
        response_text = message.content[0].text

        # Try to extract JSON from response
        try:
            # Handle case where Claude wraps in markdown
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse Claude response as JSON: {response_text[:200]}")

        # Convert to Question objects
        questions = []
        for q_data in parsed.get("questions", []):
            q = Question(
                id=q_data.get("id", f"M01_Q{len(questions)+1}"),
                text=q_data["text"],
                tipo=q_data.get("tipo", "aberta"),
                opcoes=q_data.get("opcoes"),
                obrigatoria=q_data.get("obrigatoria", True),
                dica=q_data.get("dica")
            )
            questions.append(q)

        # Validate question count
        if len(questions) < 30:
            raise ValueError(f"Generated only {len(questions)} questions, need >= 30")
        if len(questions) > 50:
            # Trim to 50
            questions = questions[:50]

        return GeneratedQuestionnaire(
            questions=questions,
            count=len(questions),
            iteration_id=iteration_id,
            document_domain=domain,
            extracted_concepts=parsed.get("extracted_concepts", []),
            gaps_identified=parsed.get("gaps_identified", [])
        )


# ============================================================================
# HELPER FUNCTION
# ============================================================================

def create_m01_service() -> M01Service:
    """Factory function to create M01Service with default Anthropic client"""
    return M01Service()
