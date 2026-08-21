"""
core/state.py — Contrat d'état partagé de la ferme.

INSPECTION PRÉALABLE (voir rapport de fin de fichier) : `FarmState` existe
déjà, complet et déjà consommé par TOUS les agents
(`kaggriculture_agents/perception/models.py`). Créer un second `FarmState` ici
dupliquerait exactement ce que la spec interdit ("ne pas créer un deuxième
système de modèles qui ferait doublon"). Ce module se contente donc de :

    1. réexporter `FarmState` (et les sous-modèles utiles) depuis
       `kaggriculture_agents.perception.models`, pour que `core` et `main.py` aient un
       point d'import stable et explicite (`from core.state import
       FarmState`) sans que le reste du projet ait besoin de connaître le
       chemin interne `kaggriculture_agents.perception.models` ;
    2. fournir un petit utilitaire de lecture (`summarize`) pour le
       logging/traçabilité (spec section 3, "Le FarmState doit être
       considéré comme une snapshot immutable ou contrôlée"), sans
       réimplémenter ni recopier les champs eux-mêmes.

Aucun agent de ce projet ne modifie `FarmState` in place (vérifié : tous
produisent des `*Proposal`, jamais une mutation de `state`). Ce module ne
fait donc appliquer aucun verrou d'immutabilité supplémentaire — `FarmState`
n'est pas un `@dataclass(frozen=True)` dans `kaggriculture_agents/perception/models.py`
(un choix déjà fait en amont, hors du périmètre de cette tâche) ; la
discipline "lecture seule" reste une convention respectée par construction
dans tout le pipeline existant, documentée ici plutôt que réimposée par un
second type de données.
"""

from kaggriculture_agents.perception.models import (  # noqa: F401 — réexport intentionnel
    Animal,
    AnimalState,
    Crop,
    CropState,
    FarmState,
    LandState,
    MarketState,
    OpponentState,
    PlayerState,
    Position,
    ResourceState,
    RiskState,
    TimeState,
    TownState,
    Worker,
    WorkerState,
)


def summarize(state: FarmState) -> dict:
    """
    Résumé compact d'un `FarmState`, pour le logging/traçabilité (spec
    section 3, utile pour le mémoire — voir `utils/logging.py`). Ne
    recalcule rien : lit uniquement des champs déjà produits par
    `PerceptionAgent`.
    """
    return {
        "step": state.time.step,
        "day": state.time.day,
        "hour": state.time.hour,
        "money": state.resources.money,
        "num_crops": len(state.crops.crops),
        "num_animals": len(state.animals.animals),
        "num_workers": len(state.workers.all_workers),
        "crops_at_risk": len(state.risks.crops_at_risk),
        "animals_at_risk": len(state.risks.animals_at_risk),
    }
