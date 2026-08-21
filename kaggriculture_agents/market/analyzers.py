"""
analyzers.py — Détection des analyses/opportunités candidates à partir d'un
FarmState.

    analyze_prices(state)               -> PriceAnalysis par produit coté
    find_sell_opportunities(state, ...) -> MarketProposal[] (SELL)
    find_hold_opportunities(state, ...) -> MarketProposal[] (HOLD)
    find_production_opportunities(...)  -> MarketProposal[] (PRODUCE)

Chaque find_*_opportunities(state, price_analyses) :
  1. filtre les candidats via rules.py (is_sell_attractive, ...) ;
  2. calcule expected_value / urgency via scoring.py ou des heuristiques
     documentées ;
  3. délègue le calcul du score final à scoring.py ;
  4. retourne des MarketProposal complets, prêts à être triés/filtrés par
     agent.py.

Aucune fonction ici n'exécute d'action de jeu, ni ne modifie `state` ou
`state.market` (spec sections 5 et 33 : lecture seule).
"""

from typing import Dict, List

from .constants import (
    ACTION_PRIORITY,
    END_OF_GAME_REMAINING_DAYS,
    HOLD_URGENCY_DEFAULT,
    MARKET_PRODUCT_INFO,
    PRODUCE_URGENCY_DEFAULT,
    PRODUCTION_INFO,
    SELL_URGENCY_DEFAULT,
    SELL_URGENCY_END_OF_GAME,
    SELL_URGENCY_SHED_NEAR_CAPACITY,
)
from .models import MarketProposal, PriceAnalysis
from .rules import is_end_of_game, is_hold_attractive, is_production_attractive, is_sell_attractive, price_level
from . import scoring
from .demand import build_demand_forecast, demand_score


def analyze_prices(state) -> List[PriceAnalysis]:
    """
    PRICE_ANALYSIS (spec section 8-10) : construit une analyse par produit
    coté dans state.market.prices.

    normalized_price = current_price / base_price, où base_price est le
    prix documenté du jeu au repos (marché à I0, voir constants.py). C'est
    une comparaison à une référence FIXE et documentée, PAS un historique
    inventé (spec section 10, option B : MarketAgent v1 = analyse
    instantanée du marché, aucun historique de prix n'existe dans
    FarmState).

    Si un produit coté n'a pas de prix de base documenté, l'analyse reste
    possible mais avec une confiance réduite et un niveau "NORMAL" par
    défaut (on ne peut pas juger s'il est cher ou pas sans référence).
    """
    forecast = build_demand_forecast(state)
    analyses = []
    for product, current_price in sorted(state.market.prices.items()):
        info = MARKET_PRODUCT_INFO.get(product)
        if info is None:
            analyses.append(PriceAnalysis(
                product=product, current_price=current_price, base_price=None,
                normalized_price=0.5, price_level="NORMAL", confidence=0.3,
                demand_score=demand_score(forecast, product), expected_price_factor=forecast.expected_price_factor.get(product, 1.0),
            ))
            continue

        base_price = info["base_price"]
        normalized = current_price / base_price if base_price > 0 else 0.5
        analyses.append(PriceAnalysis(
            product=product, current_price=current_price, base_price=base_price,
            normalized_price=normalized, price_level=price_level(normalized), confidence=1.0,
            demand_score=demand_score(forecast, product), expected_price_factor=forecast.expected_price_factor.get(product, 1.0),
        ))
    return analyses


def _analyses_by_product(price_analyses: List[PriceAnalysis]) -> Dict[str, PriceAnalysis]:
    return {a.product: a for a in price_analyses}


