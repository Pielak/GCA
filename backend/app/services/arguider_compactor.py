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
- Truncar campos de texto longo (analise, recomendacao, descricao, detalhe) dentro
  de cada finding para garantir que o prompt resultante caiba em < 8KB (Gate 2).
"""
from typing import Any, Dict, List


CRITICIDADE_ORDER = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}

# Campos de identificação/metadados preservados integralmente nos findings
_FINDING_CANONICAL_FIELDS = {"id", "criticidade", "source_persona", "score", "titulo"}

# Campos de texto longo que existem em findings — truncados para caber em 8KB
_FINDING_TEXT_FIELDS = {"analise", "recomendacao", "descricao", "detalhe"}

# Limite de chars para texto longo: imunes recebem um pouco mais de contexto
_MAX_TEXT_IMMUNE = 60   # chars para findings críticos/CONF-blocking
_MAX_TEXT_CANDIDATE = 40  # chars para findings normais

# Limite de chars para campos de texto em recomendações
_MAX_REC_TEXT = 80


def _compact_finding(f: Dict[str, Any], is_immune: bool) -> Dict[str, Any]:
    """Projeta finding para campos canônicos truncando texto longo.

    Campos canônicos (_FINDING_CANONICAL_FIELDS) são preservados integralmente
    (com títulos truncados a 60 chars). Campos de texto longo (_FINDING_TEXT_FIELDS)
    são truncados conforme imunidade. Campos desconhecidos/verbosos são descartados.

    Args:
        f: Finding original (não será mutado).
        is_immune: True para findings críticos ou CONF-blocking.

    Returns:
        Novo dict compactado.
    """
    max_text = _MAX_TEXT_IMMUNE if is_immune else _MAX_TEXT_CANDIDATE
    result: Dict[str, Any] = {}
    for key, val in f.items():
        if key in _FINDING_CANONICAL_FIELDS:
            # Título pode ser longo — truncar a 60 chars para consistência
            if isinstance(val, str) and len(val) > 60:
                result[key] = val[:60] + "..."
            else:
                result[key] = val
        elif key in _FINDING_TEXT_FIELDS:
            if isinstance(val, str) and len(val) > max_text:
                result[key] = val[:max_text] + "..."
            else:
                result[key] = val
        # Campos desconhecidos são descartados para manter o payload enxuto
    return result


def _compact_recommendation(rec: Any) -> Any:
    """Trunca campos de texto longos em uma recomendação.

    Args:
        rec: Recomendação — pode ser dict ou string.

    Returns:
        Recomendação com campos de texto truncados a _MAX_REC_TEXT chars.
    """
    if isinstance(rec, dict):
        result = {}
        for key, val in rec.items():
            if isinstance(val, str) and len(val) > _MAX_REC_TEXT:
                result[key] = val[:_MAX_REC_TEXT] + "..."
            else:
                result[key] = val
        return result
    if isinstance(rec, str) and len(rec) > _MAX_REC_TEXT:
        return rec[:_MAX_REC_TEXT] + "..."
    return rec


def compact_arguider_for_prompt(
    arguider_analysis: Dict[str, Any],
    max_findings: int = 20,
) -> Dict[str, Any]:
    """Reduz arguider_analysis preservando informação crítica dentro de < 8KB.

    Retorna novo dict (não muta o input). Findings críticos (criticidade='critica'
    ou de CONF com score<60) NUNCA são descartados. O payload resultante deve
    caber em < 8000 chars serializado (critério arquitetural Gate 2 — DT-081).

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

    # Combinar: imunes + top-K dos candidatos; compactar campos de texto em cada finding
    slots_remaining = max(0, max_findings - len(immune_findings))
    selected_findings = immune_findings + candidate_findings[:slots_remaining]
    compacted_findings = (
        [_compact_finding(f, is_immune=True) for f in immune_findings]
        + [_compact_finding(f, is_immune=False) for f in candidate_findings[:slots_remaining]]
    )
    findings_dropped = len(all_findings) - len(selected_findings)

    # 3. Truncar campos de texto nas recomendações
    recs_raw: List[Any] = (arguider_analysis.get("consolidated_recommendations") or [])[:10]
    compacted_recs = [_compact_recommendation(r) for r in recs_raw]

    # 4. Compor payload compactado
    compacted: Dict[str, Any] = {
        "overall_score": arguider_analysis.get("overall_score"),
        "blocked": arguider_analysis.get("blocked"),
        "blocking_reason": arguider_analysis.get("blocking_reason"),
        "personas_executed": arguider_analysis.get("personas_executed", []),
        "personas_failed": arguider_analysis.get("personas_failed", []),
        "personas_excluded_count": arguider_analysis.get("personas_excluded_count", 0),
        "ocg_individual_summary": ocg_individual_summary,  # sumarizado
        "ocg_global_delta": arguider_analysis.get("ocg_global_delta") or {},  # integral
        "consolidated_findings": compacted_findings,  # truncado por quantidade e tamanho
        "consolidated_recommendations": compacted_recs,  # truncado a top-10 com texto enxuto
        "_compactor_meta": {
            "findings_total": len(all_findings),
            "findings_kept": len(selected_findings),
            "findings_dropped": findings_dropped,
            "immune_findings": len(immune_findings),
        },
    }
    return compacted
