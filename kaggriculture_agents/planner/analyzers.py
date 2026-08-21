"""
analyzers.py — Analyse des contraintes de planification à partir de
`FarmState` (lecture seule, jamais modifié).

Ne duplique PAS les analyseurs d'EconomyAgent (budget sécurisé avec
réserve, niveaux CRITICAL/LIMITED/ABUNDANT) : le Planner a besoin de
quantités EXACTES pour construire un plan réalisable (voir resources.py),
pas de catégories qualitatives.
"""

from dataclasses import dataclass

from .resources import BudgetLedger, ResourceLedger


@dataclass(frozen=True)
class PlannerConstraints:
    remaining_days: int
    remaining_turns: int
    num_workers: int
    resource_ledger: ResourceLedger
    budget_ledger: BudgetLedger


def analyze_time(state) -> dict:
    return {"remaining_days": state.time.remaining_days, "remaining_turns": state.time.remaining_turns}


def analyze_workers(state) -> int:
    """
    Nombre de workers disponibles ce tour (farmer + hands). Une action
    `worker_required` ne peut être planifiée dans une phase où tous les
    workers sont déjà occupés (spec section 21, 53, 65).
    """
    return len(state.workers.all_workers)


def analyze_resources(state) -> ResourceLedger:
    return ResourceLedger(state)


def analyze_budget(state) -> BudgetLedger:
    """
    Contrairement à EconomyAgent.analyze_budget, aucune réserve de sécurité
    n'est appliquée ici (voir resources.BudgetLedger, docstring) : c'est un
    choix assumé et documenté, pas un oubli.
    """
    return BudgetLedger(balance=state.resources.money)


def analyze_constraints(state) -> PlannerConstraints:
    time_info = analyze_time(state)
    return PlannerConstraints(
        remaining_days=time_info["remaining_days"],
        remaining_turns=time_info["remaining_turns"],
        num_workers=analyze_workers(state),
        resource_ledger=analyze_resources(state),
        budget_ledger=analyze_budget(state),
    )