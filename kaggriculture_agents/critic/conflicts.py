"""
conflicts.py — Détection de conflits STRUCTURELS entre plusieurs steps du
plan (spec sections 12-21, 26).

Fonctions volontairement PURES : elles ne lisent jamais `state` directement
(les grandeurs qui en dépendent -- ressources initiales, nombre de workers,
tours restants -- sont extraites par analyzers.py et passées en argument).
Cela les rend indépendamment testables et réutilisables.
"""

from typing import Dict, List, Sequence

from .constants import (
    CODE_DUPLICATE_ACTION,
    CODE_RESOURCE_OVERUSE,
    CODE_STORAGE_OVERFLOW,
    CODE_TARGET_CONFLICT,
    CODE_TIME_CONSTRAINT_VIOLATION,
    CODE_WORKER_CAPACITY_EXCEEDED,
    EXCLUSIVE_TARGET_ACTIONS,
    RESOURCE_CONSUMPTION,
    SEVERITY_CRITICAL,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SHED_PRESSURE_ACTIONS,
    SHED_RELIEF_ACTIONS,
    WORKER_REQUIRED_ACTIONS,
)
from .models import CriticIssue


def detect_resource_conflicts(plan, initial_resources: Dict[str, float]) -> List[CriticIssue]:
    """Vérifie les ressources en tenant compte des achats du même plan.

    Correction essentielle V5.3 : `BUY_SEED`/`BUY_PRODUCT` enrichissent le
    ledger du Planner. Le Critic doit donc analyser `initial + achats -
    consommations`, sinon il rejetterait exactement la chaîne recherchée
    `BUY_SEED -> PLANT` et provoquerait un retour artificiel à PASS.
    """
    available = dict(initial_resources)
    consumers: Dict[str, List[str]] = {}

    # Les ordres marché sont exécutés indépendamment des workers et doivent
    # être considérés comme des approvisionnements utilisables par les steps
    # dépendants des phases suivantes.
    for step in sorted(plan.steps, key=lambda s: (s.phase, s.step_id)):
        quantity = max(1.0, float(getattr(step, "quantity", 1.0)))
        if step.action == "BUY_SEED" and step.product:
            key = f"SEED_{step.product}"
            available[key] = available.get(key, 0.0) + quantity
        elif step.action == "BUY_PRODUCT" and step.product:
            key = step.product
            available[key] = available.get(key, 0.0) + quantity
        elif step.action == "BUY_ANIMAL" and step.product:
            key = f"ANIMAL_{step.product}"
            available[key] = available.get(key, 0.0) + quantity
        elif step.action == "HARVEST":
            if step.source_agent == "crop" and step.product:
                available[step.product] = available.get(step.product, 0.0) + quantity
            elif step.source_agent == "animal" and step.product:
                product = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(step.product)
                if product:
                    available[product] = available.get(product, 0.0) + quantity
        elif step.action == "COLLECT_FERTILIZER":
            available["FERTILIZER"] = available.get("FERTILIZER", 0.0) + quantity

        getter = RESOURCE_CONSUMPTION.get((step.source_agent, step.action))
        if getter is None:
            continue
        key = getter(step)
        needed = max(1.0, float(getattr(step, "quantity", 1.0)))
        if available.get(key, 0.0) < needed:
            consumers.setdefault(key, []).append(step.step_id)
        else:
            available[key] = available.get(key, 0.0) - needed

    issues: List[CriticIssue] = []
    for key, step_ids in consumers.items():
        # L'issue porte sur le premier déficit détecté. La valeur initiale est
        # conservée pour rendre le diagnostic lisible.
        initial = initial_resources.get(key, 0.0)
        issues.append(CriticIssue(
            code=CODE_RESOURCE_OVERUSE, severity=SEVERITY_CRITICAL,
            message=f"Le plan épuise la ressource '{key}' avant certains steps ({', '.join(step_ids)}). "
                    f"Disponible initialement: {initial:g}; les achats du plan ont été pris en compte.",
            resource=key, expected="stock suffisant après achats planifiés", actual=len(step_ids),
        ))
    return issues

def detect_worker_conflicts(plan, num_workers: int) -> List[CriticIssue]:
    """
    Pour chaque phase, les steps `worker_required` doivent tenir dans le
    nombre de workers disponibles ce tour (spec sections 14-15) : les
    steps d'une même phase sont considérés comme simultanés. Corrigeable
    en répartissant sur davantage de phases -> ERROR (NEEDS_REVISION).
    """
    by_phase: Dict[int, List[str]] = {}
    for step in plan.steps:
        if step.worker_required:
            by_phase.setdefault(step.phase, []).append(step.step_id)

    issues: List[CriticIssue] = []
    for phase, step_ids in sorted(by_phase.items()):
        required = len(step_ids)
        if required > num_workers:
            issues.append(CriticIssue(
                code=CODE_WORKER_CAPACITY_EXCEEDED, severity=SEVERITY_ERROR,
                message=f"Phase {phase} requiert {required} worker(s) simultané(s) "
                        f"({', '.join(step_ids)}) mais seulement {num_workers} sont disponibles.",
                resource="workers", expected=f"<= {num_workers}", actual=required,
            ))
    return issues