def find_sell_opportunities(state, price_analyses: List[PriceAnalysis]) -> List[MarketProposal]:
    """
    SELL_OPPORTUNITY (spec section 11-13) : pour chaque produit réellement
    en stock (state.resources.shed) dont le prix courant n'est pas bas,
    propose de vendre le stock disponible (quantity = available_quantity,
    voir spec section 13 : ne pas inventer de stratégie de stock complexe).
    """
    analyses = _analyses_by_product(price_analyses)
    proposals = []

    for product, quantity in state.resources.shed.items():
        if quantity <= 0:
            continue
        # Le fertilisant est une ressource stratégique : le vendre alors que
        # la ferme en a peu provoque le comportement parasite SELL FERTILIZER
        # -> BUY_PRODUCT FERTILIZER observé dans les replays. On conserve un
        # buffer local ; l'EconomyAgent peut ensuite préférer une production
        # interne via les animaux.
        if product == "FERTILIZER" and int(quantity) <= 2:
            continue
        analysis = analyses.get(product)
        if analysis is None:
            # Pas de prix coté pour ce produit : impossible d'évaluer une
            # vente de façon fiable (spec section 32 : robustesse aux
            # données absentes, on ne devine pas un prix).
            continue
        if not is_sell_attractive(analysis.price_level, quantity):
            continue

        expected_value = scoring.estimate_sell_value(quantity, analysis.current_price)

        shed_near_capacity = state.risks.shed_near_capacity
        end_of_game = is_end_of_game(state.time.remaining_days, END_OF_GAME_REMAINING_DAYS)
        is_high = analysis.price_level == "HIGH"

        urgency = SELL_URGENCY_DEFAULT
        reasons = [f"Prix actuel de {product} favorable ({analysis.price_level.lower()})"]
        if shed_near_capacity:
            urgency = max(urgency, SELL_URGENCY_SHED_NEAR_CAPACITY)
            reasons.append("shed proche de sa capacité")
        if end_of_game:
            urgency = max(urgency, SELL_URGENCY_END_OF_GAME)
            reasons.append("fin de partie proche")

        priority = ACTION_PRIORITY["SELL_HIGH" if is_high else "SELL_NORMAL"]
        score = scoring.score_sell(analysis.normalized_price, expected_value, quantity)

        proposals.append(MarketProposal(
            agent="market", action="SELL", product=product, quantity=quantity,
            priority=priority, urgency=urgency, expected_value=expected_value,
            score=score, reason=", ".join(reasons), confidence=analysis.confidence,
        ))
    return proposals


def find_hold_opportunities(state, price_analyses: List[PriceAnalysis]) -> List[MarketProposal]:
    """
    HOLD_OPPORTUNITY (spec section 14) : pour chaque produit en stock dont
    le prix courant est bas, signale que vendre immédiatement semble peu
    attractif. Ce n'est qu'une proposition ("la vente immédiate semble peu
    intéressante"), jamais une injonction d'attendre.
    """
    analyses = _analyses_by_product(price_analyses)
    proposals = []

    for product, quantity in state.resources.shed.items():
        if quantity <= 0:
            continue
        analysis = analyses.get(product)
        if analysis is None:
            continue
        if not is_hold_attractive(analysis.price_level, quantity):
            continue

        # Valeur brute non réalisée : ce qu'on obtiendrait en vendant
        # maintenant, utilisée seulement comme référence descriptive.
        expected_value = scoring.estimate_sell_value(quantity, analysis.current_price)
        score = scoring.score_hold(analysis.normalized_price, quantity)

        proposals.append(MarketProposal(
            agent="market", action="HOLD", product=product, quantity=quantity,
            priority=ACTION_PRIORITY["HOLD"], urgency=HOLD_URGENCY_DEFAULT,
            expected_value=expected_value, score=score,
            reason=f"Prix actuel de {product} relativement bas : vente immédiate peu attractive",
            confidence=analysis.confidence,
        ))
    return proposals


def find_production_opportunities(state, price_analyses: List[PriceAnalysis]) -> List[MarketProposal]:
    """
    PRODUCTION_OPPORTUNITY (spec section 15) : signale qu'un produit
    végétal est actuellement intéressant à produire, sans jamais décider de
    planter (cela appartient au CropAgent, spec section 16).
    """
    analyses = _analyses_by_product(price_analyses)
    proposals = []
    remaining_days = state.time.remaining_days

    for product, product_info in PRODUCTION_INFO.items():
        analysis = analyses.get(product)
        if analysis is None:
            continue
        if not is_production_attractive(product, analysis.price_level, remaining_days):
            continue

        expected_value = scoring.estimate_produce_value(product_info, analysis.current_price)
        time_ratio = scoring.time_margin_ratio(remaining_days, product_info["first_yield_day"])
        demand = analysis.demand_score
        # La production doit suivre la demande structurelle, pas seulement le prix instantané.
        score = min(1.0, scoring.score_produce(analysis.normalized_price, expected_value, time_ratio)
                    + 0.25 * demand + 0.10 * max(0.0, analysis.expected_price_factor - analysis.normalized_price))

        proposals.append(MarketProposal(
            agent="market", action="PRODUCE", product=product, quantity=None,
            priority=ACTION_PRIORITY["PRODUCE"], urgency=min(1.0, PRODUCE_URGENCY_DEFAULT + 0.30 * demand),
            expected_value=expected_value, score=score,
            reason=f"{product}: prix {analysis.current_price:.0f}$, demande {demand:.2f}, "
                   f"facteur prix attendu {analysis.expected_price_factor:.2f}, {remaining_days}j restants",
            confidence=analysis.confidence,
        ))
    return proposals