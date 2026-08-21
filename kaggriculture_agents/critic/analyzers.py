"""
analyzers.py — Analyses dépendant de `FarmState` (lecture seule, jamais
modifié). Ce module fait le pont entre `FarmState` / `Plan` et les
fonctions pures de conflicts.py : il en extrait les grandeurs nécessaires
(ressources initiales, nombre de workers, tours restants) puis délègue la
détection proprement dite.

analyze_budget() et analyze_dependencies() / analyze_economics() n'ont pas
d'équivalent pur dans conflicts.py : le budget dépend de l'ORDRE des steps
(une vente réalise un revenu immédiat, contrairement aux ressources
nommées -- voir conflicts.detect_resource_conflicts), et les dépendances /
l'économie nécessitent de croiser plusieurs champs de `Plan` et `FarmState`
simultanément -- elles sont donc implémentées directement ici.
"""

from typing import Dict, List, Sequence, Set

from . import conflicts
from .constants import (
    AGGREGATE_FLOAT_TOLERANCE,
    ANIMAL_PRODUCT,
    CASH_CONSUMING_ACTIONS,
    CASH_REALIZING_ACTIONS,
    CODE_BUDGET_EXCEEDED,
    CODE_BUDGET_IMPOSSIBLE,
    CODE_COST_EXCEEDS_REVENUE,
    CODE_DEPENDENCY_CYCLE,
    CODE_DEPENDENCY_ORDER_INVALID,
    CODE_DOUBLE_COUNTED_PROFIT,
    CODE_MISSING_DEPENDENCY,
    CODE_PROFIT_INCONSISTENT,
    FLOAT_TOLERANCE,
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from .models import CriticIssue


# --------------------------------------------------------------------------- #
# Budget (spec sections 10-11)
# --------------------------------------------------------------------------- #
def analyze_budget(state, plan) -> List[CriticIssue]:
    """
    Deux niveaux, comme documenté dans README.md (l'argent change de main
    immédiatement à la vente, README.md section "Buying inventory... the
    buy price is quoted at post-buy inventory and the sell price at
    pre-sell inventory") :

    1. Impossibilité ABSOLUE (spec section 10, dernier exemple) : même en
       réalisant TOUTES les ventes du plan avant TOUTE dépense, le coût
       total dépasse l'argent disponible -> aucun réordonnancement ne
       répare ça -> CRITICAL, et on s'arrête là (le point 2 serait
       redondant).
    2. Dépassement PONCTUEL dans l'ordre donné (spec section 11, budget
       dynamique) : le total est finançable, mais l'ordre actuel du plan
       fait passer la trésorerie sous zéro à un moment donné -> corrigeable
       en réordonnant -> ERROR.
    """
    total_cost = sum(step.estimated_cost for step in plan.steps if step.action in CASH_CONSUMING_ACTIONS)
    total_revenue = sum(step.expected_revenue for step in plan.steps if step.action in CASH_REALIZING_ACTIONS)
    absolute_available = state.resources.money + total_revenue

    if total_cost > absolute_available + FLOAT_TOLERANCE:
        return [CriticIssue(
            code=CODE_BUDGET_IMPOSSIBLE, severity=SEVERITY_CRITICAL,
            message=f"Le plan dépense {total_cost:.0f}$ au total, mais même en réalisant toutes les "
                    f"ventes prévues ({total_revenue:.0f}$) avant toute dépense, seuls "
                    f"{absolute_available:.0f}$ seraient disponibles : impossible quel que soit l'ordre.",
            resource="money", expected=f"<= {absolute_available:.0f}", actual=total_cost,
        )]

    balance = state.resources.money
    for step in sorted(plan.steps, key=lambda s: (s.phase, s.step_id)):
        if step.action in CASH_CONSUMING_ACTIONS:
            balance -= step.estimated_cost
        if step.action in CASH_REALIZING_ACTIONS:
            balance += step.expected_revenue
        if balance < -FLOAT_TOLERANCE:
            return [CriticIssue(
                code=CODE_BUDGET_EXCEEDED, severity=SEVERITY_ERROR,
                message=f"Au step '{step.step_id}' (phase {step.phase}), la trésorerie simulée "
                        f"devient négative ({balance:.0f}$) dans l'ordre actuel du plan ; le total est "
                        f"finançable ({total_cost:.0f}$ <= {absolute_available:.0f}$), un réordonnancement "
                        f"(vendre avant d'acheter) résoudrait probablement le problème.",
                step_id=step.step_id, resource="money", expected=">= 0", actual=round(balance, 2),
            )]

    return []


# --------------------------------------------------------------------------- #
# Ressources nommées (spec sections 12-13)
# --------------------------------------------------------------------------- #
def _initial_resource_ledger(state) -> Dict[str, float]:
    ledger: Dict[str, float] = {f"SEED_{crop}": qty for crop, qty in state.resources.seeds.items()}
    ledger["WHEAT"] = state.resources.shed.get("WHEAT", 0)
    ledger["FERTILIZER"] = state.resources.shed.get("FERTILIZER", 0)
    for animal in ("GOOSE", "COW", "SHEEP"):
        ledger[f"ANIMAL_{animal}"] = state.resources.shed.get(animal, 0)
        ledger[f"INVENTORY_{animal}"] = sum(inv.get(animal, 0) for inv in state.resources.inventories)
    return ledger


def analyze_resources(state, plan) -> List[CriticIssue]:
    return conflicts.detect_resource_conflicts(plan, _initial_resource_ledger(state))


# --------------------------------------------------------------------------- #
# Workers (spec sections 14-15)
# --------------------------------------------------------------------------- #
def analyze_workers(state, plan) -> List[CriticIssue]:
    num_workers = len(state.workers.all_workers)
    return conflicts.detect_worker_conflicts(plan, num_workers)


# --------------------------------------------------------------------------- #
# Temps (spec section 21)
# --------------------------------------------------------------------------- #
def analyze_time(state, plan) -> List[CriticIssue]:
    return conflicts.detect_temporal_conflicts(plan, state.time.remaining_turns)


# --------------------------------------------------------------------------- #
# Stockage (spec section 26)
# --------------------------------------------------------------------------- #
def analyze_storage(state, plan) -> List[CriticIssue]:
    return conflicts.detect_storage_conflicts(plan, state.resources.shed_used, state.resources.shed_capacity)


# --------------------------------------------------------------------------- #
# Dépendances (spec sections 16-18, 25)
# --------------------------------------------------------------------------- #
def _realized_product(step) -> "str | None":
    """Produit ajouté à l'inventaire par ce step, s'il s'agit d'une récolte."""
    if step.action != "HARVEST":
        return None
    if step.source_agent == "crop":
        return step.product
    if step.source_agent == "animal":
        return ANIMAL_PRODUCT.get(step.product)
    return None


def _product_already_in_shed(state, product) -> bool:
    return product is not None and state.resources.shed.get(product, 0) > 0


def _detect_cycles(graph: Dict[str, List[str]]) -> Set[str]:
    """DFS 3 couleurs, même principe que kaggriculture_agents/planner/dependencies.detect_cycles."""
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


def analyze_dependencies(state, plan) -> List[CriticIssue]:
    issues: List[CriticIssue] = []
    steps_by_id = {step.step_id: step for step in plan.steps}

    for step in plan.steps:
        unresolved: List[str] = []
        for dep_id in step.depends_on:
            dep_step = steps_by_id.get(dep_id)
            if dep_step is None:
                unresolved.append(dep_id)
                continue
            if not (dep_step.phase < step.phase):
                issues.append(CriticIssue(
                    code=CODE_DEPENDENCY_ORDER_INVALID, severity=SEVERITY_ERROR,
                    message=f"Le step '{step.step_id}' (phase {step.phase}) dépend de "
                            f"'{dep_id}' (phase {dep_step.phase}), qui n'est pas placé avant lui.",
                    step_id=step.step_id, expected=f"phase < {step.phase}", actual=dep_step.phase,
                ))

        if unresolved and not _product_already_in_shed(state, step.product):
            issues.append(CriticIssue(
                code=CODE_MISSING_DEPENDENCY, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' dépend de {unresolved}, absent(s) du plan retenu, "
                        f"et '{step.product}' n'est pas déjà disponible dans le shed "
                        f"({state.resources.shed.get(step.product, 0):g} unité(s)).",
                step_id=step.step_id, resource=step.product,
                expected=">= 1 en shed ou une récolte planifiée", actual=state.resources.shed.get(step.product, 0),
            ))

        # Cas non couvert par depends_on lui-même (spec section 17) : une
        # SELL sans AUCUNE dépendance déclarée (EconomyAgent n'a trouvé
        # aucune proposition HARVEST candidate ce tour-ci), dont le produit
        # n'est ni déjà en stock, ni récolté par un autre step du plan.
        if step.action == "SELL" and not step.depends_on and not _product_already_in_shed(state, step.product):
            harvested_here = any(_realized_product(other) == step.product for other in plan.steps)
            if not harvested_here:
                issues.append(CriticIssue(
                    code=CODE_MISSING_DEPENDENCY, severity=SEVERITY_ERROR,
                    message=f"Le step '{step.step_id}' vend '{step.product}', qui n'est ni disponible "
                            f"dans le shed, ni récolté par un autre step du plan.",
                    step_id=step.step_id, resource=step.product,
                    expected=">= 1 en shed ou une récolte planifiée", actual=0,
                ))

    graph = {step.step_id: [d for d in step.depends_on if d in steps_by_id] for step in plan.steps}
    cyclic_ids = _detect_cycles(graph)
    if cyclic_ids:
        issues.append(CriticIssue(
            code=CODE_DEPENDENCY_CYCLE, severity=SEVERITY_CRITICAL,
            message=f"Cycle de dépendances détecté entre les steps : {sorted(cyclic_ids)}.",
            actual=sorted(cyclic_ids),
        ))

    return issues


# --------------------------------------------------------------------------- #
# Cohérence économique (spec section 22-23)
# --------------------------------------------------------------------------- #
def analyze_economics(state, plan) -> List[CriticIssue]:
    issues: List[CriticIssue] = []

    for step in plan.steps:
        recomputed_profit = step.expected_revenue - step.estimated_cost
        if abs(recomputed_profit - step.expected_profit) > FLOAT_TOLERANCE:
            issues.append(CriticIssue(
                code=CODE_PROFIT_INCONSISTENT, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' déclare expected_profit={step.expected_profit:.2f} "
                        f"mais expected_revenue - estimated_cost = {recomputed_profit:.2f}.",
                step_id=step.step_id, expected=round(recomputed_profit, 2), actual=step.expected_profit,
            ))

        if step.expected_profit < -FLOAT_TOLERANCE:
            issues.append(CriticIssue(
                code=CODE_COST_EXCEEDS_REVENUE, severity=SEVERITY_WARNING,
                message=f"Le step '{step.step_id}' ({step.action} {step.product or ''}) a un coût "
                        f"({step.estimated_cost:.0f}$) supérieur au revenu attendu "
                        f"({step.expected_revenue:.0f}$) : profit net négatif "
                        f"({step.expected_profit:.0f}$), peut être justifié (urgence/risque) mais "
                        f"mérite une relecture.",
                step_id=step.step_id, expected=">= 0", actual=round(step.expected_profit, 2),
            ))

    referenced_as_dependency: Set[str] = set()
    step_ids = {step.step_id for step in plan.steps}
    for step in plan.steps:
        referenced_as_dependency.update(d for d in step.depends_on if d in step_ids)

    recomputed_net = sum(
        step.expected_profit for step in plan.steps if step.step_id not in referenced_as_dependency
    )
    if plan.expected_profit - recomputed_net > AGGREGATE_FLOAT_TOLERANCE:
        issues.append(CriticIssue(
            code=CODE_DOUBLE_COUNTED_PROFIT, severity=SEVERITY_ERROR,
            message=f"Plan.expected_profit ({plan.expected_profit:.2f}) dépasse la valeur nette "
                    f"recalculée en excluant les steps référencés comme dépendance "
                    f"({recomputed_net:.2f}) : un profit semble compté deux fois "
                    f"(ex: HARVEST puis SELL du même produit).",
            resource="expected_profit", expected=round(recomputed_net, 2), actual=plan.expected_profit,
        ))

    return issues