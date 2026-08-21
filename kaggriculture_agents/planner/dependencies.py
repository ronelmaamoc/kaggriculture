"""
dependencies.py — Identification des propositions, graphe de dépendances,
détection de cycles, tri topologique.

`EconomyProposal.dependencies` référence déjà d'autres propositions avec le
schéma `f"{source_agent}:{action}:{target}"` (voir
kaggriculture_agents/economy/analyzers.py, `_find_harvest_dependencies` — ex: une vente
SELL MELON dépend d'une récolte `"crop:HARVEST:(4, 5)"` si cette récolte
n'a pas encore eu lieu ce tour-ci). Ce module réutilise EXACTEMENT ce même
schéma pour résoudre les dépendances vers un `step_id` complet.
"""

from typing import Dict, List, Sequence, Set, Tuple


def proposal_id(ep) -> str:
    """
    Identifiant complet et stable d'une EconomyProposal, unique même quand
    plusieurs propositions partagent `source_agent:action:target` (ex :
    deux EXPANSION_OPPORTUNITY -- COW et SHEEP -- sur la même pasture vide).
    """
    return f"{ep.source_agent}:{ep.action}:{ep.target}:{ep.product}"


def dependency_short_key(ep) -> str:
    """
    Clé au format utilisé par EconomyProposal.dependencies
    (`source_agent:action:target`, SANS le produit -- voir docstring du
    module). Sert à faire correspondre un `depends_on` déclaré par une
    proposition source à un `step_id` complet.
    """
    return f"{ep.source_agent}:{ep.action}:{ep.target}"


def resolve_dependencies(proposals: Sequence) -> Dict[str, Tuple[str, ...]]:
    """
    Construit, pour chaque proposition (par son step_id complet), la liste
    des step_id complets dont elle dépend. Une dépendance déclarée en clé
    courte qui ne correspond à AUCUNE proposition candidate est ignorée ici
    (elle sera traitée par agent.py comme "produit déjà en stock, pas de
    récolte à attendre ce tour-ci" -- voir agent.py et README.md).

    Si plusieurs propositions partagent la même clé courte (cas rare :
    deux HARVEST sur la même case ne devraient normalement pas coexister),
    on résout vers TOUTES par déterminisme plutôt que d'en choisir une
    arbitrairement -- le step dépendant attendra qu'AU MOINS UNE soit
    retenue (voir agent.py._dependencies_satisfied).
    """
    by_short_key: Dict[str, List[str]] = {}
    by_full_key: Dict[str, List[str]] = {}
    for ep in proposals:
        pid = proposal_id(ep)
        by_short_key.setdefault(dependency_short_key(ep), []).append(pid)
        # Certaines chaînes historiques de dépendances incluent le produit
        # (`source:action:target:product`). Elles doivent être résolues elles
        # aussi ; sinon BUY_ANIMAL -> PICKUP -> PLACE pouvait être ignoré.
        by_full_key.setdefault(pid, []).append(pid)

    graph: Dict[str, Tuple[str, ...]] = {}
    for ep in proposals:
        pid = proposal_id(ep)
        resolved: List[str] = []
        for dep in ep.dependencies:
            candidates = by_short_key.get(dep, ())
            if not candidates:
                candidates = by_full_key.get(dep, ())
            resolved.extend(candidate for candidate in candidates if candidate != pid)
        graph[pid] = tuple(sorted(set(resolved)))
    return graph


def detect_cycles(graph: Dict[str, Tuple[str, ...]]) -> Set[str]:
    """
    Retourne l'ensemble des step_id impliqués dans au moins un cycle du
    graphe de dépendances (DFS avec 3 couleurs). Un plan ne doit jamais
    contenir de cycle (spec section 14) : les propositions concernées
    doivent être exclues avant l'ordonnancement, pas "résolues" en devinant
    un ordre.
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
                # Cycle trouvé : tous les nœuds du cycle sur la pile actuelle.
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


def topological_sort(graph: Dict[str, Tuple[str, ...]]) -> List[str]:
    """
    Tri topologique déterministe (Kahn) : à égalité de disponibilité, les
    nœuds sont départagés par ordre alphabétique de step_id pour un
    résultat reproductible. Suppose que `graph` ne contient aucun cycle
    (appeler `detect_cycles` et retirer les nœuds concernés au préalable).
    """
    in_degree: Dict[str, int] = {node: 0 for node in graph}
    # Construire la relation inverse (successeurs) pour Kahn : `deps` pointe
    # vers des prédécesseurs, donc chaque arête doit être inversée.
    successors: Dict[str, List[str]] = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep in successors:
                successors[dep].append(node)
                in_degree[node] += 1

    ready = sorted(node for node, deg in in_degree.items() if deg == 0)
    order: List[str] = []
    while ready:
        ready.sort()
        node = ready.pop(0)
        order.append(node)
        for succ in successors[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)
    return order


def phases_from_order(order: List[str], graph: Dict[str, Tuple[str, ...]]) -> Dict[str, int]:
    """
    Calcule la phase minimale de chaque step_id : 0 si aucune dépendance,
    sinon 1 + max(phase des dépendances). Deux steps de même phase peuvent
    être réalisés en parallèle par des workers différents (spec section 23).
    `resources.py`/`agent.py` peuvent ensuite repousser un step à une phase
    ultérieure si les workers disponibles sont insuffisants ce tour-là.
    """
    phase: Dict[str, int] = {}
    for node in order:
        deps = graph.get(node, ())
        phase[node] = 0 if not deps else 1 + max(phase[d] for d in deps if d in phase)
    return phase