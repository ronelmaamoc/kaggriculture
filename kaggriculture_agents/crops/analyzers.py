"""
analyzers.py — Détection des tâches candidates à partir d'un FarmState.

Chaque find_*_tasks(state) :
  1. filtre les candidats via rules.py (is_ready_for_harvest, needs_water...) ;
  2. calcule urgency / expected_value / cost / distance ;
  3. délègue le calcul du score final à scoring.py ;
  4. retourne des CropProposal complets, prêts à être triés/filtrés par agent.py.

Aucune fonction ici n'exécute d'action de jeu, ni ne modifie `state`.
"""

from typing import List, Optional

from .constants import (
    CROP_INFO,
    FERTILIZE_URGENCY_DEFAULT,
    HARVEST_URGENCY_DECAYING,
    HARVEST_URGENCY_READY,
    PLANT_URGENCY_DEFAULT,
    WATER_URGENCY_AT_RISK,
    WATER_URGENCY_NORMAL,
    WEED_URGENCY_DEFAULT,
    WEED_SCORE_DEFAULT,
)
from .models import CropProposal
from .rules import can_be_fertilized, can_be_planted, is_ready_for_harvest, needs_water
from . import scoring
from ..market.demand import build_demand_forecast, demand_score


def _nearest_worker_distance(state, target) -> Optional[float]:
    workers = state.workers.all_workers
    if not workers:
        return None
    tx, ty = target
    return min(abs(tx - wx) + abs(ty - wy) for (wx, wy) in (w.position for w in workers))


def _price_for(state, crop_type: str) -> float:
    """Prix courant du marché si connu, sinon prix de base documenté du jeu."""
    price = state.market.prices.get(crop_type)
    if price is not None:
        return price
    info = CROP_INFO.get(crop_type)
    return info["base_price"] if info else 0.0


def find_harvest_tasks(state) -> List[CropProposal]:
    proposals = []
    for crop in state.crops.crops:
        if not is_ready_for_harvest(crop):
            continue

        info = CROP_INFO.get(crop.crop_type)
        is_decaying = info is not None and crop.age_days > info["max_yield_day"]
        urgency = HARVEST_URGENCY_DECAYING if is_decaying else HARVEST_URGENCY_READY

        price = _price_for(state, crop.crop_type)
        expected_value = crop.yield_units * price
        distance = _nearest_worker_distance(state, crop.position)

        score = scoring.score_harvest(urgency, expected_value, distance)

        proposals.append(CropProposal(
            agent="crop", action="HARVEST", target=crop.position, crop_type=crop.crop_type,
            priority=1.0, urgency=urgency, expected_value=expected_value, score=score,
            reason=f"{crop.crop_type} prêt à récolter ({crop.yield_units} unités)"
                   + (", entré en décroissance" if is_decaying else ""),
            estimated_distance=distance,
        ))
    return proposals


def find_weed_tasks(state) -> List[CropProposal]:
    """Retire les mauvaises herbes qui bloquent les cases productives."""
    proposals = []
    for position in sorted(state.crops.weed_tiles):
        distance = _nearest_worker_distance(state, position)
        total_tiles = max(1, len(state.crops.empty_tiles) + len(state.crops.weed_tiles) + len(state.crops.crops))
        pressure = min(1.0, len(state.crops.weed_tiles) / total_tiles)
        urgency = min(1.0, WEED_URGENCY_DEFAULT + 0.08 * pressure)
        score = min(1.0, WEED_SCORE_DEFAULT + 0.06 * pressure - 0.01 * min(distance or 0.0, 10.0))
        proposals.append(CropProposal(
            agent="crop", action="DUG", target=position, crop_type=None,
            priority=0.88, urgency=urgency, expected_value=120.0 + 180.0 * pressure,
            score=score, reason=f"mauvaise herbe à retirer pour libérer la case {position}",
            estimated_distance=distance, quantity=1.0,
        ))
    return proposals


def find_water_tasks(state) -> List[CropProposal]:
    proposals = []
    for crop in state.crops.crops:
        if not needs_water(crop):
            continue

        urgency = WATER_URGENCY_AT_RISK if crop.at_risk else WATER_URGENCY_NORMAL
        risk = 1.0 if crop.at_risk else 0.0

        price = _price_for(state, crop.crop_type)
        info = CROP_INFO.get(crop.crop_type)
        seed_cost = info["seed_cost"] if info else 0.0
        # Valeur en jeu = investissement déjà englouti (graine) + rendement
        # déjà acquis sur la case, qui seraient perdus si la culture devient
        # une weed faute d'arrosage.
        expected_value = seed_cost + crop.yield_units * price

        distance = _nearest_worker_distance(state, crop.position)
        score = scoring.score_water(urgency, expected_value, risk, distance)

        reason = "Culture non arrosée aujourd'hui"
        if crop.at_risk:
            reason += " et à risque de devenir une weed dès demain"

        proposals.append(CropProposal(
            agent="crop", action="WATER", target=crop.position, crop_type=crop.crop_type,
            priority=0.9, urgency=urgency, expected_value=expected_value, score=score,
            reason=reason, estimated_distance=distance,
        ))
    return proposals


