"""M01 — builder de prompt pra gerador de questões iterativas.

Função pura (sem I/O) que consome:
- lista de pilares com score < 75 do OCG corrente
- gaps do Arguidor (module_candidates ou gatekeeper_items) por pilar
- iteração atual + overall anterior

Retorna prompt texto pronto pra `LLMServiceFactory.call_llm` do projeto
(respeita §6.2 — zero hardcode de provider/modelo).

Formato de resposta esperado do LLM:
```json
{
  "questions": [
    {
      "id": "Q1", "type": "choice|text", "text": "...",
      "context": "P3_scope gap 20%", "pillar": "P3_scope",
      "required": true,
      "options": ["...", "..."]  // só se type=choice
    }
  ]
}
```
"""
from __future__ import annotations

import json
from typing import Any

_PILLAR_LABELS_PT = {
    "P1_business_case": "Caso de Negócio",
    "P2_business_model": "Modelo de Negócio",
    "P3_scope": "Escopo",
    "P4_quality": "Qualidade",
    "P5_ux": "Experiência do Usuário",
    "P6_legal": "Jurídico & Compliance",
    "P7_security": "Segurança",
}


def build_iterative_prompt(
    *,
    project_name: str,
    iteration: int,
    overall_before: float,
    target_pillars_scores: dict[str, float],
    arguider_gaps_by_pillar: dict[str, list[dict[str, Any]]],
    previous_iteration_feedback: str | None = None,
) -> str:
    """Monta prompt pra geração de 4-7 perguntas focadas.

    Args:
        target_pillars_scores: {"P3_scope": 55.0, "P4_quality": 68.0, ...}
        arguider_gaps_by_pillar: {"P3_scope": [{"name": "...", "severity": "..."}], ...}
        previous_iteration_feedback: resumo curto do que ficou incompleto na iter N-1.
    """
    pillars_block_parts = []
    for pillar, score in target_pillars_scores.items():
        label = _PILLAR_LABELS_PT.get(pillar, pillar)
        gaps = arguider_gaps_by_pillar.get(pillar, [])
        gaps_sample = json.dumps(gaps[:5], ensure_ascii=False)[:800]
        pillars_block_parts.append(
            f"- **{pillar}** ({label}) — score {score:.1f}/100\n"
            f"  Gaps identificados pelo Arguidor: {gaps_sample}"
        )
    pillars_block = "\n".join(pillars_block_parts) or "(nenhum pilar específico listado)"

    prev_block = ""
    if previous_iteration_feedback:
        prev_block = (
            f"\n## RESULTADO DA ITERAÇÃO ANTERIOR\n"
            f"{previous_iteration_feedback[:1000]}\n"
            f"Priorize questões que o usuário consiga responder desta vez.\n"
        )

    return (
        f"Você é um analista de governança de software sênior, falante nativo de PT-BR. "
        f"O projeto `{project_name}` está em iteração {iteration} de questionário customizado. "
        f"Score OCG atual: {overall_before:.1f}/100. Meta: ≥90.\n\n"
        f"## PILARES DEFICITÁRIOS (score < 75)\n{pillars_block}\n{prev_block}\n"
        f"## TAREFA\n"
        f"Gere 4 a 7 perguntas OBJETIVAS que um GP do projeto possa responder pra fechar "
        f"OS GAPS ACIMA. Cada pergunta:\n"
        f"  - Aponta pra UM pilar específico (campo `pillar` com o código P1..P7).\n"
        f"  - `type=choice` com 3-5 opções incluindo 'Não se aplica' quando a resposta "
        f"pode ser enumerada (estado/percentual/sim-não).\n"
        f"  - `type=text` com `max_chars=2000` quando exige descrição.\n"
        f"  - `context` curto (<=80 chars) citando o código do pilar + % de gap.\n"
        f"  - `required=true` quando o gap é show-stopper; `false` quando é informacional.\n"
        f"NÃO faça perguntas genéricas. Se não há gap claro num pilar, NÃO pergunte sobre ele.\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown fences, sem preâmbulo:\n"
        f'{{"questions": [{{"id": "Q1", "type": "choice|text", "text": "<até 220 chars>", '
        f'"context": "<até 80 chars>", "pillar": "P1_business_case|...|P7_security", '
        f'"required": true, "options": ["Opção 1", "Opção 2", "Não se aplica"]}}, ...]}}'
    )


def parse_iterative_response(raw_text: str) -> dict[str, Any]:
    """Parse tolerante da resposta do LLM. Remove fences MD se houver."""
    import re
    stripped = raw_text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", stripped, re.DOTALL)
    if m:
        stripped = m.group(1).strip()
    data = json.loads(stripped)
    qs = data.get("questions") or []
    if not isinstance(qs, list):
        raise ValueError("Campo 'questions' precisa ser lista")
    clean = []
    for i, q in enumerate(qs):
        if not isinstance(q, dict) or not q.get("text"):
            continue
        clean.append({
            "id": q.get("id") or f"Q{i+1}",
            "type": "choice" if q.get("type") == "choice" else "text",
            "text": str(q["text"])[:220],
            "context": str(q.get("context") or "")[:80],
            "pillar": q.get("pillar") or "",
            "required": bool(q.get("required", False)),
            "options": list(q.get("options") or []) if q.get("type") == "choice" else None,
            "max_chars": 2000 if q.get("type") != "choice" else None,
        })
    return {"questions": clean}
