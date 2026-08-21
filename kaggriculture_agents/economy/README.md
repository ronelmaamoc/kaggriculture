# EconomyAgent

## Rôle

Premier agent de **synthèse** : reçoit `FarmState` ainsi que les
propositions déjà produites par `CropAgent`, `AnimalAgent` et `MarketAgent`,
et évalue laquelle de ces opportunités est économiquement intéressante
compte tenu du budget, des ressources et du temps restant. Il ne construit
aucun plan combiné (rôle du futur `PlannerAgent`) et n'exécute rien.

```
FarmState, CropProposal[], AnimalProposal[], MarketProposal[]
    --> EconomyAgent.decide(...) --> list[EconomyProposal]
```

## Entrée

```python
economy_agent.decide(state, crop_proposals, animal_proposals, market_proposals)
```

`state` (jamais `obs`). Champs utilisés : `resources` (money, seeds, shed),
`time` (remaining_days). Les propositions spécialisées sont lues mais
**jamais modifiées** (spec section 3).

## Sortie

Une liste de `EconomyProposal`, une par proposition source, triée par
`economic_score` décroissant (puis `expected_profit`, `urgency`, `risk`,
puis `action`/`target` pour un ordre déterministe) :

```python
EconomyProposal(
    agent="economy", action="PLANT", source_agent="crop", target=(4, 5), product="MELON",
    cost=80, expected_revenue=250, expected_profit=170, roi=2.125, cash_delta=170,
    risk=0.12, urgency=0.3, resource_efficiency=2.125, economic_score=0.71,
    reason="PLANT MELON : ...", confidence=1.0, budget_constrained=False, dependencies=(),
)
```

## Analyse budgétaire

`analyze_budget(state)` calcule :

```
reserve     = money * RESERVE_RATIO      (0.20 par défaut)
safe_budget = max(0, money - reserve)
```

Le `safe_budget`, et non `money`, est utilisé comme référence pour le
risque et l'affordabilité (spec section 10-11 : une ferme ne doit pas
engager toute sa trésorerie).

## Analyse des ressources

`analyze_resources(state)` classe chaque ressource suivie
(`SEED_<TYPE>`, `WHEAT`, `FERTILIZER`) en `CRITICAL` / `LIMITED` /
`ABUNDANT` selon des seuils documentés dans `constants.py`. Une vente
(`SELL`) de `WHEAT` ou `FERTILIZER` alors que la ressource est `CRITICAL`
reçoit un plancher de risque (`CRITICAL_SELL_RISK_FLOOR`), pour éviter
d'aggraver une pénurie déjà critique (spec section 13).

## Formules

```
profit      = expected_revenue - cost
roi         = profit / cost                (None si cost <= 0, jamais de division par zéro)
cash_delta  = expected_revenue - cost      (identique à profit dans cette version, voir Limites)
risk        = clip01(cost / safe_budget)   (0 si cost <= 0 ; 1 si safe_budget <= 0 et cost > 0)

economic_score =
      W_PROFIT     * normalize(profit)
    + W_ROI         * normalize(roi or 0)
    + W_LIQUIDITY   * liquidity_score(cash_delta)
    + W_URGENCY     * urgency
    + W_RESOURCE    * normalize(resource_efficiency)
    - W_RISK        * risk

# forcé à 0.0 si l'action n'est pas jouable dans le temps restant
```

`cost` n'est jamais deviné : c'est soit une dépense réellement documentée
(coût de graine pour `PLANT`/`PRODUCE`, coût d'achat pour
`EXPANSION_OPPORTUNITY`), soit `0.0` pour les actions qui n'engagent
aucune dépense monétaire directe (`HARVEST`, `WATER`, `FERTILIZE`, `FEED`,
`CARE`, `COLLECT_FERTILIZER`, `SELL`, `HOLD`).

## Gestion du budget global et des conflits