def find_plant_tasks(state) -> List[CropProposal]:
    proposals = []
    seeds = state.resources.seeds
    remaining_days = state.time.remaining_days

    owned_types = [crop_type for crop_type, count in seeds.items() if count > 0]
    if not owned_types:
        return proposals

    for position in state.crops.empty_tiles:
        for crop_type in owned_types:
            if not can_be_planted(crop_type, seeds, remaining_days):
                continue

            info = CROP_INFO[crop_type]
            price = _price_for(state, crop_type)
            # Heuristique simple de profit potentiel : rendement max théorique
            # au prix courant, moins le coût de la graine. Ce n'est pas une
            # prédiction exacte (pas de simulation d'arrosage/fertilisation
            # future), juste un ordre de grandeur pour comparer les options.
            expected_value = max(info["max_yield"] * price - info["seed_cost"], 0.0)

            distance = _nearest_worker_distance(state, position)
            score = scoring.score_plant(
                PLANT_URGENCY_DEFAULT, expected_value, info["seed_cost"], distance,
            )

            proposals.append(CropProposal(
                agent="crop", action="PLANT", target=position, crop_type=crop_type,
                priority=0.4, urgency=PLANT_URGENCY_DEFAULT, expected_value=expected_value,
                score=score,
                reason=f"Case libre, graine {crop_type} disponible, "
                       f"{remaining_days}j restants (>= {info['first_yield_day']}j requis)",
                estimated_distance=distance,
            ))
    return proposals


