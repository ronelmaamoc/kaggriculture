"""
worker_allocator.py — Affectation des workers réels aux steps qui en ont besoin.

Contrairement à CropAgent/AnimalAgent (qui calculaient une distance
purement INFORMATIVE, jamais utilisée pour choisir un worker -- voir
kaggriculture_agents/crops/analyzers.py, review du CropAgent), c'est ICI, et seulement
ici, que l'architecture affecte réellement un worker à une tâche
(spec section 14, "Localité des workers").

Chaque phase est traitée indépendamment : un worker redevient disponible
au tour suivant (donc à la phase suivante), voir constants.TURNS_PER_PHASE.
"""

from typing import Dict, List, Optional, Sequence, Tuple

Position = Tuple[int, int]


def _distance(a: Optional[Position], b: Optional[Position]) -> Optional[float]:
    if a is None or b is None:
        return None
    (ax, ay), (bx, by) = a, b
    return abs(ax - bx) + abs(ay - by)


def allocate_workers(
    steps_by_phase: Dict[int, List],
    workers: Sequence[Tuple[str, Optional[Position]]],
) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """
    steps_by_phase : phase -> liste de steps `worker_required` (déjà
    filtrés par l'appelant) pour cette phase.
    workers : liste de (worker_id, position), ex: [("farmer", (4,4)),
    ("hand_0", (5,4))] -- construite depuis state.workers.all_workers.

    Retourne (assignment, unassigned) :
      - assignment : step_id -> worker_id
      - unassigned : liste de (step_id, raison), pour les steps qu'aucun
        worker disponible ne pouvait couvrir CETTE phase (ne devrait pas
        arriver pour un plan APPROVED, voir kaggriculture_agents/planner/agent.py._find_phase
        et kaggriculture_agents/critic : CODE_WORKER_CAPACITY_EXCEEDED -- defense in depth).

    Algorithme glouton déterministe (spec section 26, "Déterminisme") : pour
    chaque phase, les steps sont triés par step_id, puis pour chacun on
    prend, parmi les workers encore disponibles CETTE phase, celui qui
    minimise la distance de Manhattan à la cible (égalité départagée par
    worker_id). Ce n'est PAS un algorithme d'affectation optimal global
    (type Hongrois) : heuristique v1 documentée, cohérente avec les autres
    heuristiques du projet (kaggriculture_agents/crops/scoring.py, glouton similaire dans
    kaggriculture_agents/planner/agent.py).
    """
    assignment: Dict[str, str] = {}
    unassigned: List[Tuple[str, str]] = []

    for phase in sorted(steps_by_phase):
        available = list(workers)
        phase_steps = sorted(steps_by_phase[phase], key=lambda s: s.step_id)

        for step in phase_steps:
            if not available:
                unassigned.append((step.step_id, "aucun worker disponible dans cette phase"))
                continue

            target = step.target

            def sort_key(candidate):
                worker_id, position = candidate
                dist = _distance(target, position)
                return (dist if dist is not None else float("inf"), worker_id)

            chosen = min(available, key=sort_key)
            assignment[step.step_id] = chosen[0]
            available.remove(chosen)

    return assignment, unassigned
