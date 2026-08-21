"""
rules.py — Règles de candidature pour chaque action agricole.

Une fonction "rule" répond uniquement à la question "cette action est-elle
possible / pertinente ?" (booléen). Elle ne calcule ni score ni valeur — ça,
c'est le rôle de scoring.py. Elle ne modifie jamais FarmState (lecture seule).
"""

from typing import Dict

from .constants import CROP_INFO


def is_ready_for_harvest(crop) -> bool:
    """Une culture est récoltable dès que yield_units > 0 (déjà calculé par Perception)."""
    return crop.ready_to_harvest


def needs_water(crop) -> bool:
    """Une culture doit être arrosée si elle ne l'a pas encore été aujourd'hui."""
    return crop.needs_water


def can_be_planted(crop_type: str, seeds: Dict[str, int], remaining_days: int) -> bool:
    """
    Une plantation est possible si :
    - le type de culture est connu (présent dans CROP_INFO) ;
    - on possède au moins une graine de ce type ;
    - il reste assez de jours pour au moins atteindre le premier rendement
      (sinon planter n'a aucune chance de rapporter quoi que ce soit).
    """
    info = CROP_INFO.get(crop_type)
    if info is None:
        return False
    if seeds.get(crop_type, 0) <= 0:
        return False
    return remaining_days >= info["first_yield_day"]


def can_be_fertilized(crop, fertilizer_available: int) -> bool:
    """
    La fertilisation est pertinente si :
    - on dispose d'au moins une unité de fertilisant ;
    - la culture n'est pas déjà sous bonus de fertilisation ;
    - la culture n'est pas déjà en phase de décroissance (max_lifespan_step
      atteint) — inutile de fertiliser une culture qui décline déjà.
    """
    if fertilizer_available <= 0:
        return False
    if crop.is_fertilized_now:
        return False

    info = CROP_INFO.get(crop.crop_type)
    if info is None:
        return False

    if info["is_ongoing"]:
        # Une culture "ongoing" reste pertinente tant qu'elle n'est pas
        # entrée en décroissance (max_lifespan_step == -1 tant qu'elle
        # n'a pas atteint son cumul de production maximal).
        return crop.max_lifespan_step == -1
    else:
        # Une culture "one-time" n'est plus pertinente à fertiliser une fois
        # sa fenêtre de bonus de rendement dépassée.
        return crop.age_days <= info["max_yield_day"]
