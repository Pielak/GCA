"""
Arguider Compactor — reduz arguider_analysis para tamanho processável por LLM.

DT-081 (MVP 32): payload n8n consolidado tem ~23KB com 9 personas + findings.
DeepSeek com prompt grande retorna JSON sem updated_ocg/changes.

Estratégia:
- Truncar consolidated_findings para top-K (K=20 default)
- Critério de prioridade: criticidade='critica' > 'alta' > 'media' > 'baixa'
- Findings de CONF com score<60 SEMPRE incluídos (regra de bloqueio canônica)
- Sumarizar ocg_individual: apenas score/approved/blocking/findings_count por persona
- Manter ocg_global_delta integral (já agregado, tamanho gerenciável)
"""
from typing import Any, Dict, List


CRITICIDADE_ORDER = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}


def compact_arguider_for_prompt(
    arguider_analysis: Dict[str, Any],
    max_findings: int = 20,
) -> Dict[str, Any]:
    """Reduz arguider_analysis preservando informação crítica.

    Retorna novo dict (não muta o input). Findings críticos (criticidade='critica'
    ou de CONF com score<60) NUNCA são descartados.

    Args:
        arguider_analysis: Dict com resultado completo do Arguidor (payload n8n).
        max_findings: Número máximo de findings no payload resultante (default 20).

    Returns:
        Dict compactado com metadados de compactação em '_compactor_meta'.
    """
    if not arguider_analysis:
        return {}

    # 1. Sumarizar ocg_individual: apenas campos canônicos por persona
    ocg_individual_summary = {}
    for tag, persona_output in (arguider_analysis.get("ocg_individual") or {}).items():
        if not isinstance(persona_output, dict):
            continue
        ocg_individual_summary[tag] = {
            "score": persona_output.get("score", persona_output.get("avg_score", 0)),
            "approved": persona_output.get("approved", False),
            "blocking": persona_output.get("blocking", False),
            "findings_count": len(persona_output.get("findings", []) or []),
        }

    # 2. Truncar findings por criticidade — críticos imunes
    all_findings: List[Dict[str, Any]] = arguider_analysis.get("consolidated_findings") or []

    # Separar imunes vs candidatos a corte
    immune_findings: List[Dict[str, Any]] = []
    candidate_findings: List[Dict[str, Any]] = []
    for f in all_findings:
        if not isinstance(f, dict):
            continue
        criticidade = str(f.get("criticidade", "")).lower()
        source_persona = str(f.get("source_persona", "")).upper()
        score = f.get("score", 0)
        # CONF blocking sempre imune (regra de bloqueio canônica §6.2)
        is_conf_blocking = (
            source_persona == "CONF"
            and isinstance(score, (int, float))
            and score < 60
        )
        if criticidade == "critica" or is_conf_blocking:
            immune_findings.append(f)
        else:
            candidate_findings.append(f)

    # Ordenar candidatos por criticidade (alta → baixa)
    candidate_findings.sort(
        key=lambda f: CRITICIDADE_ORDER.get(
            str(f.get("criticidade", "baixa")).lower(), 99
        )
    )

    # Combinar: imunes + top-K dos candidatos
    slots_remaining = max(0, max_findings - len(immune_findings))
    truncated_findings = immune_findings + candidate_findings[:slots_remaining]
    findings_dropped = len(all_findings) - len(truncated_findings)

    # 3. Compor payload compactado
    compacted: Dict[str, Any] = {
        "overall_score": arguider_analysis.get("overall_score"),
        "blocked": arguider_analysis.get("blocked"),
        "blocking_reason": arguider_analysis.get("blocking_reason"),
        "personas_executed": arguider_analysis.get("personas_executed", []),
        "personas_failed": arguider_analysis.get("personas_failed", []),
        "personas_excluded_count": arguider_analysis.get("personas_excluded_count", 0),
        "ocg_individual_summary": ocg_individual_summary,  # sumarizado
        "ocg_global_delta": arguider_analysis.get("ocg_global_delta") or {},  # integral
        "consolidated_findings": truncated_findings,  # truncado
        "consolidated_recommendations": (
            arguider_analysis.get("consolidated_recommendations") or []
        )[:10],  # top 10
        "_compactor_meta": {
            "findings_total": len(all_findings),
            "findings_kept": len(truncated_findings),
            "findings_dropped": findings_dropped,
            "immune_findings": len(immune_findings),
        },
    }
    return compacted
