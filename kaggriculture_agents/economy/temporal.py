"""Planification économique temporelle.

Ce module transforme l'historique + l'état courant + les prévisions du
TaskCalendar en un petit calendrier économique déterministe. Il ne joue
aucune action : il mesure le coût d'attendre, le coût d'acheter et la valeur
des ressources produites en interne.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ResourceNeed:
    resource: str
    deadline: int
    quantity: float
    reason: str


@dataclass(frozen=True)
class ResourceSupply:
    resource: str
    turn: int
    quantity: float
    source: str
    value: float


@dataclass(frozen=True)
class EconomicOpportunity:
    resource: str
    quantity: float
    deadline: int
    internal_supply: float
    external_buy: float
    avoided_cost: float
    action_cost: float
    net_value: float
    reason: str


@dataclass(frozen=True)
class EconomicSchedule:
    turn: int
    day: int
    supplies: Tuple[ResourceSupply, ...]
    needs: Tuple[ResourceNeed, ...]
    opportunities: Tuple[EconomicOpportunity, ...]
    projected_resources: Dict[str, float]

    def internal_before(self, resource: str, deadline: Optional[int] = None) -> float:
        d = deadline if deadline is not None else 10**18
        return sum(s.quantity for s in self.supplies if s.resource == resource and s.turn <= d)

    def needed_before(self, resource: str, deadline: Optional[int] = None) -> float:
        d = deadline if deadline is not None else 10**18
        return sum(n.quantity for n in self.needs if n.resource == resource and n.deadline <= d)

    def avoidable_purchase(self, resource: str, deadline: Optional[int] = None) -> float:
        d = deadline if deadline is not None else 10**18
        return max(0.0, min(self.internal_before(resource, d), self.needed_before(resource, d)))


def build_economic_schedule(state, calendar) -> EconomicSchedule:
    """Construit un calendrier économique sur l'horizon du TaskCalendar.

    Le calcul est volontairement conservateur : seules les ressources
    explicitement observées ou prédites par le calendrier sont comptées.
    Une production future n'est pas traitée comme disponible avant sa date.
    """
    snap = calendar.forecast(state)
    now = int(state.time.step)
    horizon = now + int(calendar.horizon_days) * int(state.time.turns_per_day)
    supplies: List[ResourceSupply] = []
    needs: List[ResourceNeed] = []

    # Stock réel : ce qui est déjà possédé n'est pas un achat futur.
    for resource, qty in sorted(state.resources.shed.items()):
        if qty > 0:
            supplies.append(ResourceSupply(resource, now, float(qty), "stock", float(qty)))

    # Prévisions du calendrier : elles viennent des actifs réellement observés
    # (cultures/animaux) et des tâches futures du dernier schedule.
    market_prices = dict(state.market.prices)
    for item in snap.due_now:
        if item.resource in {"WATER", "CARE"}:
            continue
        value = float(market_prices.get(item.resource, 0.0))
        supplies.append(ResourceSupply(item.resource, now, float(item.quantity), item.source, value))
    for item in snap.future:
        if item.turn > horizon:
            continue
        if item.resource in {"WATER", "CARE"}:
            continue
        value = float(market_prices.get(item.resource, 0.0))
        supplies.append(ResourceSupply(item.resource, int(item.turn), float(item.quantity), item.source, value))

    # Besoins obligatoires connus. Les animaux consomment du blé chaque jour ;
    # les cultures peuvent avoir besoin d'eau, mais l'eau n'est pas une ressource
    # achetable et n'entre donc pas dans le calcul de cash.
    turns_day = max(1, int(state.time.turns_per_day))
    animal_count = len(state.animals.animals)
    if animal_count:
        for day_offset in range(min(int(calendar.horizon_days), max(1, int(state.time.remaining_days) + 1))):
            turn = now + day_offset * turns_day
            if turn > horizon:
                break
            # On ne compte que le blé comme besoin économique : CARE/WATER sont
            # des capacités d'action, pas des achats de ressources.
            needs.append(ResourceNeed("WHEAT", turn, float(animal_count), "alimentation animale"))

    # Les tâches futures du calendrier peuvent aussi révéler un besoin explicite
    # avant une production planifiée (ex. FEED prévu).
    for planned in snap.planned_future:
        if planned.turn > horizon:
            continue
        if planned.action == "FEED":
            needs.append(ResourceNeed("WHEAT", int(planned.turn), 1.0, "FEED planifié"))
        elif planned.action == "FERTILIZE":
            needs.append(ResourceNeed("FERTILIZER", int(planned.turn), 1.0, "FERTILIZE planifié"))

    supplies.sort(key=lambda x: (x.turn, x.resource, x.source))
    needs.sort(key=lambda x: (x.deadline, x.resource, x.reason))

    # Projection nette, dans l'ordre temporel, sans utiliser les fournitures
    # futures avant leur date. Le résultat est volontairement une borne haute
    # de connaissance, pas une simulation complète du jeu.
    projected: Dict[str, float] = {k: float(v) for k, v in state.resources.shed.items()}
    for resource in sorted(set(s.resource for s in supplies)):
        projected.setdefault(resource, 0.0)
    for supply in supplies:
        if supply.turn == now and supply.source == "stock":
            continue
        projected[supply.resource] = projected.get(supply.resource, 0.0) + supply.quantity

    opportunities: List[EconomicOpportunity] = []
    for resource in sorted(set(n.resource for n in needs)):
        ordered_needs = [n for n in needs if n.resource == resource]
        ordered_supply = [s for s in supplies if s.resource == resource]
        available = float(state.resources.shed.get(resource, 0.0))
        internal_used = 0.0
        for need in ordered_needs:
            # Consomme d'abord le stock courant, puis les productions internes
            # arrivées avant l'échéance.
            required = need.quantity
            from_stock = min(available, required)
            available -= from_stock
            required -= from_stock
            if required <= 0:
                continue
            for supply in ordered_supply:
                if supply.source == "stock" or supply.turn > need.deadline:
                    continue
                usable = max(0.0, supply.quantity - internal_used)
                take = min(usable, required)
                internal_used += take
                required -= take
                if required <= 0:
                    break
            if required > 0:
                price = float(market_prices.get(resource, 0.0))
                avoided = (need.quantity - required) * price
                # Acheter est l'alternative de référence ; produire en interne
                # a un coût d'action, modélisé par une petite valeur d'opportunité.
                action_cost = (need.quantity - required) * 8.0
                net = avoided - action_cost
                opportunities.append(EconomicOpportunity(
                    resource=resource,
                    quantity=need.quantity - required,
                    deadline=need.deadline,
                    internal_supply=need.quantity - required,
                    external_buy=required,
                    avoided_cost=avoided,
                    action_cost=action_cost,
                    net_value=net,
                    reason=f"production interne avant J{need.deadline // turns_day} évite un achat de {need.quantity - required:.0f} {resource}",
                ))
            else:
                price = float(market_prices.get(resource, 0.0))
                qty = need.quantity
                opportunities.append(EconomicOpportunity(
                    resource=resource, quantity=qty, deadline=need.deadline,
                    internal_supply=qty, external_buy=0.0,
                    avoided_cost=qty * price, action_cost=qty * 8.0,
                    net_value=qty * max(0.0, price - 8.0),
                    reason=f"{resource} couvert par la production interne avant l'échéance",
                ))

    opportunities.sort(key=lambda x: (-x.net_value, x.deadline, x.resource))
    return EconomicSchedule(
        turn=now, day=int(state.time.day),
        supplies=tuple(supplies), needs=tuple(needs),
        opportunities=tuple(opportunities), projected_resources=dict(sorted(projected.items())),
    )
