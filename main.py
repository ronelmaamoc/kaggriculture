"""
main.py — Orchestrateur du pipeline multi-agent Kaggriculture.

INSPECTION PRÉALABLE (spec section 1, 8) : la SEULE interface réelle avec
Kaggriculture est `agent(obs) -> dict` (voir
`kaggriculture_agents/executor/constants.py`, "DÉCOUVERTE IMPORTANTE" ; confirmé par
README.md du jeu, exemple `my_agent(obs)`). Ce module respecte ce contrat
exactement, sans l'altérer.

Ce fichier ne contient AUCUNE règle métier : uniquement
l'enchaînement des appels entre agents spécialisés, avec les signatures réelles découvertes à l'inspection :

    PerceptionAgent.analyze(obs) -> FarmState
    CropAgent.decide(state) -> list[CropProposal]
    AnimalAgent.decide(state) -> list[AnimalProposal]
    MarketAgent.decide(state) -> list[MarketProposal]
    EconomyAgent.decide(state, crop, animal, market) -> list[EconomyProposal]
    PlannerAgent.plan(state, economy_proposals) -> Plan
    CriticAgent.evaluate(state, plan) -> Critique
    CoordinatorAgent.coordinate(state, plan, critique) -> ExecutionSchedule
    ExecutorAgent.execute(state, schedule) -> ExecutionResult   (.turn_actions est le dict final)

Séparation persistant / par-tour (spec section 9) :
  - les instances d'agents (`self._perception`, ..., `self._executor`) sont
    créées UNE SEULE FOIS dans `__init__` et réutilisées à chaque tour —
    c'est en particulier indispensable pour `ExecutorAgent`, dont
    l'idempotence (spec section 26) repose sur une mémoire interne
    (`_completed_batches`) qui doit survivre d'un tour à l'autre ;
  - le `Blackboard`, lui, est recréé À CHAQUE tour dans `run()` : aucune
    hypothèse sur la ferme ne doit survivre d'une observation à la suivante
    (spec section 9, 11).
"""

from typing import Optional

from kaggriculture_agents.animals.agent import AnimalAgent
from kaggriculture_agents.coordinator.agent import CoordinatorAgent
from kaggriculture_agents.coordinator.daily_planner import DailyPlan, build_daily_plan
from kaggriculture_agents.coordinator.models import ExecutionSchedule, ExecutionStep, ScheduleStatus
from kaggriculture_agents.critic.agent import CriticAgent
from kaggriculture_agents.crops.agent import CropAgent
from kaggriculture_agents.economy.agent import EconomyAgent
from kaggriculture_agents.economy.calendar import TaskCalendar
from kaggriculture_agents.executor.agent import ExecutorAgent
from kaggriculture_agents.executor.constants import DEFAULT_TURN_ACTIONS
from kaggriculture_agents.market.agent import MarketAgent
from kaggriculture_agents.investment.agent import InvestmentAgent
from kaggriculture_agents.perception.agent import PerceptionAgent, PerceptionError
from kaggriculture_agents.planner.agent import PlannerAgent
from core.blackboard import Blackboard
from utils.logging import LoggerRegistry
from utils.trace import DecisionTrace


