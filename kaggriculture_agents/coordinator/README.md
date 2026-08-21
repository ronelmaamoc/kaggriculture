# CoordinatorAgent

## Rôle

Transforme un `Plan` déjà **approuvé** par `CriticAgent` en un
`ExecutionSchedule` : une séquence d'exécution concrète, affectée à des
workers réels et datée en tours de jeu.

```
FarmState, Plan, Critique --> CoordinatorAgent.coordinate(...) --> ExecutionSchedule
```

Il ne construit **aucune** stratégie, ne critique rien, et n'exécute
**aucune** action Kaggriculture. Ce sera le rôle du futur `ExecutorAgent`.

## Position dans l'architecture

```
PlannerAgent  -->  Plan  -->  CriticAgent  -->  Critique
                                                    │
                    FarmState ──────────────────────┤
                                                    ▼
                                          CoordinatorAgent
                                                    │
                                                    ▼
                                          ExecutionSchedule
                                                    │
                                                    ▼
                                    (futur ExecutorAgent, hors scope)
```

## Ce que le Coordinator NE recalcule PAS (et pourquoi)

Contrairement à une implémentation naïve, ce module ne reconstruit **pas**
de graphe de dépendances complet ni d'ordonnancement par phase depuis
zéro : `PlanStep.phase` et `PlanStep.depends_on` sont déjà le résultat
validé de `PlannerAgent` (ordre topologique + capacité workers par phase,
voir `kaggriculture_agents/planner/agent.py._find_phase`), et `CriticAgent` a déjà
revérifié cet ordre, les ressources, le budget et le temps avant
d'approuver. Recalculer ces éléments dupliquerait une logique déjà validée
et risquerait de **contredire** un plan approuvé.

Le rôle réel du Coordinator se limite donc à ce qui n'a **pas encore** été
décidé en amont :

| Déjà décidé par Planner/Critic | Décidé ici par le Coordinator |
|---|---|
| Quelles actions retenir | — |
| Ordre / dépendances / phases | — (vérifié défensivement, jamais recalculé) |
| Capacité workers par phase | — (vérifiée défensivement) |
| **Quel worker précis** (`farmer` vs `hand_0`...) | ✅ `worker_allocator.py` |
| **Quel tour de jeu** (`estimated_turn`) | ✅ `resource_scheduler.py` |
| Statut final d'exécutabilité (READY/PARTIAL/BLOCKED) | ✅ `validators.py` |

Toutes les vérifications de dépendances/conflits faites ici (modules
`dependency_graph.py`, `conflict_resolver.py`) sont donc volontairement
**défensives** ("defense in depth") : elles ne devraient jamais rien
trouver sur un plan `APPROVED`, mais si une incohérence existe malgré tout
entre agents, le Coordinator la détecte et écarte le step concerné
(`ExecutionSchedule.blocked`) plutôt que de produire un schedule
silencieusement incorrect — ou de tenter de "réparer" le plan.

## Découplage (duck-typing strict)

Comme le reste du projet (voir `kaggriculture_agents/critic/agent.py`), ce module
**n'importe jamais** les modèles publics d'un autre agent (`FarmState`,
`Plan`, `PlanStep`, `Critique`, `CritiqueStatus`). Il accède à leurs
attributs en duck-typing et compare `critique.status` à une **valeur**
locale (`constants.APPROVED_STATUS_VALUE`), jamais à l'énumération
elle-même.

## Entrée

- `state` : `FarmState` (utilisé uniquement pour `state.workers.all_workers`
  et `state.time.step`).
- `plan` : `Plan` (`plan.steps`, chaque `PlanStep` avec `step_id`, `action`,
  `source_agent`, `target`, `product`, `phase`, `depends_on`, `reason`).
- `critique` : `Critique` (`critique.status`).

## Sortie

```python
ExecutionSchedule(
    steps=(ExecutionStep(...), ...),
    total_steps=3,
    estimated_turns=2,
    status=ScheduleStatus.READY,
    explanation="3 action(s) programmée(s) sur 2 phase(s).",
    blocked=(),
)
```

