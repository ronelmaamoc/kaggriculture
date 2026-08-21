"""
analyzers.py — Détection des tâches candidates à partir d'un FarmState.

Chaque find_*_tasks(state) :
  1. filtre les candidats via rules.py (needs_feed, needs_care...) ;
  2. calcule urgency / expected_value / cost / distance ;
  3. délègue le calcul du score final à scoring.py ;
  4. retourne des AnimalProposal complets, prêts à être triés/filtrés par agent.py.

Aucune fonction ici n'exécute d'action de jeu, ni ne modifie `state`.
"""

from typing import List, Optional

from .constants import (
    ACTION_PRIORITY,
    ANIMAL_INFO,
    CARE_URGENCY_DEFAULT,
    EXPANSION_URGENCY_DEFAULT,
    FEED_RESOURCE,
    FEED_URGENCY_CRITICAL,
    FEED_URGENCY_NORMAL,
    FERTILIZER_URGENCY_DEFAULT,
    HARVEST_URGENCY_DEFAULT,
    STRUCTURE_TO_ANIMALS,
)
from .models import AnimalProposal
from .rules import (
    can_expand,
    feed_available,
    has_fertilizer_to_collect,
    is_ready_for_harvest,
    needs_care,
    needs_feed,
)
from . import scoring
from ..market.demand import build_demand_forecast, demand_score


def _nearest_worker_distance(state, target) -> Optional[float]:
    workers = state.workers.all_workers
    if not workers:
        return None
    tx, ty = target
    return min(abs(tx - wx) + abs(ty - wy) for (wx, wy) in (w.position for w in workers))


def _price_for(state, product: str, fallback_base_price: float) -> float:
    """Prix courant du marché si connu, sinon prix de base documenté du jeu."""
    price = state.market.prices.get(product)
    return price if price is not None else fallback_base_price


def find_feed_tasks(state) -> List[AnimalProposal]:
    proposals = []
    feed_stock = state.resources.shed.get(FEED_RESOURCE, 0)
    feed_price = _price_for(state, FEED_RESOURCE, 25)

    for animal in state.animals.animals:
        if not needs_feed(animal):
            continue
        if not feed_available(feed_stock):
            # Pas de blé disponible : proposer FEED serait une action non
            # exécutable (option A de la spec : ne pas produire la proposition).
            continue

        info = ANIMAL_INFO.get(animal.animal_type)
        if info is None:
            continue

        is_critical = animal.at_risk
        urgency = FEED_URGENCY_CRITICAL if is_critical else FEED_URGENCY_NORMAL
        risk = 1.0 if is_critical else 0.0
        priority = ACTION_PRIORITY["FEED_CRITICAL" if is_critical else "FEED_NORMAL"]

        product_price = _price_for(state, info["product"], info["base_price"])
        expected_value = scoring.estimate_feed_risk_value(animal, info, product_price)

        distance = _nearest_worker_distance(state, animal.position)
        score = scoring.score_feed(urgency, expected_value, risk, feed_price, distance)

        reason = f"{animal.animal_type} non nourri aujourd'hui"
        if is_critical:
            reason += " et déjà en retard d'un jour : risque de fuite ce soir"

        proposals.append(AnimalProposal(
            agent="animal", action="FEED", target=animal.position, animal_type=animal.animal_type,
            priority=priority, urgency=urgency, expected_value=expected_value, score=score,
            reason=reason, estimated_distance=distance,
        ))
    return proposals


def find_care_tasks(state) -> List[AnimalProposal]:
    proposals = []
    for animal in state.animals.animals:
        if not needs_care(animal):
            continue

        info = ANIMAL_INFO.get(animal.animal_type)
        if info is None:
            continue

        product_price = _price_for(state, info["product"], info["base_price"])
        # CARE ne rapporte rien directement : sa valeur est le bonus banqué
        # (1 unité de production) qui sera payé au prochain cycle si
        # l'animal est aussi nourri ce jour-là (README.md, "Animal Care").
        expected_value = product_price

        distance = _nearest_worker_distance(state, animal.position)
        score = scoring.score_care(CARE_URGENCY_DEFAULT, expected_value, distance)

        proposals.append(AnimalProposal(
            agent="animal", action="CARE", target=animal.position, animal_type=animal.animal_type,
            priority=ACTION_PRIORITY["CARE"], urgency=CARE_URGENCY_DEFAULT,
            expected_value=expected_value, score=score,
            reason=f"{animal.animal_type} pas encore soigné aujourd'hui (bonus banqué au prochain cycle)",
            estimated_distance=distance,
        ))
    return proposals


def find_harvest_tasks(state) -> List[AnimalProposal]:
    proposals = []
    for animal in state.animals.animals:
        if not is_ready_for_harvest(animal):
            continue

        info = ANIMAL_INFO.get(animal.animal_type)
        if info is None:
            continue

        product_price = _price_for(state, info["product"], info["base_price"])
        expected_value = animal.yield_units * product_price

        distance = _nearest_worker_distance(state, animal.position)
        score = scoring.score_harvest(HARVEST_URGENCY_DEFAULT, expected_value, distance)

        proposals.append(AnimalProposal(
            agent="animal", action="HARVEST", target=animal.position, animal_type=animal.animal_type,
            priority=ACTION_PRIORITY["HARVEST"], urgency=HARVEST_URGENCY_DEFAULT,
            expected_value=expected_value, score=score,
            reason=f"{info['product']} prêt à récolter sur {animal.animal_type} ({animal.yield_units} unités)",
            estimated_distance=distance,
        ))
    return proposals