class KaggricultureOrchestrator:
    """
    Enchaîne le pipeline complet pour un tour donné. Une seule instance
    doit être créée par partie (voir module docstring, "Séparation
    persistant / par-tour") — c'est ce que fait le singleton exposé par
    `agent(obs)` en bas de ce fichier.
    """

    def __init__(self, log: bool = False, trace_path: Optional[str] = None) -> None:
        self._perception = PerceptionAgent()
        self._crop_agent = CropAgent()
        self._animal_agent = AnimalAgent()
        self._market_agent = MarketAgent()
        self._investment_agent = InvestmentAgent()
        self._economy_agent = EconomyAgent()
        # Mémoire persistante de la partie : calendrier des tâches, ressources
        # produites/attendues et actions effectivement exécutées.
        self._task_calendar = TaskCalendar()
        self._planner_agent = PlannerAgent()
        self._critic_agent = CriticAgent()
        self._coordinator_agent = CoordinatorAgent()
        self._executor_agent = ExecutorAgent()
        self._loggers = LoggerRegistry(emit=log)
        self._trace = DecisionTrace(trace_path) if trace_path else DecisionTrace(enabled=False)
        self._last_seen_step: Optional[int] = None
        self._daily_plan: Optional[DailyPlan] = None
        self._daily_plan_day: Optional[int] = None

    def reset_episode(self) -> None:
        """Réinitialise TOUT l'état persistant entre deux épisodes.

        Le runner local peut réutiliser le même callable `agent` pour plusieurs
        parties (batch). Sans ce reset, l'historique du MarketAgent, le
        calendrier et l'idempotence de l'Executor contaminent la partie suivante.
        """
        self._task_calendar.reset()
        self._executor_agent.reset()
        for component in (self._market_agent, self._crop_agent, self._animal_agent,
                          self._economy_agent, self._planner_agent, self._critic_agent,
                          self._coordinator_agent):
            reset = getattr(component, "reset", None)
            if callable(reset):
                reset()
        self._last_seen_step = None
        self._daily_plan = None
        self._daily_plan_day = None
        self._trace.reset_episode()

    def run(self, obs: dict) -> dict:
        """
        Point d'entrée d'UN tour. Ne lève jamais d'exception vers
        l'appelant (spec section 10, 13 : "une erreur d'un agent ne doit
        pas provoquer silencieusement une action incohérente" -> ici, une
        erreur à n'importe quelle étape retombe sur l'action neutre
        `DEFAULT_TURN_ACTIONS` plutôt que de faire planter la partie).
        """
        current_step = int(obs.get("step", 0)) if isinstance(obs, dict) else 0
        # step=0 est le marqueur fiable d'un nouvel épisode pour Kaggriculture.
        if current_step == 0 and self._last_seen_step is not None and self._last_seen_step != 0:
            self.reset_episode()
        self._last_seen_step = current_step
        blackboard = Blackboard()
        perception_logger = self._loggers.get("perception")

        try:
            state = self._perception.analyze(obs)
        except PerceptionError as exc:
            perception_logger.error("Échec de la perception, action de repli", error=str(exc))
            return dict(DEFAULT_TURN_ACTIONS)
        except Exception as exc:  # défensif : une obs structurellement inattendue ne doit jamais planter la partie
            perception_logger.error("Erreur inattendue en perception, action de repli", error=str(exc))
            return dict(DEFAULT_TURN_ACTIONS)

        blackboard.set_state(state)
        self._task_calendar.observe(state)
        perception_logger.info("FarmState construit", turn=state.time.step)

        # Le pipeline multi-agent EST la stratégie : chaque agent spécialisé
        # produit une décision/proposition consommée par l'agent suivant.
        # Aucun contrôleur monolithique parallèle ne doit prendre la main.
        try:
            execution_result = self._run_pipeline(state, blackboard)
            actions = execution_result.turn_actions if hasattr(execution_result, "turn_actions") else (execution_result if isinstance(execution_result, dict) else dict(DEFAULT_TURN_ACTIONS))
            validated = _validate_turn_actions(actions, state)
            self._trace.write(
                turn=state.time.step, state=state, crop=blackboard.get_crop_analysis(),
                animal=blackboard.get_animal_analysis(), market=blackboard.get_market_analysis(),
                investment=blackboard.get_investment_analysis(), economy=blackboard.get_economic_analysis(),
                plan=blackboard.get_plan(), critique=blackboard.get_critique(),
                schedule=blackboard.get_execution_schedule(), execution=blackboard.get_execution_result(),
                final_actions=validated, calendar=self.calendar_snapshot(state), daily_plan=self._daily_plan,
            )
            self._loggers.get("orchestrator").info(
                "Décision multi-agent exécutée",
                turn=state.time.step,
                market_orders=len(validated.get("market", [])),
                farmer_action=validated.get("farmer", ["PASS"])[0],
            )
            return validated
        except Exception as exc:
            fallback = dict(DEFAULT_TURN_ACTIONS)
            self._trace.write(
                turn=state.time.step, state=state, crop=blackboard.get_crop_analysis(),
                animal=blackboard.get_animal_analysis(), market=blackboard.get_market_analysis(),
                investment=blackboard.get_investment_analysis(), economy=blackboard.get_economic_analysis(),
                plan=blackboard.get_plan(), critique=blackboard.get_critique(),
                schedule=blackboard.get_execution_schedule(), execution=blackboard.get_execution_result(),
                final_actions=fallback, calendar=self.calendar_snapshot(state), daily_plan=self._daily_plan, error=str(exc),
            )
            self._loggers.get("orchestrator").error(
                "Erreur dans le pipeline multi-agent, action de repli",
                turn=state.time.step,
                error=str(exc),
            )
            return fallback

    def _run_pipeline(self, state, blackboard: Blackboard) -> dict:
        turn = state.time.step

        crop_proposals = self._crop_agent.decide(state)
        blackboard.set_crop_analysis(crop_proposals)
        self._loggers.get("crop").info("Propositions générées", turn=turn, count=len(crop_proposals))

        animal_proposals = self._animal_agent.decide(state)
        blackboard.set_animal_analysis(animal_proposals)
        self._loggers.get("animal").info("Propositions générées", turn=turn, count=len(animal_proposals))

        market_proposals = self._market_agent.decide(state)
        blackboard.set_market_analysis(market_proposals)
        self._loggers.get("market").info("Propositions générées", turn=turn, count=len(market_proposals))

        investment_proposals = self._investment_agent.decide(
            state, crop_proposals, animal_proposals, market_proposals,
        )
        blackboard.set_investment_analysis(investment_proposals)
        self._loggers.get("investment").info(
            "Intentions d'investissement générées", turn=turn, count=len(investment_proposals)
        )

        economy_proposals = self._economy_agent.decide(
            state, crop_proposals, animal_proposals, market_proposals, investment_proposals,
            calendar=self._task_calendar,
        )
        blackboard.set_economic_analysis(economy_proposals)
        self._loggers.get("economy").info("Synthèse économique produite", turn=turn, count=len(economy_proposals))

        plan = self._planner_agent.plan(state, economy_proposals)
        blackboard.set_plan(plan)
        self._loggers.get("planner").info("Plan produit", turn=turn, steps=len(plan.steps))

        critique = self._critic_agent.evaluate(state, plan)
        blackboard.set_critique(critique)
        self._loggers.get("critic").info("Plan évalué", turn=turn, status=critique.status.value)

        schedule = self._coordinator_agent.coordinate(state, plan, critique)
        self._task_calendar.record_schedule(schedule)

        # V5.9 : le plan opérationnel est REPLANIFIÉ à chaque observation.
        # Un plan journalier figé devient obsolète dès qu'une action modifie
        # la ferme (PLANT, HARVEST, DIG, PLACE, etc.). Cette replanification
        # est volontairement légère : build_daily_plan ne retient que les
        # tâches immédiatement actionnables (phase 0) et recalcule les routes
        # depuis les positions réelles des workers.
        self._daily_plan = build_daily_plan(state, plan, start_hour=int(state.time.hour))
        self._daily_plan_day = int(state.time.day)
        self._loggers.get("coordinator").info(
            "Plan opérationnel dynamique construit",
            turn=turn, day=state.time.day, hour=state.time.hour,
            workers=len(self._daily_plan.workers),
            desired_workers=self._daily_plan.desired_workers,
            recommended_hires=self._daily_plan.recommended_hires,
            tasks=len(self._daily_plan.tasks),
            movement=self._daily_plan.movement_count,
            maintenance=self._daily_plan.maintenance_count,
            harvest=self._daily_plan.harvest_count,
        )

        daily_worker_schedule = self._build_daily_worker_schedule(state, self._daily_plan)
        blackboard.set_execution_schedule(daily_worker_schedule)

        worker_result = self._executor_agent.execute(state, daily_worker_schedule)

        # Le marché reste dynamique : achats indispensables en début de
        # journée, ventes/ajustements à la fin de journée, calculés sur l'état
        # réellement obtenu. Cela évite de figer une vente avant de connaître
        # les récoltes effectivement réalisées.
        market_result = self._execute_daily_market(state, economy_proposals, turn)

        result = self._merge_execution_results(worker_result, market_result)
        blackboard.set_execution_result(result)
        self._task_calendar.record_execution(result, state)
        self._loggers.get("executor").info(
            "Journée opérationnelle exécutée", turn=turn,
            status=result.status.value,
            daily_plan_day=self._daily_plan.day,
            worker_actions=sum(1 for a in result.turn_actions.get("hands", []) + [result.turn_actions.get("farmer", ["PASS"])] if a and a[0] != "PASS"),
            market_orders=len(result.turn_actions.get("market", [])),
        )

        return result.turn_actions

    def _build_daily_worker_schedule(self, state, daily_plan: DailyPlan) -> ExecutionSchedule:
        """Convert current-hour worker slots into a conflict-free executable schedule.

        IMPORTANT: multiple planner proposals can legitimately refer to the same
        board cell (for example HARVEST + WATER). Kaggriculture accepts only one
        action per worker per turn and a harvested/digged target may disappear
        immediately. Sending both actions in the same turn therefore creates a
        deterministic INVALID_TARGET race. Keep at most one state-changing task
        per target and prefer the action with the highest operational priority.
        """
        hour = int(state.time.hour)
        candidates = [t for t in daily_plan.tasks if t.planned_hour == hour]

        # A movement may share a destination with a productive action without
        # invalidating the board cell, so only non-movement tasks participate in
        # target arbitration.
        movement = {"EAST", "WEST", "NORTH", "SOUTH"}
        priority = {
            "FEED": 0, "WATER": 0, "HARVEST": 1, "CARE": 2,
            "DIG": 2, "DUG": 2, "FERTILIZE": 3, "PLANT": 4,
            "COLLECT_FERTILIZER": 4, "BUILD_COOP": 5, "BUILD_PASTURE": 5,
            "PICKUP": 5, "PLACE": 5, "DROP": 5,
        }
        selected = []
        occupied_targets = set()
        # Stable order: urgent state-preserving actions first, then economic
        # priority, then worker/task id for deterministic replay.
        candidates = sorted(
            candidates,
            key=lambda t: (
                0 if t.action in movement else 1,
                priority.get(t.action, 9),
                -float(t.priority),
                t.worker_id, t.task_id,
            ),
        )
        for task in candidates:
            if task.action not in movement and task.target is not None:
                target = tuple(task.target)
                if target in occupied_targets:
                    continue
                occupied_targets.add(target)
            selected.append(task)

        steps = []
        for idx, task in enumerate(selected):
            steps.append(ExecutionStep(
                execution_id=f"daily:{daily_plan.day}:{state.time.step}:{idx}",
                plan_step_id=task.task_id, action=task.action, source_agent=task.source_agent,
                target=task.target, product=task.product, phase=0,
                estimated_turn=int(state.time.step), worker_id=task.worker_id,
                dependencies=(), quantity=1.0, reason=task.reason,
            ))
        return ExecutionSchedule(
            steps=tuple(steps), total_steps=len(steps), estimated_turns=1,
            status=ScheduleStatus.READY,
            explanation=daily_plan.explanation, blocked=(),
        )

    def _execute_daily_market(self, state, economy_proposals, turn: int):
        """Execute only market actions appropriate to the current daily window."""
        if self._daily_plan is None:
            return self._executor_agent.execute(state, ExecutionSchedule(status=ScheduleStatus.READY))

        hour = int(state.time.hour)
        turns = int(state.time.turns_per_day)
        start_of_day = hour == 0
        end_window = hour >= int(self._daily_plan.market_window_start)

        if not start_of_day and not end_window:
            return self._executor_agent.execute(state, ExecutionSchedule(status=ScheduleStatus.READY))

        if start_of_day:
            allowed = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}
        else:
            allowed = {"SELL"}

        selected = []
        seen = set()
        for ep in sorted(economy_proposals, key=lambda x: (-float(getattr(x, "economic_score", 0.0)), -float(getattr(x, "urgency", 0.0)), str(getattr(x, "product", "")))):
            action = str(getattr(ep, "action", ""))
            product = getattr(ep, "product", None)
            if action not in allowed or action == "HOLD":
                continue
            key = (action, product)
            if key in seen:
                continue
            seen.add(key)
            selected.append(ep)
            if len(selected) >= 10:
                break

        steps = tuple(ExecutionStep(
            execution_id=f"market:{state.time.day}:{state.time.step}:{i}",
            plan_step_id=f"market:{state.time.day}:{state.time.step}:{i}:{ep.action}:{ep.product}",
            action=ep.action, source_agent="market", target=None, product=ep.product,
            phase=0, estimated_turn=int(state.time.step), worker_id=None, dependencies=(),
            quantity=float(getattr(ep, "quantity", 1.0) or 1.0), reason=str(getattr(ep, "reason", "marché dynamique")),
        ) for i, ep in enumerate(selected))
        schedule = ExecutionSchedule(
            steps=steps, total_steps=len(steps), estimated_turns=1,
            status=ScheduleStatus.READY,
            explanation=("Marché début de journée : approvisionnement/recrutement." if start_of_day else "Marché fin de journée : ventes calculées sur l'état réellement accompli."),
            blocked=(),
        )
        return self._executor_agent.execute(state, schedule)

    @staticmethod
    def _merge_execution_results(worker_result, market_result):
        from kaggriculture_agents.executor.models import ExecutionResult, ExecutionStatus
        actions = {
            "farmer": worker_result.turn_actions.get("farmer", ["PASS"]),
            "hands": worker_result.turn_actions.get("hands", []),
            "market": market_result.turn_actions.get("market", []),
        }
        executed = tuple(getattr(worker_result, "executed_steps", ())) + tuple(getattr(market_result, "executed_steps", ()))
        failed = tuple(getattr(worker_result, "failed_steps", ())) + tuple(getattr(market_result, "failed_steps", ()))
        skipped = tuple(getattr(worker_result, "skipped_steps", ())) + tuple(getattr(market_result, "skipped_steps", ()))
        if failed and executed:
            status = ExecutionStatus.PARTIAL
        elif failed:
            status = ExecutionStatus.FAILED
        else:
            status = ExecutionStatus.COMPLETED
        return ExecutionResult(
            status=status, turn_actions=actions, executed_steps=executed,
            failed_steps=failed, skipped_steps=skipped,
            actions_sent=len(executed) + len(failed), actions_succeeded=len(executed),
            actions_failed=len(failed),
            explanation=f"DailyPlan: workers fixes + marché dynamique; {len(executed)} action(s) exécutée(s).",
        )

    def calendar_snapshot(self, state):
        """Expose le calendrier pour audit/tests sans donner aux autres agents un accès mutable."""
        return self._task_calendar.forecast(state)

    def logs(self) -> list:
        """Toutes les entrées de log accumulées depuis la création de l'orchestrateur (traçabilité, spec section 24, mémoire)."""
        return self._loggers.all_entries()


