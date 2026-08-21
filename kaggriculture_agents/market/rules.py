"""
rules.py — Règles de candidature pour chaque type d'analyse/action du marché.

Une fonction "rule" répond uniquement à la question "cette action est-elle
possible / pertinente ?" (booléen). Elle ne calcule ni score ni valeur — ça,
c'est le rôle de scoring.py. Elle ne modifie jamais FarmState (lecture
seule) ni le marché (voir spec section 5 et 33 : le MarketAgent observe,
il n'écrit jamais dans state.market).
"""

from typing import Optional

from .constants import PRICE_HIGH_THRESHOLD, PRICE_LOW_THRESHOLD, PRODUCTION_INFO


def is_price_high(normalized_price: float, threshold: float = PRICE_HIGH_THRESHOLD) -> bool:
    """Prix courant nettement au-dessus du prix de base (marché en pénurie)."""
    return normalized_price >= threshold


def is_price_low(normalized_price: float, threshold: float = PRICE_LOW_THRESHOLD) -> bool:
    """Prix courant nettement en dessous du prix de base (marché en surplus)."""
    return normalized_price <= threshold


def price_level(normalized_price: float) -> str:
    """Traduit un normalized_price en catégorie LOW / NORMAL / HIGH."""
    if is_price_low(normalized_price):
        return "LOW"
    if is_price_high(normalized_price):
        return "HIGH"
    return "NORMAL"


def is_sell_attractive(level: str, available_quantity: float) -> bool:
    """
    Une vente est une proposition pertinente si :
    - on possède réellement du stock (sinon SELL serait inexécutable) ;
    - le prix n'est pas actuellement bas (sinon on préfère proposer HOLD,
      voir is_hold_attractive — les deux propositions sont mutuellement
      exclusives pour un même produit, cf. agent.py._resolve_local_conflicts).
    """
    return available_quantity > 0 and level in ("NORMAL", "HIGH")


def is_hold_attractive(level: str, available_quantity: float) -> bool:
    """
    Conserver est pertinent quand on a du stock mais que le prix actuel est
    bas : vendre immédiatement semble peu intéressant (spec section 14).
    Ce n'est qu'une proposition, jamais une obligation d'attendre.
    """
    return available_quantity > 0 and level == "LOW"


def is_production_attractive(product: str, level: str, remaining_days: int) -> bool:
    """
    Une opportunité de production est pertinente si :
    - le produit est un produit végétal documenté (PRODUCTION_INFO) ;
    - le prix courant est actuellement haut ;
    - il reste assez de jours pour au moins atteindre le premier rendement.

    Le MarketAgent ne sait pas si une parcelle est réellement disponible
    (il n'observe pas state.crops) : c'est une opportunité EN PRINCIPE, que
    le futur PlannerAgent pourra combiner avec une CropProposal réelle
    (spec section 17).
    """
    info = PRODUCTION_INFO.get(product)
    if info is None:
        return False
    if level != "HIGH":
        return False
    return remaining_days >= info["first_yield_day"]


def has_known_base_price(product: str, market_product_info: dict) -> bool:
    return product in market_product_info


def is_end_of_game(remaining_days: int, threshold: int) -> bool:
    """Moins d'un jour de jeu restant : conserver du stock devient risqué (spec section 30)."""
    return remaining_days <= threshold