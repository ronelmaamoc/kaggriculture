"""
environment_adapter.py — Isole l'ExecutorAgent de l'API réelle de
Kaggriculture (spec section 28), qui se résume à UN dictionnaire d'actions
retourné une fois par tour (voir constants.py, "DÉCOUVERTE IMPORTANTE").

Il n'existe pas d'objet "environnement" interrogeable en cours de partie
dans ce projet : `execute_action` ne peut donc jamais recevoir de retour
`turn`/`reward`/`state` réellement observé — seulement confirmer que
l'action a été correctement formée et mise en file pour la soumission de
ce tour. Un adapter de test (Fake/Mock, spec section 39) peut simuler des
`ActionResult` arbitraires, exactement comme si un vrai moteur pas-à-pas
existait — c'est l'endroit prévu pour ça.
"""

from typing import Optional, Protocol, Tuple

from .models import ActionResult


class EnvironmentAdapter(Protocol):
    def execute_action(self, action: Tuple[str, ...], worker_id: Optional[str] = None) -> ActionResult:
        ...


class QueueingEnvironmentAdapter:
    """
    Adapter par défaut (le seul qui corresponde à l'API réelle du jeu,
    voir constants.py) : ne contacte rien, confirme uniquement que l'action
    est correctement formée et prête à être incluse dans le dictionnaire de
    ce tour (`ExecutionResult.turn_actions`). Le VRAI résultat (succès ou
    non côté moteur Kaggriculture) n'est connu qu'à l'observation du tour
    SUIVANT, hors du périmètre d'un seul appel à `ExecutorAgent.execute`.
    """

    def execute_action(self, action: Tuple[str, ...], worker_id: Optional[str] = None) -> ActionResult:
        if not action:
            return ActionResult(success=False, message="Action vide.", error_code="INVALID_ACTION")
        return ActionResult(
            success=True, turn=None, state=None, reward=None,
            message=f"Action {action} mise en file pour la soumission de ce tour.",
            error_code=None,
        )