def detect_target_conflicts(plan) -> List[CriticIssue]:
    """
    - TARGET_CONFLICT (spec sections 20, 26) : deux steps différents
      d'actions EXCLUSIVES (PLANT, EXPANSION_OPPORTUNITY) visant la même
      case -- une case ne peut porter qu'une seule culture / qu'un seul
      animal. Corrigeable en retirant l'un des deux -> ERROR.
    - DUPLICATE_ACTION (spec section 19) : le même (action, target,
      product) apparaît plusieurs fois -- redondant mais inoffensif (la
      plupart des actions Kaggriculture sont des no-op en double, voir
      README.md "WATER... subsequent waterings... are a no-op") -> WARNING.
    """
    issues: List[CriticIssue] = []

    exclusive_groups: Dict[tuple, List] = {}
    seen_exact: Dict[tuple, List[str]] = {}

    for step in plan.steps:
        if step.action in EXCLUSIVE_TARGET_ACTIONS and step.target is not None:
            exclusive_groups.setdefault((step.action, step.target), []).append(step)

        exact_key = (step.source_agent, step.action, step.target, step.product)
        seen_exact.setdefault(exact_key, []).append(step.step_id)

    for (action, target), steps in exclusive_groups.items():
        if len(steps) > 1:
            step_ids = [s.step_id for s in steps]
            issues.append(CriticIssue(
                code=CODE_TARGET_CONFLICT, severity=SEVERITY_ERROR,
                message=f"{len(steps)} steps '{action}' visent la même case {target} "
                        f"({', '.join(step_ids)}) : une case ne peut porter qu'une seule "
                        f"culture / un seul animal à la fois.",
                resource="land", actual=step_ids,
            ))

    for exact_key, step_ids in seen_exact.items():
        if len(step_ids) > 1:
            action = exact_key[1]
            issues.append(CriticIssue(
                code=CODE_DUPLICATE_ACTION, severity=SEVERITY_WARNING,
                message=f"L'action '{action}' est proposée {len(step_ids)} fois de façon identique "
                        f"({', '.join(step_ids)}) : redondant (no-op au-delà de la première exécution).",
                actual=step_ids,
            ))

    return issues


def detect_temporal_conflicts(plan, remaining_turns: int) -> List[CriticIssue]:
    """
    Estime le nombre MINIMAL de tours nécessaires à l'exécution du plan
    (spec section 21) : chaque phase contenant au moins un step
    `worker_required` occupe au moins un tour (les steps de cette phase
    s'exécutent en parallèle par des workers différents, README.md "Turn
    Processing Order" -- actions farmer/hand). Les phases purement marché
    (SELL/HOLD/PRODUCE) ne consomment aucun tour farmer/hand dédié (les
    ordres marché sont soumis indépendamment, même section du README).
    Heuristique volontairement simple : ne modélise pas les déplacements
    entre cases (spec section 28, CropAgent/AnimalAgent ne fournissent pas
    non plus de simulation de trajet).
    """
    phases_needing_a_turn = {
        step.phase for step in plan.steps if step.worker_required
    }
    min_turns_needed = len(phases_needing_a_turn)

    if min_turns_needed <= remaining_turns:
        return []

    return [CriticIssue(
        code=CODE_TIME_CONSTRAINT_VIOLATION, severity=SEVERITY_ERROR,
        message=f"Le plan nécessite au moins {min_turns_needed} tour(s) avec worker "
                f"(une phase par tour minimum) mais il ne reste que {remaining_turns} tour(s) "
                f"dans la partie.",
        resource="turns", expected=f"<= {remaining_turns}", actual=min_turns_needed,
    )]


def detect_storage_conflicts(plan, shed_used: float, shed_capacity: float) -> List[CriticIssue]:
    """
    Pression nette sur le shed (spec section 26) : chaque HARVEST /
    COLLECT_FERTILIZER ajoute une pression, chaque SELL en relâche une
    (approximation à 1 unité/step, voir constants.SHED_PRESSURE_ACTIONS).
    Un dépassement n'est jamais fatal sur Kaggriculture -- le surplus est
    simplement perdu au DROP (README.md, "shedCapacity... overflow...
    discarded") -- donc WARNING, jamais bloquant.
    """
    produced = sum(1 for step in plan.steps if step.action in SHED_PRESSURE_ACTIONS)
    relieved = sum(1 for step in plan.steps if step.action in SHED_RELIEF_ACTIONS)
    net_pressure = produced - relieved
    if net_pressure <= 0:
        return []

    projected = shed_used + net_pressure
    if projected <= shed_capacity:
        return []

    return [CriticIssue(
        code=CODE_STORAGE_OVERFLOW, severity=SEVERITY_WARNING,
        message=f"Le plan ajoute une pression nette d'environ {net_pressure} unité(s) au shed "
                f"(déjà à {shed_used:g}/{shed_capacity:g}), soit ~{projected:g} projeté(es) : "
                f"le surplus serait perdu au prochain DROP sans vente/consommation intermédiaire "
                f"supplémentaire.",
        resource="shed", expected=f"<= {shed_capacity:g}", actual=projected,
    )]