`ScheduleStatus` :
- `READY` : tout le plan a pu être programmé (ou le plan était vide).
- `PARTIAL` : une partie a pu être programmée, le reste est dans `blocked`.
- `BLOCKED` : rien n'a pu être programmé (plan non approuvé, ou tout bloqué).

## Allocation des workers

Heuristique gloutonne déterministe (`worker_allocator.py`), phase par
phase : pour chaque step nécessitant un worker (trié par `step_id`), on
choisit parmi les workers encore libres CETTE phase celui qui minimise la
distance de Manhattan à la cible (égalité départagée par `worker_id`). Ce
n'est **pas** un algorithme d'affectation optimal global (type Hongrois) :
heuristique v1 documentée, cohérente avec les heuristiques déjà utilisées
ailleurs dans le projet (`kaggriculture_agents/crops/scoring.py`, sélection gloutonne du
`PlannerAgent`).

## Datation temporelle

1 phase = 1 tour de jeu (`constants.TURNS_PER_PHASE = 1`), à partir du tour
courant (`state.time.step`). Simplification documentée et assumée,
cohérente avec la façon dont `EconomyAgent` construit ses dépendances
(une vente dépend d'une récolte antérieure ou du même tour de
planification, jamais "plus tard dans le même tour").

## Ce que le CoordinatorAgent NE fait PAS

- Il ne construit aucune stratégie ni ne remplace le `PlannerAgent`.
- Il ne réévalue pas économiquement le plan, ni ne le critique à nouveau.
- Il ne modifie jamais `FarmState`, `Plan` ni `Critique` (lecture seule).
- Il n'exécute **aucune** action Kaggriculture, n'appelle jamais
  `env.step()`, ne déplace physiquement aucun worker.
- Il ne "répare" jamais un plan incohérent : il l'écarte et explique
  pourquoi (`ExecutionSchedule.blocked`).
- Il n'introduit aucun hasard (`random`) : à `state`/`plan`/`critique`
  identiques, le résultat est strictement identique.

## Exemple d'utilisation

```python
from kaggriculture_agents.perception.agent import PerceptionAgent
from kaggriculture_agents.crops.agent import CropAgent
from kaggriculture_agents.animals.agent import AnimalAgent
from kaggriculture_agents.market.agent import MarketAgent
from kaggriculture_agents.economy.agent import EconomyAgent
from kaggriculture_agents.planner.agent import PlannerAgent
from kaggriculture_agents.critic.agent import CriticAgent
from kaggriculture_agents.coordinator.agent import CoordinatorAgent

perception, coordinator = PerceptionAgent(), CoordinatorAgent()
crop_agent, animal_agent, market_agent = CropAgent(), AnimalAgent(), MarketAgent()
economy_agent, planner_agent, critic_agent = EconomyAgent(), PlannerAgent(), CriticAgent()

def agent(obs):
    state = perception.analyze(obs)

    economy_proposals = economy_agent.decide(
        state,
        crop_agent.decide(state),
        animal_agent.decide(state),
        market_agent.decide(state),
    )
    plan = planner_agent.plan(state, economy_proposals)
    critique = critic_agent.evaluate(state, plan)
    schedule = coordinator.coordinate(state, plan, critique)

    # Le futur ExecutorAgent transformera schedule.steps en actions
    # Kaggriculture. Pour l'instant, la stratégie officielle de soumission
    # reste inchangée tant qu'il n'existe pas.
    return {"farmer": ["PASS"], "hands": [], "market": []}
```

## Limites actuelles

- Allocation des workers gloutonne, pas optimale globalement (voir
  ci-dessus).
- 1 phase = 1 tour : ne modélise pas d'actions dont l'exécution réelle
  prendrait plusieurs tours (aucune donnée `FarmState` actuelle ne le
  justifie).
- Aucune notion de ré-planification dynamique si l'observation change
  entre la construction du plan et son exécution : ce sera le rôle d'une
  future boucle de contrôle au niveau de `main.py` (hors scope de cet
  agent).
