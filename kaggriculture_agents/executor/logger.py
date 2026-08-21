"""
logger.py — Traçabilité structurée de l'exécution (spec sections 24-25).

Enregistre chaque événement en mémoire (`self.entries`, une liste de dict)
plutôt que d'écrire directement sur la sortie standard : garde les tests
déterministes et silencieux par défaut, tout en restant inspectable
(`entries`) ou imprimable à la demande (`emit=True`).
"""

from typing import Any, Dict, List, Optional


class ExecutionLogger:
    def __init__(self, emit: bool = False):
        self.emit = emit
        self.entries: List[Dict[str, Any]] = []

    def _record(self, event: str, **fields) -> None:
        entry = {"event": event, **fields}
        self.entries.append(entry)
        if self.emit:
            print(entry)

    def execution_start(self, execution_batch_id: str, total_steps: int) -> None:
        self._record("EXECUTION_START", execution_batch_id=execution_batch_id, total_steps=total_steps)

    def action_start(self, execution_id: str, action, worker_id: Optional[str]) -> None:
        self._record("ACTION_START", execution_id=execution_id, action=action, worker_id=worker_id)

    def action_success(self, execution_id: str, turn: Optional[int]) -> None:
        self._record("ACTION_SUCCESS", execution_id=execution_id, turn=turn)

    def action_failure(self, execution_id: str, code: str, message: str) -> None:
        self._record("ACTION_FAILURE", execution_id=execution_id, code=code, message=message)

    def action_skipped(self, execution_id: str, reason: str) -> None:
        self._record("ACTION_SKIPPED", execution_id=execution_id, reason=reason)

    def execution_end(self, execution_batch_id: str, status: str) -> None:
        self._record("EXECUTION_END", execution_batch_id=execution_batch_id, status=status)
