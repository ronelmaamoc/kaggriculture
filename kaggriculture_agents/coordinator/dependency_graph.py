"""
dependency_graph.py — Vérification DÉFENSIVE des dépendances d'un Plan déjà approuvé.

Important (spec sections 10, 26) : le CoordinatorAgent NE RECALCULE PAS les
phases à partir de zéro. `PlanStep.phase` est déjà la sortie validée de
PlannerAgent (ordre topologique + capacité workers, voir
kaggriculture_agents/planner/agent.py) et déjà revérifiée par CriticAgent
(analyze_dependencies). Ce module ne fait donc QUE de la vérification en
profondeur ("defense in depth") : un plan APPROVED ne devrait jamais
déclencher ces fonctions, mais si une incohérence existe malgré tout entre
agents, le Coordinator doit la détecter plutôt que de produire un schedule
silencieusement incorrect (spec section 24, "détecter une incohérence entre
les agents").
"""

from typing import Dict, List, Sequence, Set, Tuple


def build_graph(steps: Sequence) -> Dict[str, Tuple[str, ...]]:
    """step_id -> tuple des step_id dont il dépend (PlanStep.depends_on)."""
    return {step.step_id: tuple(step.depends_on) for step in steps}


def detect_cycles(graph: Dict[str, Tuple[str, ...]]) -> Set[str]:
    """
    DFS 3 couleurs, algorithme identique par principe à
    kaggriculture_agents/planner/dependencies.detect_cycles (dupliqué localement, voir
    docstring du module et convention de découplage globale du projet).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    in_cycle: Set[str] = set()

    def visit(node: str, stack: List[str]) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, ()):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle_start = stack.index(dep)
                in_cycle.update(stack[cycle_start:])
            elif color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            visit(node, [])
    return in_cycle


def find_invalid_phase_order(steps: Sequence) -> List[Tuple[str, str, str]]:
    """
    Retourne une liste de (step_id, dependency_id, message) pour chaque
    dépendance qui ne serait PAS respectée par les phases déjà assignées :
    soit la dépendance est absente du plan, soit elle n'est pas dans une
    phase strictement antérieure (spec section 10, "le Coordinator ne doit
    jamais inverser une dépendance validée par le CriticAgent" -- ici on
    vérifie juste qu'elle ne l'a effectivement pas été).
    """
    by_id = {step.step_id: step for step in steps}
    invalid: List[Tuple[str, str, str]] = []
    for step in steps:
        for dep_id in step.depends_on:
            dep = by_id.get(dep_id)
            if dep is None:
                invalid.append((step.step_id, dep_id, "dépendance absente du plan"))
            elif dep.phase >= step.phase:
                invalid.append((
                    step.step_id, dep_id,
                    f"phase de la dépendance ({dep.phase}) non antérieure à la phase du step ({step.phase})",
                ))
    return invalid
