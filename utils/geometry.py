"""
utils/geometry.py — Opérations géométriques partagées.

RÈGLE RÉELLE DE DÉPLACEMENT (vérifiée dans README.md du jeu avant de choisir
l'algorithme par défaut, spec section 6) : le déplacement d'un worker se
fait case par case sur une grille (NORTH/SOUTH/EAST/WEST, voir
`kaggriculture_agents/executor/constants.py`), jamais en diagonale — la distance
Manhattan (`|dx| + |dy|`) est donc la mesure pertinente pour ce projet, pas
la distance euclidienne.

DUPLICATION EXISTANTE (constatée à l'inspection, spec section 6 "ne pas
dupliquer les fonctions déjà présentes dans les agents") : `CropAgent`
(`kaggriculture_agents/crops/analyzers.py::_nearest_worker_distance`), `AnimalAgent`
(`kaggriculture_agents/animals/analyzers.py::_nearest_worker_distance`) et
`CoordinatorAgent` (`kaggriculture_agents/coordinator/worker_allocator.py::_distance`)
calculent chacun leur propre distance Manhattan inline. Cette tâche
n'inclut PAS de réécrire ces agents (contrainte absolue #1 : "ne réécris
pas les agents existants") : ce module fournit la version centralisée pour
tout code NOUVEAU (ce fichier même, `main.py`, une future refactorisation
explicitement demandée), sans toucher au code existant qui fonctionne déjà
et dont les tests passent.
"""

from typing import Iterable, Optional, Sequence, Tuple

Position = Tuple[int, int]


def manhattan_distance(a: Position, b: Position) -> int:
    """Distance réelle de déplacement dans Kaggriculture (grille, pas de diagonale)."""
    ax, ay = a
    bx, by = b
    return abs(ax - bx) + abs(ay - by)


def euclidean_distance(a: Position, b: Position) -> float:
    """
    Fournie pour complétude (spec section 6) mais non utilisée par les
    agents existants : aucun d'eux ne modélise de déplacement en diagonale.
    """
    ax, ay = a
    bx, by = b
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def nearest_target(position: Position, targets: Iterable[Position]) -> Optional[Position]:
    """
    Cible la plus proche de `position` au sens de la distance Manhattan.
    Retourne `None` si `targets` est vide. Départage déterministe : à
    distance égale, la cible la plus petite au sens de l'ordre naturel des
    tuples est retenue (même convention que `kaggriculture_agents/planner/conflicts.py`
    pour les départages à score égal : reproductibilité avant tout).
    """
    targets = list(targets)
    if not targets:
        return None
    return min(targets, key=lambda t: (manhattan_distance(position, t), t))


def total_distance(path: Sequence[Position]) -> int:
    """Somme des distances Manhattan entre positions consécutives d'un chemin (0 si moins de 2 points)."""
    if len(path) < 2:
        return 0
    return sum(manhattan_distance(path[i], path[i + 1]) for i in range(len(path) - 1))
