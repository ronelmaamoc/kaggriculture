# ExecutorAgent

## Rôle

Transforme un `ExecutionSchedule` (produit par `CoordinatorAgent`) en
actions Kaggriculture **réellement soumises**. C'est le premier agent de
toute la chaîne à avoir le droit de toucher l'environnement.

```
FarmState, ExecutionSchedule --> ExecutorAgent.execute(...) --> ExecutionResult
```

## ⚠️ Découverte importante avant implémentation (spec section 4)

La spec demandait d'inspecter comment le projet communique réellement avec
Kaggriculture avant d'écrire ce module. Résultat de cette inspection :
**il n'existe, nulle part dans ce projet, un objet "environnement"
interrogeable pas à pas.** La seule interface réelle est la fonction

```python
def agent(obs) -> dict:
    ...
    return {"farmer": [...], "hands": [[...], ...], "market": [[...], ...]}
```

appelée **une fois par tour** par le moteur Kaggriculture (voir
`kaggriculture_agents/coordinator/README.md`, exemple d'utilisation). Il n'y a donc :

- **aucun retour synchrone par action** (pas de `reward`/`turn`/`state`
  observés immédiatement après une action individuelle, contrairement à un
  environnement type Gym) ;
- **aucune granularité "une action, un appel"** : Kaggriculture ne
  connaît que le dictionnaire complet soumis pour CE tour ;
- **un seul quadrant de temps par appel** : un `ExecutionSchedule` peut
  couvrir plusieurs phases (plusieurs tours futurs), mais un seul appel à
  `execute()` ne peut agir que sur `state.time.step`, le tour courant.

Ce module est conçu **autour** de cette contrainte réelle plutôt que
d'inventer une API `env.step()` qui n'existe pas (voir
`constants.py`, section "DÉCOUVERTE IMPORTANTE", pour le détail).
Conséquences concrètes :

- `ExecutionResult.turn_actions` est le **véritable produit final** :
  c'est exactement le dictionnaire à retourner depuis `agent(obs)`.
- Les steps du schedule dont `estimated_turn != state.time.step` (tours
  futurs) sont marqués `SkippedStep(reason="FUTURE_TURN")`, pas exécutés,
  pas en erreur : puisque tout le pipeline (`Perception → ... →
  Coordinator`) est rejoué à chaque tour à partir d'une observation
  fraîche, ils seront naturellement reproposés le moment venu.
- L'`EnvironmentAdapter` par défaut (`QueueingEnvironmentAdapter`) ne
  contacte rien : il confirme seulement qu'une action est bien formée. Le
  vrai résultat côté moteur (a-t-il vraiment récolté ?) n'est observable
  qu'au prochain appel de `agent(obs)`, via la nouvelle observation — hors
  du périmètre d'un seul `execute()`.
- Un worker Kaggriculture ne peut faire **qu'une seule action par tour**
  (se déplacer OU agir, jamais les deux). Si le worker affecté n'est pas
  déjà sur `step.target`, l'ExecutorAgent envoie **un pas de déplacement**
  vers la cible au lieu de l'action prévue (`action_mapper.move_towards`) ;
  l'action prévue sera reproposée automatiquement une fois le worker
  arrivé, grâce au replanning à chaque tour.

## Position dans l'architecture

```
CoordinatorAgent  -->  ExecutionSchedule
                              │
        FarmState ────────────┤
                              ▼
                       ExecutorAgent
                              │
                              ▼
                    ExecutionResult.turn_actions
                              │
                              ▼
                 retourné par agent(obs) à Kaggriculture
```

## Entrée

- `state` : `FarmState` (`state.time.step`, `state.workers.*`,
  `state.crops.crops`, `state.animals.animals` — jamais modifié).
- `schedule` : `ExecutionSchedule` (`schedule.steps`, `schedule.status`,
  `schedule.explanation` — jamais modifié, accédé en duck-typing comme
  partout ailleurs dans le projet, voir "Découplage" ci-dessous).
- `adapter` (optionnel) : `EnvironmentAdapter` — un Fake/Mock en tests
  (spec section 39), le `QueueingEnvironmentAdapter` par défaut sinon.
- `dry_run` (défaut `False`) : simule sans appeler l'adapter.
- `force` (défaut `False`) : outrepasse la protection d'idempotence.

## Sortie

```python
ExecutionResult(
    status=ExecutionStatus.COMPLETED,
    executed_steps=(ExecutedStep(execution_id="exec:0", plan_step_id="crop:HARVEST:(1, 1):WHEAT",
                                  action=("HARVEST",), worker_id="farmer", success=True, turn=None, result=...),),
    failed_steps=(),
    skipped_steps=(SkippedStep(execution_id="exec:2", plan_step_id="...", reason="FUTURE_TURN"),),
    actions_sent=1, actions_succeeded=1, actions_failed=0,
    turn_actions={"farmer": ["HARVEST"], "hands": [], "market": []},
    explanation="1 action(s) exécutée(s), 0 échec(s), 1 étape(s) ignorée(s) (statut completed).",
)
```

`ExecutionStatus` :

| Statut | Condition |
| --- | --- |
| `COMPLETED` | tous les steps dus ce tour ont réussi (ou rien n'était dû) |
| `PARTIAL` | certains ont réussi, d'autres ont échoué de façon récupérable |
| `FAILED` | tout a échoué, ou une erreur non récupérable a stoppé le moteur |
| `BLOCKED` | `schedule.status == "blocked"` — rien n'est envoyé |

## Algorithme (par step dû ce tour, dans l'ordre de `execution_id`)

```
dépendances déjà échouées/ignorées ce tour ? --> SKIPPED (DEPENDENCY_FAILED)
worker connu et pas déjà utilisé ce tour ?   --> sinon FAILURE (WORKER_UNAVAILABLE)
cible encore valide (crop/animal présent) ?  --> sinon FAILURE (INVALID_TARGET)
mapping vers l'action Kaggriculture           --> sinon FAILURE (INVALID_ACTION / UNSUPPORTED_ACTION)
   (déplacement d'un pas si le worker n'est pas encore sur la cible)
appel à l'EnvironmentAdapter (sauf dry_run)
échec non récupérable ? --> arrêt du moteur, reste marqué SKIPPED (ENGINE_STOPPED)
```

## Fichiers

- `agent.py` — API publique, filtrage "dû ce tour", idempotence, assemblage du dict final.
- `execution_engine.py` — boucle principale, dépendances/worker/cible/mapping/adapter.
- `action_mapper.py` — traduction ExecutionStep → action Kaggriculture (+ déplacement).
- `environment_adapter.py` — `Protocol` + `QueueingEnvironmentAdapter` par défaut.
- `validators.py` — vérifications défensives (worker disponible, cible existante).
- `error_handler.py` — classification récupérable / non récupérable.
- `logger.py` — traçabilité structurée en mémoire (`ExecutionLogger.entries`).
- `constants.py` — vocabulaire d'actions, codes d'erreur, seuils.
- `models.py` — `ExecutionResult`, `ExecutedStep`, `ExecutionFailure`, `SkippedStep`, `ActionResult`.

## Découplage (duck-typing strict)

Comme `kaggriculture_agents/critic` et `kaggriculture_agents/coordinator` : ce module n'importe jamais
les modèles publics d'un autre agent (`FarmState`, `ExecutionSchedule`,
`ExecutionStep`...). Il accède à leurs attributs en duck-typing et compare
`schedule.status.value` à une valeur locale
(`constants.BLOCKED_SCHEDULE_STATUS_VALUE`), jamais à l'énumération
`ScheduleStatus` elle-même.

## Idempotence (spec section 26)

`ExecutorAgent` doit être instancié **une seule fois** et réutilisé à
chaque tour (comme tous les autres agents, voir
`kaggriculture_agents/coordinator/README.md`, exemple d'utilisation). Il retient la
signature (`frozenset` des `execution_id`) du dernier batch réellement
envoyé (hors `dry_run`) ; un second appel avec le **même** schedule ne
renvoie rien une deuxième fois, sauf `force=True`. `execution_id` n'étant
pas stable d'un tour à l'autre (un nouveau `Plan`/`Schedule` est reconstruit
à chaque tour), cette protection couvre le cas réaliste — un appel
accidentel en double sur le même schedule — pas une notion de "mémoire
inter-tours" qui n'a pas de sens ici.

## Ce que l'ExecutorAgent ne fait PAS

- Il ne prend aucune décision stratégique : il exécute ce que le
  `CoordinatorAgent` a programmé, jamais autre chose.
- Il ne modifie ni `FarmState` ni `ExecutionSchedule` (lecture seule).
- Il ne réimplémente aucune règle de jeu (coûts, faisabilité...) — déjà
  validées par les agents précédents.
- Il ne planifie pas de nouveau, ne boucle pas automatiquement vers
  `PlannerAgent`/`CoordinatorAgent`.
- Il n'exécute jamais un schedule `BLOCKED`.
- Il n'invente aucune action Kaggriculture (`constants.SIMPLE_WORKER_ACTIONS`
  est la seule source de vocabulaire).

## Limites actuelles (assumées et documentées)

- **`EXPANSION_OPPORTUNITY` n'est pas exécutable** : placer un animal
  nécessite `BUY_ANIMAL` (marché) → livraison au shed → `PICKUP` →
  `PLACE`, une chaîne multi-tour qu'aucun agent en amont ne construit
  aujourd'hui (`MarketAgent` ne propose jamais `BUY_ANIMAL`). L'action est
  rejetée proprement (`UNSUPPORTED_ACTION`), jamais simulée.
- **Quantité de vente fixée à 1** (`DEFAULT_SELL_QUANTITY`) : ni
  `PlanStep` ni `ExecutionStep` ne portent de champ `quantity` — même
  simplification déjà assumée par `kaggriculture_agents/planner/resources.py` et
  `kaggriculture_agents/critic/constants.SHED_PRESSURE_ACTIONS`.
- **Déplacement à un seul pas, sans pathfinding** : priorité à l'axe X,
  convention de repère (x croissant = EAST, y croissant = SOUTH) non
  vérifiée ailleurs dans le projet — aucun autre module n'en avait eu
  besoin avant cet agent.
- **Pas de parallélisme réel** : les steps dus ce tour sont traités
  séquentiellement en mémoire (spec section 12) ; ils sont de toute façon
  soumis ensemble dans le même dictionnaire à Kaggriculture, qui les
  traite "simultanément" de son côté.
- **`turn` dans `ActionResult` est toujours `None`** avec l'adapter par
  défaut (aucune confirmation synchrone du moteur réel, voir plus haut) ;
  seul un adapter de test (Fake/Mock) peut le renseigner.
