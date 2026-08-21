# Agent Perception / State Analyzer

## Rôle

Transforme l'observation brute `obs` fournie par Kaggriculture en un état
structuré, normalisé, exploitable par les futurs agents de décision
(`CropAgent`, `AnimalAgent`, `MarketAgent`, `EconomyAgent`, `PlannerAgent`,
`CoordinatorAgent`...).

Cet agent **n'observe et n'analyse**. Il ne décide et ne produit **aucune
action** de jeu (`PLANT`, `WATER`, `HARVEST`, `FEED`, `CARE`, `SELL`, `BUY_*`,
`HIRE`, `BUY_LAND`, ...).

```
obs (Kaggriculture) --> PerceptionAgent.analyze(obs) --> FarmState
```

## Entrée

`obs`, tel que documenté dans `README.md` / `AGENTS.md` du projet :
`player`, `step`, `day`, `hour`, `farms`, `market`, `town`, `private`.

## Sortie

Un objet `FarmState` (voir `models.py`) composé de :

| Sous-état | Contenu |
|---|---|
| `time` | tour, jour, heure, tours/jours restants |
| `player` | argent, quadrants débloqués, hires du jour |
| `resources` | argent, graines, shed, inventaires des unités |
| `crops` | liste des cultures + catégories (prêtes, à arroser, à risque) |
| `animals` | liste des animaux + catégories (à nourrir, à soigner, à risque) |
| `workers` | position du farmer et des hands |
| `land` | quadrants débloqués/verrouillés, tuiles verrouillées |
| `market` | prix, inventaire du marché |
| `town` | boutiques débloquées (avec doublons agrégés) |
| `opponent` | état PUBLIC de l'adversaire (son shed reste invisible) |
| `risks` | cultures/animaux à risque, weeds, shed proche de la capacité |

## Fonctions principales

- `parsers.py` : extraction brute depuis `obs` (aucun calcul dérivé).
- `analyzers.py` : calculs dérivés (âge, catégorisation, détection de
  risques) à partir des données extraites.
- `agent.py` : orchestration `obs -> FarmState` + validation structurelle.

## Ce que l'agent ne fait pas

- Il ne décide jamais d'une action de jeu.
- Il ne propose aucune stratégie (ça sera le rôle des agents suivants).
- Il n'invente aucune clé qui n'existe pas réellement dans `obs` : les champs
  qui dépendent de la configuration d'épisode (durée de la saison, capacité
  du shed...) sont des paramètres explicites du constructeur, avec des
  valeurs par défaut documentées, jamais des suppositions silencieuses.

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent

perception = PerceptionAgent()  # ou PerceptionAgent(episode_steps=500, ...)

def agent(obs):
    state = perception.analyze(obs)

    if state.risks.animals_at_risk:
        ...  # sera géré par le futur AnimalAgent

    return {"farmer": ["PASS"], "hands": [], "market": []}
```