def find_fertilizer_tasks(state) -> List[AnimalProposal]:
    proposals = []
    for animal in state.animals.animals:
        if not has_fertilizer_to_collect(animal):
            continue

        # Le fertilisant collecté se vend/s'utilise au prix du marché du
        # fertilisant, pas au prix du produit animal (README.md : "SELL"
        # s'applique à tout produit, "FERTILIZE" utilise du FERTILIZER).
        fertilizer_price = _price_for(state, "FERTILIZER", 100)
        expected_value = 1 * fertilizer_price  # COLLECT_FERTILIZER rapporte toujours 1 unité

        distance = _nearest_worker_distance(state, animal.position)
        score = scoring.score_fertilizer(FERTILIZER_URGENCY_DEFAULT, expected_value, distance)

        proposals.append(AnimalProposal(
            agent="animal", action="COLLECT_FERTILIZER", target=animal.position, animal_type=animal.animal_type,
            priority=ACTION_PRIORITY["COLLECT_FERTILIZER"], urgency=FERTILIZER_URGENCY_DEFAULT,
            expected_value=expected_value, score=score,
            reason=f"Fertilisant disponible sur {animal.animal_type}",
            estimated_distance=distance,
        ))
    return proposals


def find_animal_investment_tasks(state) -> List[AnimalProposal]:
    """Lance puis développe l'élevage après la première rentrée agricole.

    Le visuel du leader suggère une montée en puissance par vagues : les
    premières récoltes financent d'abord une structure + un animal, puis les
    achats suivants sont déclenchés lorsque la trésorerie et le marché le
    permettent. On évite donc l'achat animal au démarrage et on privilégie
    SHEEP/COW quand leur produit est bien valorisé.
    """
    first_revenue = (
        state.time.day >= 3
        or state.resources.money > 3000.0
        or any(int(state.resources.shed.get(k, 0)) > 0 for k in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"))
    )
    if state.time.day < 2 or state.time.remaining_days < 4:
        return []

    # Si un animal est déjà acheté mais encore dans le shed : respecter la
    # chaîne réelle BUY_ANIMAL -> (BUILD_* si nécessaire) -> PICKUP -> PLACE.
    for animal_type, info in ANIMAL_INFO.items():
        if int(state.resources.shed.get(animal_type, 0)) <= 0:
            continue
        structures = [(pos, kind) for pos, kind in state.animals.empty_structures
                      if kind == info["structure_kind"]]
        build_pos = None
        if structures:
            place_pos, kind = structures[0]
        else:
            candidates = list(state.crops.empty_tiles) + list(state.crops.weed_tiles)
            if not candidates:
                return []
            workers = state.workers.all_workers
            anchor = workers[0].position if workers else (0, 0)
            place_pos = min(sorted(set(candidates)), key=lambda p: (0 if p in state.crops.empty_tiles else 1, abs(p[0]-anchor[0]) + abs(p[1]-anchor[1]), p))
            kind = info["structure_kind"]
            build_pos = place_pos

        center = state.land.board_size // 2
        shed_access = [(center-1, center-1), (center, center-1),
                       (center-1, center), (center, center)]
        workers = state.workers.all_workers
        anchor = workers[0].position if workers else shed_access[0]
        pickup_target = min(shed_access, key=lambda p: (abs(p[0]-anchor[0]) + abs(p[1]-anchor[1]), p))
        value = info["max_held"] * _price_for(state, info["product"], info["base_price"])
        proposals = []
        if build_pos is not None:
            build_action = "BUILD_COOP" if info["structure_kind"] == "COOP" else "BUILD_PASTURE"
            proposals.append(AnimalProposal(
                agent="animal", action=build_action, target=build_pos, animal_type=animal_type,
                priority=0.995, urgency=1.0, expected_value=0.0, score=0.995,
                reason=f"animal {animal_type} déjà acheté : construire {kind} avant placement",
                estimated_distance=None, quantity=1.0,
            ))
        proposals.append(AnimalProposal(
            agent="animal", action="PICKUP", target=pickup_target, animal_type=animal_type,
            priority=1.0, urgency=1.0, expected_value=0.0, score=1.0,
            reason=f"{animal_type} acheté : récupérer l'animal au shed avant placement",
            estimated_distance=None, quantity=1.0,
        ))
        proposals.append(AnimalProposal(
            agent="animal", action="PLACE", target=place_pos, animal_type=animal_type,
            priority=0.99, urgency=1.0, expected_value=value, score=0.99,
            reason=f"{animal_type} récupéré : placement dans {kind}",
            estimated_distance=None, quantity=1.0,
        ))
        return proposals

    # Limiter l'accélération initiale : un premier animal après J3, puis un
    # nouvel animal tous les ~4 jours quand le capital est suffisant.
    animal_count = len(state.animals.animals)
    desired_count = 1
    if state.time.day >= 7:
        desired_count = min(4, 1 + (state.time.day - 7) // 5)
    if animal_count >= desired_count:
        return []

    candidates = []
    demand_forecast = build_demand_forecast(state)
    for animal_type, info in sorted(ANIMAL_INFO.items()):
        product = info["product"]
        price = _price_for(state, product, info["base_price"])
        gross = info["max_held"] * price
        profit = gross - info["purchase_cost"]
        speed = 1.0 / max(1, info["first_yield_day"])
        dscore = demand_score(demand_forecast, product)
        expected_factor = demand_forecast.expected_price_factor.get(product, price / max(1.0, info["base_price"]))
        score = (
            0.40 * min(1.0, profit / 1200.0)
            + 0.18 * min(1.0, speed * 6.0)
            + 0.17 * min(1.0, price / max(1.0, info["base_price"] * 1.5))
            + 0.20 * dscore
            + 0.05 * min(1.0, max(0.0, expected_factor - 1.0))
        )
        candidates.append((score, animal_type, info, price, dscore))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    if not candidates:
        return []

    # On lance une seule nouvelle ligne à la fois : build + achat, puis
    # placement au tour suivant. Les vagues suivantes sont déclenchées par
    # les observations réelles (structure + trésorerie).
    score, animal_type, info, price, dscore = candidates[0]
    money = float(state.resources.money)
    min_cash_after = 700.0 if animal_type != "GOOSE" else 500.0
    if money - info["purchase_cost"] < min_cash_after:
        return []

    proposals: List[AnimalProposal] = []
    structure_pos = None
    for pos, kind in state.animals.empty_structures:
        if kind == info["structure_kind"]:
            structure_pos = pos
            break

    if structure_pos is None and (state.crops.empty_tiles or state.crops.weed_tiles):
        workers = state.workers.all_workers
        anchor = workers[0].position if workers else (0, 0)
        structure_pos = min(
            sorted(set(state.crops.empty_tiles + state.crops.weed_tiles)),
            key=lambda p: (0 if p in state.crops.empty_tiles else 1, abs(p[0]-anchor[0]) + abs(p[1]-anchor[1]), p),
        )
        build_action = "BUILD_COOP" if info["structure_kind"] == "COOP" else "BUILD_PASTURE"
        proposals.append(AnimalProposal(
            agent="animal", action=build_action, target=structure_pos, animal_type=animal_type,
            priority=0.94, urgency=0.94, expected_value=0.0, score=0.94,
            reason=f"première vague d'élevage après récolte : construire {info['structure_kind']} pour {animal_type}",
            estimated_distance=None, quantity=1.0,
        ))

    proposals.append(AnimalProposal(
        agent="animal", action="BUY_ANIMAL", target=None, animal_type=animal_type,
        priority=0.92, urgency=0.90,
        expected_value=gross, score=score + 0.08,
        reason=f"réinvestissement : acheter {animal_type} ({info['product']}) ; demande marché {dscore:.2f}, prix {price:.0f}$",
        estimated_distance=None, quantity=1.0,
    ))
    return proposals

def find_expansion_opportunities(state) -> List[AnimalProposal]:
    """
    Signale les structures vides (COOP/PASTURE) comme des opportunités
    d'expansion possibles. NE décide PAS d'acheter l'animal : c'est une
    décision économique globale qui appartient à un futur EconomyAgent /
    PlannerAgent (voir spec, section 17-18).
    """
    proposals = []
    remaining_days = state.time.remaining_days

    # Depuis J3, find_animal_investment_tasks porte la décision complète
    # BUY_ANIMAL + BUILD_* ; on évite ici une seconde opportunité économique
    # concurrente pour le même animal.
    if state.time.day >= 3 and not state.animals.animals:
        return proposals

    for position, structure_kind in state.animals.empty_structures:
        candidate_types = STRUCTURE_TO_ANIMALS.get(structure_kind, [])
        for animal_type in candidate_types:
            if not can_expand(animal_type, remaining_days):
                continue

            info = ANIMAL_INFO[animal_type]
            product_price = _price_for(state, info["product"], info["base_price"])
            expected_value = scoring.estimate_expansion_value(animal_type, info, product_price)

            distance = _nearest_worker_distance(state, position)
            score = scoring.score_expansion(
                EXPANSION_URGENCY_DEFAULT, expected_value, info["purchase_cost"], distance,
            )

            proposals.append(AnimalProposal(
                agent="animal", action="EXPANSION_OPPORTUNITY", target=position, animal_type=animal_type,
                priority=ACTION_PRIORITY["EXPANSION_OPPORTUNITY"], urgency=EXPANSION_URGENCY_DEFAULT,
                expected_value=expected_value, score=score,
                reason=f"{structure_kind} vide, {animal_type} pourrait y être placé "
                       f"({remaining_days}j restants >= {info['first_yield_day']}j requis)",
                estimated_distance=distance,
            ))
    return proposals