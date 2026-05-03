"""
Technical Questionnaire Service — Lógica de visibilidade dinâmica e validação cruzada

Funções para:
1. Calcular quais perguntas são visíveis baseado em respostas atuais
2. Validar conflitos lógicos (se Q3=Não, Q7-14 devem estar vazios)
3. Calcular progresso baseado apenas em perguntas visíveis
"""
from typing import Dict, List, Any, Set
import structlog

logger = structlog.get_logger(__name__)


def calculate_visibility(responses: Dict[str, Any], schema: List[Dict[str, Any]]) -> List[str]:
    """
    Calcula quais perguntas são visíveis baseado em respostas atuais.

    Algoritmo:
    1. Q sempre visível se visibleIf = []
    2. Q visível se TODAS as condições em visibleIf são satisfeitas
       - Condição: resposta de pergunta pai == valor esperado
    3. Retorna lista de números de perguntas visíveis (["Q1", "Q2", ...])
    """
    visible = set()

    for question in schema:
        numero = question["numero"]
        visible_if = question.get("visibleIf", [])

        # Se não há condições, sempre visível
        if not visible_if:
            visible.add(numero)
            continue

        # Verificar se todas as condições são satisfeitas
        all_conditions_met = True
        for condition in visible_if:
            depends_on = condition["dependsOn"]
            expected_value = condition["valor"]

            # Se a pergunta pai não foi respondida, não aparecer
            if depends_on not in responses:
                all_conditions_met = False
                break

            # Verificar se a resposta coincide (para strings e listas)
            actual_value = responses[depends_on]
            if isinstance(actual_value, list):
                # Se é lista, verificar se o valor está na lista
                if expected_value not in actual_value:
                    all_conditions_met = False
                    break
            else:
                # Se é string, verificar igualdade
                if str(actual_value) != expected_value:
                    all_conditions_met = False
                    break

        if all_conditions_met:
            visible.add(numero)

    return sorted(list(visible))


def prune_orphan_responses(
    responses: Dict[str, Any], schema: List[Dict[str, Any]]
) -> tuple[Dict[str, Any], List[str]]:
    """MVP 35 fix: remove respostas órfãs (campos não-visíveis com valor).

    Quando GP muda Q3 de "Sim, agressivo" para "Sim, modesto", as perguntas
    Q9/Q10 deixam de ser visíveis na UI — mas seus valores antigos
    permanecem em responses. validate_questionnaire detecta como conflito
    "Q9 deve estar vazio pois Q3=Sim, modesto", mas GP não consegue
    corrigir porque o campo não é mais editável.

    Solução canônica: ao salvar, qualquer resposta cuja pergunta NÃO esteja
    visível é removida. Auto-correção transparente. Estado responses sempre
    consistente com visibilidade dinâmica.

    Retorna (responses limpas, lista de campos órfãos removidos).
    """
    visible = set(calculate_visibility(responses, schema))
    pruned: Dict[str, Any] = {}
    removed: List[str] = []
    for key, value in responses.items():
        # Permite chaves auxiliares (Qx_outros) que pertencem a Qx visível
        base_key = key.split("_")[0] if "_" in key else key
        if base_key in visible:
            pruned[key] = value
        else:
            removed.append(key)
    return pruned, removed


def calculate_progress(responses: Dict[str, Any], schema: List[Dict[str, Any]]) -> int:
    """
    Calcula progresso baseado apenas em perguntas visíveis.

    Algoritmo:
    1. Calcular perguntas visíveis com calculate_visibility()
    2. Contar quantas perguntas visíveis obrigatórias estão preenchidas
    3. progress = (preenchidas / visíveis_obrigatórias) * 100

    Retorna: 0-100 (percentual)
    """
    visible = calculate_visibility(responses, schema)

    # Filtrar apenas perguntas visíveis e obrigatórias
    visible_required = [
        q for q in schema
        if q["numero"] in visible and q.get("obrigatoria", True)
    ]

    if not visible_required:
        return 100  # Se nenhuma obrigatória é visível, 100%

    # Contar preenchidas
    preenchidas = 0
    for question in visible_required:
        numero = question["numero"]
        if numero in responses and responses[numero]:
            preenchidas += 1

    progress = int((preenchidas / len(visible_required)) * 100)
    return min(progress, 100)  # Garantir máximo 100%


def validate_questionnaire(
    responses: Dict[str, Any],
    schema: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Valida questionário para conflitos lógicos e progresso.

    Validações:
    1. Visibilidade condicional: se Q3="Não", Q7-14 devem estar vazios
    2. Progresso mínimo: >= 80% para poder submeter
    3. Campos obrigatórios visíveis: todos preenchidos

    Retorna:
    {
        "is_valid": bool,
        "progress": int (0-100),
        "conflicts": ["mensagem de erro 1", "mensagem de erro 2", ...]
    }
    """
    conflicts = []
    visible = calculate_visibility(responses, schema)
    progress = calculate_progress(responses, schema)

    # 1. Validação de Conflitos Lógicos (revela/visibleIf)
    for question in schema:
        numero = question["numero"]
        revela = question.get("revela", [])

        # Se esta pergunta "revela" outras, validar que elas estão corretas
        if revela and numero in responses:
            # Pergunta pai foi respondida
            parent_value = responses[numero]

            for child_numero in revela:
                # Encontrar pergunta filha
                child_q = None
                for q in schema:
                    if q["numero"] == child_numero:
                        child_q = q
                        break

                if not child_q:
                    continue

                # Verificar se filho deveria estar visível
                child_visible_if = child_q.get("visibleIf", [])
                if not child_visible_if:
                    # Sem condição, filho é sempre visível — skip
                    continue

                # Checar se a resposta do pai permite o filho ser visível
                child_should_be_visible = any(
                    condition["dependsOn"] == numero and condition["valor"] in [parent_value]
                    if isinstance(parent_value, (str, int))
                    else condition["dependsOn"] == numero and condition["valor"] in parent_value
                    for condition in child_visible_if
                )

                # Se filho não deveria estar visível mas foi preenchido, erro
                if not child_should_be_visible and child_numero in responses and responses[child_numero]:
                    parent_str = str(parent_value)
                    conflicts.append(
                        f"{child_numero} deve estar vazio pois {numero}={parent_str}"
                    )

    # 2. Validação de Campos Obrigatórios Visíveis
    for question in schema:
        numero = question["numero"]
        if numero not in visible:
            continue  # Campo não visível, skip

        if not question.get("obrigatoria", True):
            continue  # Campo opcional, skip

        # Campo obrigatório e visível: deve estar preenchido
        if numero not in responses or not responses[numero]:
            conflicts.append(f"{numero} é obrigatório e deve ser preenchido")

    # 3. Verificar progresso mínimo
    # (Não é conflito, mas informação importante)

    is_valid = len(conflicts) == 0

    return {
        "is_valid": is_valid,
        "progress": progress,
        "conflicts": conflicts,
    }
