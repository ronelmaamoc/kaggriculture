"""
rules.py — Règles de candidature pour chaque action animale.

Une fonction "rule" répond uniquement à la question "cette action est-elle
possible / pertinente ?" (booléen). Elle ne calcule ni score ni valeur — ça,
c'est le rôle de scoring.py. Elle ne modifie jamais FarmState (lecture seule).
"""

from typing import Dict, Optional

from .constants import ANIMAL_INFO


def needs_feed(animal) -> bool:
    """Un animal doit être nourri s'il ne l'a pas encore été aujourd'hui."""
    return animal.needs_feed


def needs_care(animal) -> bool:
    """Un animal peut être soigné s'il ne l'a pas encore été aujourd'hui."""
    return animal.needs_care


def is_ready_for_harvest(animal) -> bool:
    """Une production animale est récoltable dès que yield_units > 0."""
    return animal.ready_to_harvest


def has_fertilizer_to_collect(animal) -> bool:
    """Le fertilisant est prêt à être collecté quand fertilizer_available est vrai."""
    return animal.fertilizer_available


def feed_available(feed_stock: int) -> bool:
    """
    FEED nécessite du blé (WHEAT) en stock. Sans blé disponible, proposer
    FEED serait une action non exécutable (voir README.md : "All animals
    must be fed every day using wheat").
    """
    return feed_stock > 0


def can_expand(animal_type: str, remaining_days: int) -> bool:
    """
    Une opportunité d'expansion n'est pertinente que si :
    - le type d'animal est connu (présent dans ANIMAL_INFO) ;
    - il reste assez de jours pour au moins atteindre le premier rendement
      (sinon l'acheter n'a aucune chance de rapporter quoi que ce soit avant
      la fin des 720 tours).
    """
    info = ANIMAL_INFO.get(animal_type)
    if info is None:
        return False
    return remaining_days >= info["first_yield_day"]