def find_seed_purchase_tasks(state) -> List[CropProposal]:
    """Construit le portefeuille de semences pour le prochain cycle.

    Stratégie observée sur les captures du meilleur agent :
      1. amorçage très agressif avec des cultures rapides WHEAT/CARROT afin
         d'obtenir la première rentrée autour de J2-J3 ;
      2. après cette première rentrée, bascule vers les cultures à forte
         valeur par jour (MELON/STRAWBERRY/TOMATO), en conservant WHEAT/CARROT
         si le marché ou le temps restant les rend meilleurs ;
      3. acheter assez de graines pour alimenter toutes les cases libres,
         plutôt que d'attendre d'être totalement à zéro.

    Cette fonction ne décide jamais d'un ordre Kaggriculture : elle produit
    uniquement BUY_SEED, ensuite arbitré par Economy/Planner/Critic.
    """
    if state.time.remaining_days <= 0:
        return []

    free_tiles = len(state.crops.empty_tiles) + len(state.crops.weed_tiles)
    demand_forecast = build_demand_forecast(state)
    current_seeds = {k: int(v) for k, v in state.resources.seeds.items()}
    money = float(state.resources.money)
    first_revenue = money > 3000.0 or any(
        int(state.resources.shed.get(k, 0)) > 0
        for k in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
    ) or state.time.day >= 3

    # Phase 1 : premier cycle très rapide. Deux cultures seulement afin que
    # les workers puissent planter/récolter en parallèle sans disperser le
    # portefeuille.
    if not first_revenue:
        candidate_types = ("WHEAT", "CARROT")
    else:
        candidate_types = tuple(CROP_INFO.keys())

    candidates = []
    for crop_type in candidate_types:
        info = CROP_INFO[crop_type]
        if state.time.remaining_days < info["first_yield_day"]:
            continue
        price = float(state.market.prices.get(crop_type, info["base_price"]))
        seed_cost = float(info["seed_cost"])
        # Profit/jour : critère principal du portefeuille. La tendance du
        # marché est approximée ici par le prix courant; MarketAgent garde
        # l'historique et pilote les ventes séparément.
        gross = info["max_yield"] * price
        profit = max(0.0, gross - seed_cost)
        per_day = profit / max(1, info["first_yield_day"])
        speed_bonus = 1.0 / max(1, info["first_yield_day"])
        # Pendant le premier cycle, la vitesse domine explicitement la valeur.
        if not first_revenue:
            score = 0.70 * min(1.0, speed_bonus * 2.0) + 0.30 * min(1.0, profit / 150.0)
        else:
            score = 0.65 * min(1.0, per_day / 180.0) + 0.25 * min(1.0, price / max(1.0, info["base_price"] * 1.5)) + 0.10 * min(1.0, speed_bonus * 4.0)
        dscore = demand_score(demand_forecast, crop_type)
        expected_factor = demand_forecast.expected_price_factor.get(crop_type, price / max(1.0, info["base_price"]))
        # La demande structurelle compte davantage après la première rentrée.
        score = min(1.0, score + (0.28 * dscore if first_revenue else 0.10 * dscore)
                    + 0.08 * max(0.0, expected_factor - price / max(1.0, info["base_price"])))
        candidates.append((score, crop_type, info, price, profit, per_day, dscore))

    if not candidates:
        return []
    candidates.sort(key=lambda x: (-x[0], x[1]))

    # On remplit les cases libres. Au démarrage, WHEAT/CARROT sont répartis
    # 60/40 ; ensuite la meilleure culture prend la majorité et la seconde
    # sert de diversification si elle est économiquement proche.
    selected = candidates[:2] if len(candidates) > 1 else candidates[:1]
    proposals: List[CropProposal] = []
    remaining_tiles = free_tiles

    if len(selected) == 1:
        allocations = [(selected[0], remaining_tiles)]
    else:
        if not first_revenue:
            first_qty = max(1, int(round(remaining_tiles * 0.60)))
        else:
            d1, d2 = selected[0][6], selected[1][6]
            # Quantité proportionnelle à la demande des boutiques, avec un
            # plafond pour conserver une diversification minimale.
            demand_ratio = d1 / max(0.01, d1 + d2)
            quality_ratio = 0.70 if selected[0][0] - selected[1][0] > 0.10 else 0.55
            first_ratio = max(0.45, min(0.80, 0.55 * quality_ratio / 0.55 + 0.45 * demand_ratio))
            first_qty = max(1, int(round(remaining_tiles * first_ratio)))
        allocations = [(selected[0], first_qty), (selected[1], remaining_tiles - first_qty)]

    # Les graines déjà disponibles sont déduites : on n'achète que le déficit.
    # Au premier cycle, un petit buffer de 10 graines permet de replanter sans
    # attendre la prochaine observation; après la première récolte on évite
    # d'immobiliser trop de capital en semences.
    buffer = min(10, max(0, free_tiles // 4)) if not first_revenue else min(5, max(0, free_tiles // 8))
    for idx, (candidate, target_qty) in enumerate(allocations):
        _score, crop_type, info, price, profit, _per_day, _demand = candidate
        current = current_seeds.get(crop_type, 0)
        desired = target_qty + (buffer if idx == 0 else 0)
        qty = max(0, desired - current)
        if qty <= 0:
            continue
        # En phase de production, on peut engager jusqu'à 90% du cash dans
        # les graines : c'est volontairement agressif et conforme au visuel.
        max_qty_by_cash = int(max(0.0, money * (0.90 if not first_revenue else 0.75)) // info["seed_cost"])
        qty = min(qty, max_qty_by_cash)
        if qty <= 0:
            continue
        cost = qty * info["seed_cost"]
        proposals.append(CropProposal(
            agent="crop", action="BUY_SEED", target=None, crop_type=crop_type,
            priority=0.98 if not first_revenue else 0.72,
            urgency=0.98 if not first_revenue else 0.62,
            expected_value=qty * info["max_yield"] * price,
            score=float(_score),
            reason=(f"cycle {'initial rapide' if not first_revenue else 'réinvestissement'} : "
                    f"acheter {qty} graine(s) {crop_type} pour remplir {target_qty} case(s) libres"),
            confidence=1.0, estimated_distance=None, quantity=float(qty),
        ))
        money -= cost
    return proposals

def find_fertilize_tasks(state) -> List[CropProposal]:
    proposals = []
    fertilizer_available = state.resources.shed.get("FERTILIZER", 0)

    for crop in state.crops.crops:
        if not can_be_fertilized(crop, fertilizer_available):
            continue

        info = CROP_INFO.get(crop.crop_type)
        if info is None:
            continue

        price = _price_for(state, crop.crop_type)
        expected_value = scoring.estimate_fertilize_value(crop, info, price)
        distance = _nearest_worker_distance(state, crop.position)
        score = scoring.score_fertilize(FERTILIZE_URGENCY_DEFAULT, expected_value, distance)

        proposals.append(CropProposal(
            agent="crop", action="FERTILIZE", target=crop.position, crop_type=crop.crop_type,
            priority=0.6, urgency=FERTILIZE_URGENCY_DEFAULT, expected_value=expected_value,
            score=score, reason=f"Fertilisant disponible, {crop.crop_type} encore en croissance",
            estimated_distance=distance,
        ))
    return proposals
