"""
utils/logging.py — Logger structuré commun aux agents (spec section 7).

Même convention que `kaggriculture_agents/executor/logger.py::ExecutionLogger` (la seule
forme de logging déjà présente dans le projet à l'inspection, `import
logging` n'apparaît nulle part ailleurs) : entrées en mémoire (déterministe,
testable, silencieux par défaut), imprimables à la demande via `emit=True`.
Ce module généralise cette convention à N'IMPORTE QUEL agent (pas seulement
l'Executor) avec les métadonnées demandées : agent, turn, action,
execution_id, plan_id.

Ne contient AUCUNE logique métier (spec section 7, "ne doit pas modifier la
logique métier") : uniquement de l'enregistrement d'événements.
"""

from typing import Any, Dict, List

LEVEL_DEBUG = "DEBUG"
LEVEL_INFO = "INFO"
LEVEL_WARNING = "WARNING"
LEVEL_ERROR = "ERROR"


class AgentLogger:
    """
    Logger dédié à UN agent nommé (ex: `AgentLogger("planner")`), pour que
    chaque ligne s'auto-identifie sans avoir à le répéter à chaque appel :

        logger = AgentLogger("planner", emit=True)
        logger.info("Plan généré", turn=42, plan_id="plan:42")
        # -> [PLANNER] Plan généré {'turn': 42, 'plan_id': 'plan:42'}
    """

    def __init__(self, agent: str, emit: bool = False) -> None:
        self.agent = agent
        self.emit = emit
        self.entries: List[Dict[str, Any]] = []

    def _record(self, level: str, message: str, **metadata) -> Dict[str, Any]:
        entry = {"agent": self.agent, "level": level, "message": message, **metadata}
        self.entries.append(entry)
        if self.emit:
            print(f"[{self.agent.upper()}] {message} {metadata}" if metadata else f"[{self.agent.upper()}] {message}")
        return entry

    def debug(self, message: str, **metadata) -> Dict[str, Any]:
        return self._record(LEVEL_DEBUG, message, **metadata)

    def info(self, message: str, **metadata) -> Dict[str, Any]:
        return self._record(LEVEL_INFO, message, **metadata)

    def warning(self, message: str, **metadata) -> Dict[str, Any]:
        return self._record(LEVEL_WARNING, message, **metadata)

    def error(self, message: str, **metadata) -> Dict[str, Any]:
        return self._record(LEVEL_ERROR, message, **metadata)

    def entries_at(self, level: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e["level"] == level]

    def clear(self) -> None:
        self.entries.clear()


class LoggerRegistry:
    """
    Fournit un `AgentLogger` par nom d'agent, réutilisé à chaque appel
    (`get("planner")` retourne toujours la même instance) — pratique pour
    `main.py`, qui a besoin d'un logger stable par étape du pipeline sur
    toute la durée de vie de l'orchestrateur.
    """

    def __init__(self, emit: bool = False) -> None:
        self._emit = emit
        self._loggers: Dict[str, AgentLogger] = {}

    def get(self, agent: str) -> AgentLogger:
        if agent not in self._loggers:
            self._loggers[agent] = AgentLogger(agent, emit=self._emit)
        return self._loggers[agent]

    def all_entries(self) -> List[Dict[str, Any]]:
        """Toutes les entrées de tous les loggers, dans l'ordre d'enregistrement au sein de chacun (voir metadata['turn'] pour ordonner globalement si besoin)."""
        entries: List[Dict[str, Any]] = []
        for logger in self._loggers.values():
            entries.extend(logger.entries)
        return entries
