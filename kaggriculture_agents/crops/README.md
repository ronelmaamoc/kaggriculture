# CropAgent

## Rôle

Analyse les cultures présentes dans `FarmState` (produit par `PerceptionAgent`)
et formule des **propositions d'actions agricoles**. Il ne décide rien de
définitif et n'exécute aucune action : c'est un agent d'intention, pas
d'exécution.

```
FarmState --> CropAgent.decide(state) --> list[CropProposal]
```

## Entrée

`FarmState` (jamais `obs` directement). Champs utilisés :
`crops`, `resources` (seeds, shed), `market` (prices), `time` (remaining_days),
`workers` (uniquement pour calculer une distance informative).

## Sortie

Une liste de `CropProposal`, triée par `score` décroissant (puis `urgency`,
puis position, pour un ordre déterministe) :

```python
CropProposal(
    agent="crop", action="HARVEST", target=(4, 3), crop_type="MELON",
    priority=1.0, urgency=0.6, expected_value=1500.0, score=0.83,
    reason="MELON prêt à récolter (6 unités)",
    confidence=1.0, estimated_distance=3.0,
)
```

## Actions proposées

`HARVEST`, `WATER`, `PLANT`, `FERTILIZE` — les 4 actions de culture réelles
documentées dans README.md / AGENTS.md du projet.

## Système de scoring

Formule commune (poids dans `constants.py`) :

```
score = W_URGENCY * urgency + W_VALUE * value_norm + W_RISK * risk
        - W_COST * cost_norm - W_DISTANCE * distance_norm
```

Tous les termes sont normalisés dans `[0, 1]` avant pondération. `priority`
(catégorie générale de l'action) et `urgency` (importance temporelle) sont
des informations distinctes du `score` (qualité globale), utilisables
séparément par le futur `CoordinatorAgent`.

## Gestion des priorités et des risques

- `HARVEST` : urgence maximale si la culture est entrée en décroissance
  (au-delà de `max_yield_day`), modérée sinon.
- `WATER` : urgence et risque maximaux si `consecutive_unwatered >= 1`
  (un jour de plus = weed).
- `PLANT` : jamais urgent (c'est une opportunité), filtré par le temps
  restant (`remaining_days >= first_yield_day`) et les graines disponibles.
- `FERTILIZE` : proposé seulement si le fertilisant est disponible et la
  culture n'a pas déjà atteint sa fenêtre de décroissance.

## Ce que le CropAgent NE fait PAS

- Il n'exécute aucune action (`WATER`, `HARVEST`, `PLANT`, `FERTILIZE` ne
  sont jamais appelées directement).
- Il n'affecte aucun travailleur (`estimated_distance` est une information
  géométrique, pas une affectation Farmer/Hand).
- Il ne raisonne pas sur le budget global ni sur l'achat de terrain
  (`EconomyAgent`, `PlannerAgent`).
- Il ne décide pas de vendre/acheter sur le marché (`MarketAgent`).
- Il ne modifie jamais `FarmState` (lecture seule).

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent
from kaggriculture_agents.crops.agent import CropAgent

perception = PerceptionAgent()
crop_agent = CropAgent()

def agent(obs):
    state = perception.analyze(obs)
    proposals = crop_agent.decide(state)
    # Pour l'instant, aucun Planner/Coordinator : la stratégie officielle
    # de soumission reste inchangée tant que ces agents n'existent pas.
    return {"farmer": ["PASS"], "hands": [], "market": []}
```

## Limites actuelles

- `expected_value` pour `PLANT`/`FERTILIZE` est une heuristique locale (pas
  une simulation exacte du moteur de jeu ni une prise en compte du marché
  dynamique futur).
- Aucune allocation de travailleurs, aucune contrainte budgétaire globale,
  aucune vue multi-tours : ce sera le rôle des agents suivants
  (`AnimalAgent`, `MarketAgent`, `EconomyAgent`, `PlannerAgent`, `CriticAgent`,
  `CoordinatorAgent`).