Après évaluation individuelle, `EconomyAgent._apply_budget_conflicts`
parcourt les propositions par `economic_score` décroissant et accumule le
coût des propositions engageant une dépense réelle. Toute proposition qui
ferait dépasser le `safe_budget` une fois les meilleures déjà comptées est
marquée `budget_constrained=True` et son score est pénalisé — **elle
n'est jamais retirée de la liste** : le choix final revient au
`PlannerAgent` (spec section 31-32).

## Gestion des dépendances (anti double-comptage)

Une `MarketProposal SELL` dont le produit correspond à une récolte
proposée par `CropAgent`/`AnimalAgent` reçoit un champ `dependencies`
listant ces propositions sources (ex. `("crop:HARVEST:(4, 5)",)`). Cela
signale explicitement au futur `PlannerAgent` que le revenu de cette vente
suppose la récolte correspondante, sans que l'`EconomyAgent` ne fusionne
ou ne supprime lui-même les propositions concernées (spec section 54-55).

## Gestion du temps

`is_time_feasible(remaining_days, required_days)` : pour `PLANT`
(CropProposal) et `PRODUCE` (MarketProposal), `required_days` est le
`first_yield_day` documenté du produit ; pour `EXPANSION_OPPORTUNITY`
(AnimalProposal), celui de l'animal. Les autres actions sont considérées
immédiates (`required_days=None`). Si le temps restant est insuffisant,
`economic_score = 0.0` (spec section 35).

## Ce que l'EconomyAgent NE fait PAS

- Il n'exécute, ne plante, ne récolte, ne nourrit, ne vend, n'achète et ne
  déplace aucun travailleur.
- Il ne modifie ni `FarmState` ni les propositions reçues.
- Il n'appelle jamais directement `CropAgent`, `AnimalAgent` ou
  `MarketAgent` : il ne reçoit que leurs propositions déjà calculées.
- Il ne construit pas de plan combiné ni n'affecte les travailleurs (rôle
  du futur `PlannerAgent`/`CoordinatorAgent`).

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent
from kaggriculture_agents.crops.agent import CropAgent
from kaggriculture_agents.animals.agent import AnimalAgent
from kaggriculture_agents.market.agent import MarketAgent
from kaggriculture_agents.economy.agent import EconomyAgent

perception = PerceptionAgent()
crop_agent = CropAgent()
animal_agent = AnimalAgent()
market_agent = MarketAgent()
economy_agent = EconomyAgent()

def agent(obs):
    state = perception.analyze(obs)
    crop_proposals = crop_agent.decide(state)
    animal_proposals = animal_agent.decide(state)
    market_proposals = market_agent.decide(state)
    economy_proposals = economy_agent.decide(state, crop_proposals, animal_proposals, market_proposals)
    # Pas encore de PlannerAgent : la stratégie officielle de soumission
    # reste inchangée tant que cet agent n'existe pas.
    return {"farmer": ["PASS"], "hands": [], "market": []}
```

## Limites actuelles

- `cash_delta` est actuellement identique à `expected_profit` : aucun flux
  non monétaire différé (ex. paiement à retardement) n'est modélisé
  séparément.
- Les coûts de `PLANT`/`PRODUCE`/`EXPANSION_OPPORTUNITY` sont les coûts
  d'achat documentés du jeu, pas une simulation complète (frais annexes
  non pris en compte).
- La détection de dépendance (`dependencies`) ne relie que les ventes aux
  récoltes de même produit ; elle n'empêche pas activement un double
  comptage si le futur `PlannerAgent` combine naïvement les propositions —
  elle expose seulement l'information nécessaire pour l'éviter.
- `budget_constrained` est calculé par un parcours glouton (meilleur score
  d'abord) ; ce n'est pas une optimisation combinatoire du budget global
  (qui reviendrait à faire le travail du `PlannerAgent`).
- Aucune allocation de travailleurs, aucun ordonnancement d'actions.