def _validate_turn_actions(actions: dict, state) -> dict:
    """Defensive protocol validation before returning to Kaggriculture."""
    if not isinstance(actions, dict):
        return dict(DEFAULT_TURN_ACTIONS)
    farmer = actions.get("farmer", ["PASS"])
    hands = actions.get("hands", [])
    market = actions.get("market", [])
    # Les actions worker portent parfois des arguments : PLANT <crop>,
    # PLACE <item> [n], etc. Le protocole n'exige qu'une seule OP, pas une
    # liste de longueur 1.
    if not isinstance(farmer, list) or len(farmer) < 1:
        farmer = ["PASS"]
    if not isinstance(hands, list) or len(hands) != len(state.workers.hands):
        hands = [["PASS"] for _ in state.workers.hands]
    if not isinstance(market, list):
        market = []
    # Kaggriculture accepts at most 10 market orders per turn.
    market = market[:10]

    valid_market = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}
    valid_worker = {
        "PASS", "NORTH", "SOUTH", "EAST", "WEST",
        "DIG", "PLANT", "WATER", "HARVEST", "FERTILIZE",
        "BUILD_COOP", "BUILD_PASTURE", "FEED",
        "COLLECT_FERTILIZER", "CARE", "DROP", "PICKUP", "PLACE",
    }

    def valid_worker_action(a):
        return isinstance(a, list) and len(a) >= 1 and a[0] in valid_worker

    if not valid_worker_action(farmer):
        farmer = ["PASS"]
    fixed_hands = []
    for a in hands:
        fixed_hands.append(a if valid_worker_action(a) else ["PASS"])

    fixed_market = []
    for order in market:
        if isinstance(order, list) and order and order[0] in valid_market:
            fixed_market.append(order)
    return {"farmer": farmer, "hands": fixed_hands, "market": fixed_market}

# --------------------------------------------------------------------------- #
# Contrat Kaggriculture : agent(obs) -> dict
# --------------------------------------------------------------------------- #
_orchestrator: Optional[KaggricultureOrchestrator] = None


def configure_trace(path: Optional[str]) -> None:
    """Enable/disable forensic JSONL tracing before a run."""
    global _orchestrator
    _orchestrator = KaggricultureOrchestrator(trace_path=path)


def _get_orchestrator() -> KaggricultureOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = KaggricultureOrchestrator()
    return _orchestrator


def agent(obs: dict) -> dict:
    """Point d'entrée exact attendu par Kaggriculture (spec section 8) : `def agent(obs) -> dict`."""
    return _get_orchestrator().run(obs)


