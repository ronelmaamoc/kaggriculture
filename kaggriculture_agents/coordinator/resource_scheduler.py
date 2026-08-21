"""
resource_scheduler.py — Datation temporelle des steps (spec sections 18-21).

L'ORDRE des ressources (ex: BUY_SEEDS avant PLANT, HARVEST avant SELL) est
déjà garanti par la construction même du Plan : PlannerAgent ne place un
step en phase N que si toutes ses dépendances sont en phase < N (voir
kaggriculture_agents/planner/agent.py._schedule), et CriticAgent revérifie cet ordre
avant d'approuver (analyze_dependencies, analyze_resources). Le rôle réel
et non redondant de ce module est donc de traduire les phases (relatives,
sans unité) en TOURS DE JEU concrets (spec section 20, "Gestion du temps"),
à partir du tour courant (`FarmState.time.step`).
"""

from typing import Sequence

from .constants import TURNS_PER_PHASE


def estimated_turn_for_phase(base_turn: int, phase: int) -> int:
    return base_turn + phase * TURNS_PER_PHASE


def compute_estimated_turns(steps: Sequence) -> int:
    """Nombre de tours de jeu couverts par le schedule (0 si aucun step)."""
    if not steps:
        return 0
    return (max(step.phase for step in steps) + 1) * TURNS_PER_PHASE
