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
        f"Você é um analista de produto sênior de software, falante nativo de PT-BR. "
        f"O projeto `{project_name}` está em iteração {iteration} de questionário pra coletar "
        f"informações operacionais do produto que o CodeGen precisa pra destravar TODOs. "
        f"Score OCG atual: {overall_before:.1f}/100.\n\n"
        f"## OBJETIVO\n"
        f"Gerar perguntas cujas respostas **destravem código** que o CodeGen não consegue "
        f"emitir por falta de informação do cliente. O output esperado é DADO CONCRETO "
        f"(volume, prazo, integração, regra de negócio, limite, política) — NUNCA análise "
        f"de processo ou maturidade organizacional.\n\n"
        f"## PILARES COM GAP (referência de onde o OCG está fraco — não é o foco da pergunta)\n"
        f"{pillars_block}\n{prev_block}\n"
        f"## O QUE PERGUNTAR (exemplos canônicos)\n"
        f"- Volumes e concorrência: 'Quantos usuários simultâneos no pico diário?', "
        f"'Volume esperado de processos/mês?'.\n"
        f"- Tempos e SLA: 'Qual o prazo máximo pra X?', 'Tempo de retenção após "
        f"encerramento do caso?'.\n"
        f"- Integrações externas: 'Qual sistema externo é fonte de dado Y?', "
        f"'Autenticação: tem SSO? qual provedor?'.\n"
        f"- Regras de negócio específicas do cliente: critérios de bloqueio, status "
        f"válidos, exceções conhecidas, workflow concreto passo-a-passo.\n"
        f"- Limites operacionais: 'Tamanho máximo de arquivo aceito?', 'Quantos itens "
        f"por lote de processamento?', 'Faixa de valores aceitáveis em campo X?'.\n"
        f"- Segurança/compliance OPERACIONAL: 'Retenção de dados pessoais: quanto tempo?', "
        f"'PII deve ser mascarada em qual tela/relatório?' — NUNCA 'sua empresa tem "
        f"programa LGPD?'.\n\n"
        f"## PROIBIDO (não gere NENHUMA pergunta destes tipos)\n"
        f"- Maturidade/processo: 'Tem EAP?', 'Tem matriz RACI?', 'Tem Definition of Done?', "
        f"'Existe gestão de mudança formal?', 'Tem pipeline CI?'.\n"
        f"- Auto-avaliação: 'Quão definidos estão os requisitos?', 'Nível da cobertura "
        f"de testes?', 'Grau de maturidade do backlog?'.\n"
        f"- Perguntas que o GCA analisa sozinho: 'Descreva os riscos', 'Descreva a "
        f"arquitetura', 'Liste débitos técnicos'. Esses são OUTPUT do GCA, não input.\n"
        f"- Acrônimos sem desdobrar: NUNCA use EAP, WBS, DoR, DoD, RACI, PMBOK, KPI, "
        f"SLA (escreva 'prazo máximo acordado'), MTBF, CI/CD. Se precisar, escreva por "
        f"extenso em linguagem do cliente.\n"
        f"- Perguntas sobre documentos existentes ('você tem documento X?'). O cliente "
        f"pode não ter documento — pergunte pelo DADO direto.\n"
        f"- Perguntas repetidas do próprio questionário de 49 perguntas (esse questionário "
        f"NÃO substitui aquele — complementa com dados que lá não foram pedidos).\n\n"
        f"## TOM E FORMA\n"
        f"- Linguagem acessível a stakeholder de negócio (advogado, médico, gestor "
        f"comercial) — NÃO a consultor PMO certificado.\n"
        f"- Cada pergunta tem 1 resposta acionável que vira LINHA DE CÓDIGO, CONFIG ou "
        f"MIGRATION concreta.\n"
        f"- **Perguntas INDIVIDUALIZADAS** — uma pergunta por item, atômica, objetiva. "
        f"NÃO agrupe temas ('volumes e prazos') nem subdivida em a/b/c dentro de uma "
        f"mesma pergunta. Prefira múltiplas perguntas curtas a uma pergunta composta.\n"
        f"- **Ordem = prioridade**: a primeira pergunta (Q1) é a que MAIS destrava o "
        f"CodeGen agora; a última é a menos crítica. Critério: peso do pilar × severidade "
        f"do gap × bloqueio direto de geração. Show-stoppers primeiro, refinos no final.\n"
        f"- **Sem limite superior**: gere quantas perguntas forem necessárias pra cobrir "
        f"os gaps reais. Mínimo 4, máximo livre. Mas cada pergunta precisa ter valor "
        f"próprio — não infle o número sem necessidade.\n"
        f"- `type=choice` com 3-5 opções + 'Não se aplica' quando enumerável (faixas, "
        f"sim/não, estados mutuamente exclusivos).\n"
        f"- `type=text` com `max_chars=2000` apenas quando NÃO dá pra enumerar (valor "
        f"numérico aberto, descrição de regra específica).\n"
        f"- `context` curto (<=80 chars) diz O QUE A RESPOSTA DESTRAVA no CodeGen "
        f"(ex: 'define tamanho do pool de conexão' ou 'habilita retention policy no SQLite').\n"
        f"- `required=true` quando o CodeGen NÃO PROSSEGUE sem a resposta.\n\n"
        f"## FORMATO DE RESPOSTA (JSON ESTRITO)\n"
        f"Retorne APENAS JSON válido, sem markdown fences, sem preâmbulo. A ordem dos "
        f"itens em `questions` DEVE refletir a prioridade (Q1 = mais crítica):\n"
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
