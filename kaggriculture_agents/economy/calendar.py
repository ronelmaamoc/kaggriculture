"""Calendrier économique persistant de la ferme.

Le calendrier est la mémoire longue du système multi-agent. Il conserve :
- les actions réellement exécutées depuis le début de la partie ;
- les derniers états observés et les transitions de ressources ;
- les actifs persistants (cultures, animaux, workers) et leurs échéances ;
- les ressources qui devraient devenir disponibles dans les prochains tours ;
- les achats qui peuvent être évités parce qu'une production interne arrive.

Il ne décide jamais d'une action Kaggriculture. Il fournit uniquement un
forecast déterministe à EconomyAgent/Planner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..animals.constants import ANIMAL_INFO
from ..crops.constants import CROP_INFO
from .temporal import build_economic_schedule, EconomicSchedule


@dataclass(frozen=True)
class TaskEvent:
    turn: int
    day: int
    action: str
    product: Optional[str]
    target: Optional[object]
    worker_id: Optional[str]
    success: bool
    estimated_cash_cost: float = 0.0
    action_cost: float = 1.0


@dataclass(frozen=True)
class PlannedTask:
    turn: int
    action: str
    product: Optional[str]
    target: Optional[object]
    worker_id: Optional[str]


@dataclass(frozen=True)
class ForecastItem:
    turn: int
    day: int
    resource: str
    quantity: float
    source: str
    target: Optional[object] = None


@dataclass(frozen=True)
class CalendarSnapshot:
    current_turn: int
    current_day: int
    history_size: int
    last_actions: Tuple[TaskEvent, ...]
    due_now: Tuple[ForecastItem, ...]
    future: Tuple[ForecastItem, ...]
    planned_future: Tuple[PlannedTask, ...]
    owned_resources: Dict[str, float]


class TaskCalendar:
    """Mémoire persistante, une instance par partie."""

    def __init__(self, horizon_days: int = 14, history_limit: int = 4000) -> None:
        self.horizon_days = horizon_days
        self.history_limit = history_limit
        self._events: List[TaskEvent] = []
        self._last_turn: Optional[int] = None
        self._last_state = None
        self._observed_turns: set[int] = set()
        self._planned: List[PlannedTask] = []

    # ------------------------------------------------------------------ #
    # Mémoire de partie
    # ------------------------------------------------------------------ #
    def observe(self, state) -> None:
        """Enregistre une observation sans la muter.

        Un reset de step signifie une nouvelle partie : la mémoire est alors
        réinitialisée pour éviter de transporter les actifs d'une ancienne
        partie dans la suivante.
        """
        turn = int(state.time.step)
        if self._last_turn is not None and turn < self._last_turn:
            self.reset()
        self._last_turn = turn
        self._last_state = state
        self._observed_turns.add(turn)

    def record_execution(self, execution_result, state) -> None:
        """Ajoute uniquement les actions effectivement réussies au journal."""
        turn = int(state.time.step)
        day = int(state.time.day)
        for step in getattr(execution_result, "executed_steps", ()):
            if not step.success:
                continue
            action = tuple(step.action)
            act = action[0] if action else "PASS"
            product = getattr(step, "product", None) or (action[1] if len(action) > 1 and act in {
                "PLANT", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "PLACE"
            } else None)
            qty = float(getattr(step, "quantity", 1.0) or 1.0)
            price = float(getattr(state.market, "prices", {}).get(product, 0.0)) if product else 0.0
            # Le journal garde un coût d'action pour mesurer l'opportunité
            # perdue : une action worker consomme un slot, un ordre marché
            # consomme un slot marché. Le coût cash est une estimation au
            # prix observé AVANT l'action, utile pour le bilan historique.
            cash_cost = 0.0
            if act in {"BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"}:
                cash_cost = price * qty
            elif act in {"SELL"}:
                cash_cost = -price * qty
            self._events.append(TaskEvent(
                turn=turn, day=day, action=act, product=product,
                target=getattr(step, "target", None) or getattr(step, "plan_step_id", None),
                worker_id=step.worker_id, success=True,
                estimated_cash_cost=cash_cost, action_cost=1.0,
            ))
        if len(self._events) > self.history_limit:
            self._events = self._events[-self.history_limit:]

    def record_schedule(self, schedule) -> None:
        """Mémorise les étapes futures du dernier schedule.

        Les étapes passées sont remplacées par le nouveau plan : le système
        replannifie chaque tour, donc conserver plusieurs plans futurs
        concurrents serait faux.
        """
        self._planned = []
        for step in getattr(schedule, "steps", ()):
            turn = int(getattr(step, "estimated_turn", 0))
            if self._last_turn is not None and turn <= self._last_turn:
                continue
            self._planned.append(PlannedTask(
                turn=turn, action=str(step.action), product=getattr(step, "product", None),
                target=getattr(step, "target", None), worker_id=getattr(step, "worker_id", None),
            ))
        self._planned.sort(key=lambda x: (x.turn, x.action, str(x.product), str(x.target)))

    def reset(self) -> None:
        self._events.clear()
        self._last_turn = None
        self._last_state = None
        self._observed_turns.clear()
        self._planned.clear()

    @property
    def history(self) -> Tuple[TaskEvent, ...]:
        return tuple(self._events)

    def count(self, action: str, product: Optional[str] = None) -> int:
        return sum(1 for e in self._events if e.action == action and (product is None or e.product == product))

    def historical_cost(self, action: Optional[str] = None) -> float:
        """Coût cash estimé cumulé des actions réellement réussies."""
        return sum(e.estimated_cash_cost for e in self._events if action is None or e.action == action)

    def historical_action_count(self, action: Optional[str] = None) -> int:
        return sum(1 for e in self._events if action is None or e.action == action)

    def historical_product_count(self, action: str, product: str) -> int:
        return sum(1 for e in self._events if e.action == action and e.product == product)

    # ------------------------------------------------------------------ #
    # Prévisions déterministes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _turn_for_day(state, day: int) -> int:
        return max(int(state.time.step), int(day) * int(state.time.turns_per_day))

    def forecast(self, state) -> CalendarSnapshot:
        """Construit le calendrier à partir des actifs observés.

        Le calendrier ne suppose pas qu'une récolte future existe si l'actif
        n'est pas actuellement présent dans FarmState. Il utilise planted_day /
        placed_day et les tables documentées des cultures/animaux.
        """
        self.observe(state)
        current = int(state.time.step)
        due: List[ForecastItem] = []
        future: List[ForecastItem] = []

        # Cultures : récolte future + entretien immédiat.
        for crop in state.crops.crops:
            info = CROP_INFO.get(crop.crop_type)
            if crop.needs_water:
                due.append(ForecastItem(current, state.time.day, "WATER", 0, "crop", crop.position))
            if crop.ready_to_harvest:
                due.append(ForecastItem(current, state.time.day, crop.crop_type, crop.yield_units, "crop_harvest", crop.position))
            if info:
                harvest_day = int(crop.planted_day) + int(info["first_yield_day"])
                harvest_turn = self._turn_for_day(state, harvest_day)
                if harvest_turn > current and harvest_turn <= current + self.horizon_days * state.time.turns_per_day:
                    future.append(ForecastItem(harvest_turn, harvest_day, crop.crop_type, max(1, int(info["max_yield"])), "crop_harvest", crop.position))

        # Animaux : feed/care/fertilizer/production.
        for animal in state.animals.animals:
            if animal.needs_feed:
                due.append(ForecastItem(current, state.time.day, "WHEAT", 1, "animal_feed", animal.position))
            if animal.needs_care:
                due.append(ForecastItem(current, state.time.day, "CARE", 0, "animal_care", animal.position))
            if animal.fertilizer_available:
                due.append(ForecastItem(current, state.time.day, "FERTILIZER", 1, "animal_fertilizer", animal.position))
            info = ANIMAL_INFO.get(animal.animal_type)
            if info:
                yield_day = int(animal.placed_day) + int(info["first_yield_day"])
                yield_turn = self._turn_for_day(state, yield_day)
                if yield_turn > current and yield_turn <= current + self.horizon_days * state.time.turns_per_day:
                    future.append(ForecastItem(yield_turn, yield_day, info["product"], max(1, int(info["max_held"])), "animal_harvest", animal.position))

        # Les actions déjà planifiées par le Coordinator deviennent aussi
        # des événements futurs du calendrier. On ne fait confiance qu'aux
        # actions productrices de ressources : elles peuvent éviter un achat
        # futur tant que le plan reste valide.
        for planned in self._planned:
            if planned.turn <= current:
                continue
            if planned.action == "HARVEST" and planned.product:
                future.append(ForecastItem(planned.turn, planned.turn // max(1, state.time.turns_per_day), planned.product, 1, "planned_harvest", planned.target))
            elif planned.action == "COLLECT_FERTILIZER":
                future.append(ForecastItem(planned.turn, planned.turn // max(1, state.time.turns_per_day), "FERTILIZER", 1, "planned_fertilizer", planned.target))
            elif planned.action == "BUY_PRODUCT" and planned.product:
                future.append(ForecastItem(planned.turn, planned.turn // max(1, state.time.turns_per_day), planned.product, 1, "planned_purchase", planned.target))

        # Tri stable : échéance puis source puis cible.
        due.sort(key=lambda x: (x.turn, x.source, str(x.target)))
        future.sort(key=lambda x: (x.turn, x.source, str(x.target)))

        owned: Dict[str, float] = {}
        for k, v in state.resources.seeds.items():
            owned[f"SEED_{k}"] = float(v)
        for k, v in state.resources.shed.items():
            owned[k] = float(v)

        return CalendarSnapshot(
            current_turn=current,
            current_day=int(state.time.day),
            history_size=len(self._events),
            last_actions=tuple(self._events[-20:]),
            due_now=tuple(due),
            future=tuple(future),
            planned_future=tuple(self._planned),
            owned_resources=owned,
        )

    # ------------------------------------------------------------------ #
    # Analyse économique utilisée par EconomyAgent
    # ------------------------------------------------------------------ #
    def internal_supply_before(self, state, resource: str, deadline_turn: Optional[int] = None) -> float:
        """Quantité que la ferme devrait produire avant une échéance."""
        snap = self.forecast(state)
        deadline = deadline_turn if deadline_turn is not None else int(state.time.step) + self.horizon_days * state.time.turns_per_day
        return sum(item.quantity for item in snap.future if item.resource == resource and item.turn <= deadline)

    def has_due_internal_supply(self, state, resource: str) -> bool:
        snap = self.forecast(state)
        return any(item.resource == resource for item in snap.due_now) or self.internal_supply_before(state, resource, int(state.time.step)) > 0

    def purchase_penalty(self, state, action: str, product: Optional[str], quantity: float = 1.0) -> Tuple[float, str]:
        """Retourne une pénalité économique si un achat est inutile/redondant.

        Valeur entre 0 et 1 : 1 = achat presque certainement inutile, 0 =
        aucune raison de le pénaliser.
        """
        if action not in {"BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"} or not product:
            return 0.0, ""

        snap = self.forecast(state)
        owned = snap.owned_resources.get(product, 0.0)
        if action == "BUY_PRODUCT":
            # Une ressource disponible maintenant doit toujours battre son achat.
            if owned >= quantity:
                return 1.0, f"achat {product} redondant : stock mémoire {owned:.0f}"
            # Production interne déjà due : attendre/collecter est meilleur que BUY_PRODUCT.
            if self.has_due_internal_supply(state, product):
                return 0.90, f"achat {product} pénalisé : production interne disponible aujourd'hui"
            # Production future avant le prochain besoin : pénalité partielle.
            supply = self.internal_supply_before(state, product)
            if supply >= quantity:
                return 0.65, f"achat {product} pénalisé : ~{supply:.0f} unité(s) déjà prévues par la ferme"

        if action == "BUY_ANIMAL":
            # Si un animal identique est déjà dans le shed, ne pas en racheter
            # un second sans signal d'expansion explicite.
            if owned >= quantity:
                return 0.95, f"{product} déjà acheté et mémorisé dans le shed"

        return 0.0, ""

    def task_priority(self, state, action: str, product: Optional[str] = None) -> float:
        """Priorité temporelle : ce qui est dû aujourd'hui domine le reste."""
        snap = self.forecast(state)
        if action == "WATER" and any(x.source == "crop" for x in snap.due_now):
            return 1.0
        if action == "HARVEST" and any(x.source in {"crop_harvest", "animal_harvest"} and (product is None or x.resource == product) for x in snap.due_now):
            return 1.0
        if action == "COLLECT_FERTILIZER" and any(x.source == "animal_fertilizer" for x in snap.due_now):
            return 0.95
        if action in {"FEED", "CARE"} and any(x.source in {"animal_feed", "animal_care"} for x in snap.due_now):
            return 0.98
        return 0.35


    def economic_schedule(self, state) -> EconomicSchedule:
        """Retourne le calendrier économique temporel courant.

        Le résultat est reconstruit à partir de l'historique réel et de
        l'observation courante : aucune prédiction précédente n'est prise
        comme un fait.
        """
        return build_economic_schedule(state, self)

    def describe(self, state) -> str:
        snap = self.forecast(state)
        due = ", ".join(f"{x.source}:{x.resource}" for x in snap.due_now[:12]) or "aucune"
        future = ", ".join(f"J{x.day}:{x.resource}({x.quantity:.0f})" for x in snap.future[:12]) or "aucune"
        return f"mémoire={snap.history_size} actions; dues={due}; futures={future}"
