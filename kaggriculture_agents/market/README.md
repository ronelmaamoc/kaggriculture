# MarketAgent

## Rôle

Analyse le marché présent dans `FarmState` (produit par `PerceptionAgent`)
et formule des **propositions économiques locales**. Il ne décide rien de
définitif et n'exécute aucune action : c'est un agent d'intention, pas
d'exécution.

FarmState --> MarketAgent.decide(state) --> list[MarketProposal]


Il répond à : *"Que nous dit le marché actuel et quelles opportunités
économiques locales peut-on identifier ?"* — pas à *"Que devons-nous faire
avec toute la ferme ?"* (cette décision appartient aux futurs `EconomyAgent`
/ `PlannerAgent` / `CoordinatorAgent`).

## Entrée

`FarmState` (jamais `obs` directement). Champs utilisés :
`market` (prices), `resources` (shed), `time` (remaining_days),
`risks` (shed_near_capacity).

## Sortie

Une liste de `MarketProposal`, triée par `score` décroissant (puis
`urgency`, puis `action`/`product`, pour un ordre déterministe) :

```python
MarketProposal(
    agent="market", action="SELL", product="MELON", quantity=5,
    priority=0.9, urgency=0.4, expected_value=1250.0, score=0.91,
    reason="Prix actuel de MELON favorable (high)",
    confidence=1.0,
)
```

## Actions proposées

`SELL`, `HOLD`, `PRODUCE` — les trois catégories retenues pour cette
première version (spec section 20 : suffisantes, `BUY_OPPORTUNITY` n'est
pas implémenté).

## Système d'analyse : PriceAnalysis

`analyze_prices(state)` (aussi exposé via `MarketAgent.analyze_prices`)
calcule, pour chaque produit coté dans `state.market.prices` :

normalized_price = current_price / base_price


où `base_price` est le prix documenté du jeu **au repos** (marché à son
inventaire d'équilibre `I0`, voir README.md du projet, table "The Price
Function"). C'est une comparaison à une référence fixe et documentée — le
`MarketAgent` **n'invente aucun historique de prix** : `FarmState` ne
contient que les prix courants, donc cette version est une analyse
purement instantanée (spec section 10, option B).

normalized_price <= 0.85 -> price_level = LOW
normalized_price >= 1.15 -> price_level = HIGH
sinon -> price_level = NORMAL


Si un produit coté n'a pas de prix de base documenté, l'analyse reste
produite mais avec `confidence` réduite et `price_level = NORMAL` par
défaut (pas de jugement de valeur sans référence).

## Système de scoring

Trois formules distinctes (poids dans `constants.py`), toutes bornées dans
`[0, 1]` avant pondération :

score_sell = W_PRICE_SELL * price_position + W_VALUE_SELL * value_norm + W_INVENTORY_SELL * inventory_norm
score_hold = W_PRICE_HOLD * (1 - price_position) + W_INVENTORY_HOLD * inventory_norm
score_produce = W_PRICE_PRODUCE * price_position + W_VALUE_PRODUCE * value_norm + W_TIME_PRODUCE * time_score


`priority` (catégorie générale de l'action) et `urgency` (importance
temporelle) restent des informations distinctes du `score` (qualité
globale), utilisables séparément par le futur `CoordinatorAgent`.

## Gestion des priorités et de l'urgence

- `SELL` : urgence renforcée si `state.risks.shed_near_capacity` est vrai
  (stock proche de la limite) ou si `state.time.remaining_days <= 1`
  (fin de partie proche) — spec sections 29-30.
- `HOLD` : urgence toujours faible (jamais une obligation d'attendre).
- `PRODUCE` : dépend du temps restant par rapport au premier rendement
  documenté (`PRODUCTION_INFO`), pas seulement du prix.

## Ce que le MarketAgent NE fait PAS

- Il n'exécute aucune action (`SELL`, `BUY_PRODUCT`, `PLANT` ne sont
  jamais appelées directement).
- Il ne modifie jamais `state.market` ni aucune autre partie de
  `FarmState` (lecture seule).
- Il ne communique pas directement avec `CropAgent` ni `AnimalAgent` :
  les trois agents partagent uniquement `FarmState` comme source commune
  (spec section 16).
- Il ne décide pas de vendre/acheter réellement ni de la quantité
  finale : ce sera le rôle du futur `EconomyAgent`.
- Il ne raisonne pas sur le budget global ni sur l'affectation des
  travailleurs.
- Il n'invente aucun historique de prix, coût de production ou volatilité
  non présents dans `FarmState`.

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent
from kaggriculture_agents.market.agent import MarketAgent

perception = PerceptionAgent()
market_agent = MarketAgent()

def agent(obs):
    state = perception.analyze(obs)
    proposals = market_agent.decide(state)
    # Pour l'instant, aucun Planner/Coordinator/EconomyAgent : la stratégie
    # officielle de soumission reste inchangée tant que ces agents n'existent pas.
    return {"farmer": ["PASS"], "hands": [], "market": []}
```

## Limites actuelles

- `normalized_price` compare uniquement au prix de base documenté du jeu,
  pas à un historique réel (aucun historique n'est disponible dans
  `FarmState` v1).
- `expected_value` pour `PRODUCE` est une estimation optimiste (rendement
  maximum documenté), pas une simulation exacte, et ne soustrait aucun
  coût de production (coût de graine non fiable à cette échelle).
- `BUY_OPPORTUNITY` n'est pas implémenté dans cette version (spec
  section 20-21).
- Le MarketAgent n'observe ni les parcelles ni les structures d'élevage :
  une `PRODUCE_OPPORTUNITY` est une opportunité "en principe", pas une
  confirmation qu'une parcelle est disponible.
- Aucune vue multi-tours, aucune contrainte budgétaire globale : ce sera
  le rôle des agents suivants (`EconomyAgent`, `PlannerAgent`,
  `CriticAgent`, `CoordinatorAgent`).