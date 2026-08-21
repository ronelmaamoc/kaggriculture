# AnimalAgent

## Rôle

Analyse les animaux et structures animales présents dans `FarmState`
(produit par `PerceptionAgent`) et formule des **propositions d'actions
animales**. Il ne décide rien de définitif et n'exécute aucune action :
c'est un agent d'intention, pas d'exécution — exactement le même contrat
que `CropAgent`.

```
FarmState --> AnimalAgent.decide(state) --> list[AnimalProposal]
```

## Entrée

`FarmState` (jamais `obs` directement). Champs utilisés :
`animals`, `market` (prices), `workers` (uniquement pour calculer une
distance informative).

## Sortie

Une liste de `AnimalProposal`, triée par `score` décroissant (puis
`urgency`, puis position, pour un ordre déterministe) :

```python
AnimalProposal(
    agent="animal", action="FEED", target=(6, 6), animal_type="GOOSE",
    priority=1.0, urgency=0.95, expected_value=350.0, score=0.91,
    reason="GOOSE non nourri aujourd'hui et à risque de s'échapper dès demain (irrécupérable)",
    confidence=1.0, estimated_distance=1.0,
)
```

## Actions proposées

`FEED`, `CARE`, `HARVEST`, `COLLECT_FERTILIZER` — 4 des actions animales
documentées dans README.md / AGENTS.md du projet.

`BUY_ANIMAL`, `BUILD_COOP`, `BUILD_PASTURE` sont **volontairement exclues**
de cette première version : décider d'investir dans de nouveaux animaux ou
structures mélange production animale et stratégie économique globale
(budget, horizon, concurrence). Cette responsabilité reviendra à un futur
`EconomyAgent` / `PlannerAgent`, qui pourra s'appuyer sur
`state.animals.empty_structures` pour repérer les opportunités.

## Système de scoring

Formule commune (poids dans `constants.py`, identiques à `CropAgent`) :

```
score = W_URGENCY * urgency + W_VALUE * value_norm + W_RISK * risk
        - W_COST * cost_norm - W_DISTANCE * distance_norm
```

Tous les termes sont normalisés dans `[0, 1]` avant pondération. `priority`
(catégorie générale de l'action) et `urgency` (importance temporelle) sont
des informations distinctes du `score` (qualité globale), utilisables
séparément par le futur `CoordinatorAgent`.

Une différence assumée par rapport à `CropAgent` : une distance de
travailleur **inconnue** (`None`, aucun travailleur sur la ferme) est traitée
comme une absence de pénalité de distance, jamais comme une distance nulle
artificielle — voir `scoring.combine_score`.

## Gestion des priorités et des risques

- `FEED` (P1 — survie) : urgence et risque maximaux si
  `consecutive_unfed >= seuil de risque` (un jour de plus = animal perdu,
  irrécupérable). La valeur en jeu inclut alors le coût d'achat de l'animal,
  pas seulement sa production en attente.
- `HARVEST` (P2 — production déjà acquise) : urgence renforcée si
  `yield_units >= max_held` (le stockage sur case est saturé : toute
  production supplémentaire tant que l'animal n'est pas récolté ne
  s'accumule pas).
- `COLLECT_FERTILIZER` (P2 — production déjà acquise) : urgence modérée et
  constante — contrairement à `HARVEST`, le fertilisant non collecté ne se
  perd pas et ne s'accumule pas non plus (README.md), donc pas d'urgence
  temporelle propre.
- `CARE` (P3 — maintenance) : jamais critique, c'est un bonus futur
  optionnel (banque +1 unité pour la prochaine production planifiée), pas
  une perte évitée.

## Ce que l'AnimalAgent NE fait PAS

- Il n'exécute aucune action (`FEED`, `CARE`, `HARVEST`,
  `COLLECT_FERTILIZER` ne sont jamais appelées directement).
- Il n'affecte aucun travailleur (`estimated_distance` est une information
  géométrique, pas une affectation Farmer/Hand).
- Il ne décide pas d'acheter des animaux ni de construire des structures
  (`EconomyAgent`, `PlannerAgent`).
- Il ne raisonne pas sur le budget global ni sur le marché
  (`EconomyAgent`, `MarketAgent`).
- Il ne modifie jamais `FarmState` (lecture seule).

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent
from kaggriculture_agents.crops.agent import CropAgent
from kaggriculture_agents.animals.agent import AnimalAgent

perception = PerceptionAgent()
crop_agent = CropAgent()
animal_agent = AnimalAgent()

def agent(obs):
    state = perception.analyze(obs)
    crop_proposals = crop_agent.decide(state)
    animal_proposals = animal_agent.decide(state)
    # Pour l'instant, aucun Planner/Coordinator : la stratégie officielle
    # de soumission reste inchangée tant que ces agents n'existent pas.
    return {"farmer": ["PASS"], "hands": [], "market": []}
```

## Limites actuelles

- `expected_value` est une heuristique locale (pas une simulation exacte du
  moteur de jeu ni une prise en compte du marché dynamique futur), au même
  titre que celle de `CropAgent`.
- `estimate_care_value` suppose que le bonus banqué sera bien versé ; en
  pratique il ne l'est que si l'animal est aussi nourri le jour de la
  prochaine production planifiée (README.md, "basic needs first").
- Aucune allocation de travailleurs, aucune contrainte budgétaire globale,
  aucune vue multi-tours : ce sera le rôle des agents suivants
  (`MarketAgent`, `EconomyAgent`, `PlannerAgent`, `CriticAgent`,
  `CoordinatorAgent`).