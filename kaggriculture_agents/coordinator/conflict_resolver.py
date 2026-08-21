"""
conflict_resolver.py — Vérification DÉFENSIVE des conflits de worker.

`worker_allocator.allocate_workers` garantit par construction qu'un même
worker n'est jamais affecté deux fois dans la même phase (il est retiré de
`available` dès qu'il est choisi). Ce module fournit une vérification
INDÉPENDANTE de ce résultat (spec section 13, "Éviter les conflits de
worker"), testable seule, et utilisée par agent.py comme dernière ligne de
défense avant de produire l'ExecutionSchedule -- au cas où l'affectation
proviendrait d'ailleurs (ex : un futur algorithme d'allocation alternatif).
"""

from typing import Dict, List, Sequence, Tuple


def detect_worker_conflicts(
    steps: Sequence,
    assignment: Dict[str, str],
) -> List[Tuple[int, str, Tuple[str, ...]]]:
    """
    Retourne une liste de (phase, worker_id, step_ids) pour chaque worker
    affecté à PLUSIEURS steps d'une même phase -- ce qui est physiquement
    impossible (un worker ne peut réaliser qu'une seule action par tour).
    """
    by_phase_worker: Dict[Tuple[int, str], List[str]] = {}
    for step in steps:
        worker_id = assignment.get(step.step_id)
        if worker_id is None:
            continue
        by_phase_worker.setdefault((step.phase, worker_id), []).append(step.step_id)

    return [
        (phase, worker_id, tuple(sorted(step_ids)))
        for (phase, worker_id), step_ids in sorted(by_phase_worker.items())
        if len(step_ids) > 1
    ]
