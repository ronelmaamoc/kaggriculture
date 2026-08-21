# Kaggriculture Strategy v5.9.4

> Stratégie multi-agent pour Kaggriculture : perception, analyse spécialisée, synthèse économique, planification, critique, coordination et exécution.

## 1. Vue d'ensemble

Le projet transforme l'observation Kaggriculture `obs` en actions finales :

```text
obs
 │
 ▼
PerceptionAgent
 │
 ▼
FarmState
 ├──► CropAgent
 ├──► AnimalAgent
 ├──► MarketAgent
 └──► InvestmentAgent
          │
          ▼
     EconomyAgent
          │
          ▼
      PlannerAgent
          │
          ▼
       CriticAgent
          │
          ▼
    CoordinatorAgent
          │
          ▼
      DailyPlan
          │
          ▼
      ExecutorAgent
          │
          ▼
{"farmer": [...], "hands": [...], "market": [...]}
```

Le point d'entrée réel attendu par Kaggriculture est :

```python
def agent(obs) -> dict:
    ...
```

La version du dépôt est **5.9.4**.

---

# 2. Architecture multi-agent

## 2.1 PerceptionAgent

**Dossier :** `kaggriculture_agents/perception/`

### Rôle

Convertit :

```text
obs → FarmState
```

Il extrait et normalise notamment :

- temps : step, jour, heure, temps restant ;
- joueur : argent, terrain débloqué, recrutements ;
- ressources : graines, shed, inventaires ;
- cultures ;
- animaux ;
- workers et positions ;
- terrain ;
- marché ;
- ville ;
- état public de l'adversaire ;
- risques.

### Modules

```text
perception/
├── agent.py
├── analyzers.py
├── constants.py
├── models.py
└── parsers.py
```

### Règle

Le PerceptionAgent **ne décide et n'exécute aucune action**. Il ne doit pas produire directement `PLANT`, `WATER`, `HARVEST`, `FEED`, `SELL`, `BUY_*`, `HIRE`, etc.

---

## 2.2 CropAgent

**Dossier :** `kaggriculture_agents/crops/`

### Rôle

Analyse les cultures de `FarmState` et produit des `CropProposal`.

```text
FarmState
   ↓
CropAgent.decide(state)
   ↓
CropProposal[]
```

### Actions

- `PLANT`
- `WATER`
- `HARVEST`
- `FERTILIZE`

### Raisonnement

Les propositions tiennent compte notamment de :

- urgence ;
- risque ;
- valeur attendue ;
- coût ;
- temps restant ;
- disponibilité des ressources.

Une récolte proche d'une perte peut être prioritaire ; `PLANT` est une opportunité qui doit rester compatible avec l'horizon disponible.

### Ne fait pas

CropAgent ne :

- modifie pas `FarmState` ;
- n'exécute pas d'action ;
- n'affecte pas les workers ;
- ne gère pas le budget global ;
- ne décide pas des ventes ;
- ne construit pas le plan final.

---

## 2.3 AnimalAgent

**Dossier :** `kaggriculture_agents/animals/`

### Rôle

Analyse les animaux et structures animales et produit des `AnimalProposal`.

### Actions

- `FEED`
- `CARE`
- `HARVEST`
- `COLLECT_FERTILIZER`

### Priorités

- `FEED` : priorité maximale lorsque l'animal risque une perte irréversible ;
- `HARVEST` : important lorsque la production est prête ou proche de la capacité maximale ;
- `COLLECT_FERTILIZER` : récupération de la production ;
- `CARE` : maintenance, moins critique.

Les décisions globales d'achat d'animaux ou de structures appartiennent aux couches d'investissement et de planification.

---

## 2.4 MarketAgent

**Dossier :** `kaggriculture_agents/market/`

### Rôle

Analyse le marché courant et produit des `MarketProposal`.

```text
FarmState
   ↓
MarketAgent.decide(state)
   ↓
MarketProposal[]
```

### Actions

- `SELL`
- `PRODUCE`

`HOLD` n'est pas une action Kaggriculture et n'est plus émis comme action planifiable.

### Analyse des prix

La version actuelle compare le prix courant à une référence documentée :

```text
normalized_price = current_price / base_price
```

Puis :

```text
<= 0.85 → LOW
>= 1.15 → HIGH
sinon   → NORMAL
```

Le MarketAgent ne doit pas inventer un historique, une volatilité ou un prix futur absent des données.

---

## 2.5 InvestmentAgent

**Dossier :** `kaggriculture_agents/investment/`

### Rôle

Identifie les investissements nécessaires à la capacité et à la croissance.

Il produit notamment des intentions pour :

- `HIRE`
- `BUY_LAND`
- `BUY_PRODUCT`
- `PLACE`
- chaînes d'investissement liées aux animaux et aux ressources.

### Politique actuelle

L'agent prend notamment en compte :

- la capacité journalière des `hands` ;
- la phase de la partie ;
- les ressources disponibles ;
- l'expansion du terrain ;
- la capacité à rentabiliser un investissement avant la fin ;
- les besoins de survie des animaux ;
- les buffers de ressources.

L'expansion foncière possède notamment un garde-fou de temps restant afin d'éviter un investissement tardif non récupérable.

### Règle

InvestmentAgent produit des propositions. Il ne retourne jamais directement le dictionnaire d'actions Kaggriculture.

---

## 2.6 EconomyAgent

**Dossier :** `kaggriculture_agents/economy/`

### Rôle

Synthétise les propositions :

```text
CropProposal[]
AnimalProposal[]
MarketProposal[]
InvestmentProposal[]
             │
             ▼
       EconomyProposal[]
```

### Budget

La logique utilise une réserve :

```text
reserve = money × RESERVE_RATIO
safe_budget = max(0, money - reserve)
```

La totalité de la trésorerie n'est donc pas considérée comme librement dépensable.

### Ressources

Les ressources peuvent être classées :

```text
CRITICAL
LIMITED
ABUNDANT
```

Cela permet notamment de pénaliser une vente d'une ressource déjà critique.

### Score

Le score économique combine notamment :

- profit ;
- ROI ;
- liquidité ;
- urgence ;
- efficacité des ressources ;
- risque.

Les poids sont définis dans `economy/constants.py`.

### Dépendances

L'EconomyAgent peut expliciter des chaînes comme :

```text
HARVEST → SELL
```

ou :

```text
production → revenu
```

afin d'éviter le double comptage.

### Ne fait pas

Il ne construit pas le plan final, ne déplace pas les workers et n'exécute aucune action.

---

## 2.7 PlannerAgent

**Dossier :** `kaggriculture_agents/planner/`

### Rôle

Transforme les `EconomyProposal` en `Plan`.

### Étapes

Le Planner :

1. dédoublonne les propositions ;
2. résout les conflits de cibles ;
3. filtre les propositions infaisables ;
4. construit le graphe de dépendances ;
5. détecte les cycles ;
6. sélectionne les propositions prêtes ;
7. vérifie ressources, budget et workers ;
8. met à jour les ledgers ;
9. ordonne les actions ;
10. produit un `Plan`.

La sélection est principalement gloutonne selon :

```text
economic_score
→ urgency
→ risk
```

### Résultat

Les `PlanStep` portent notamment :

- action ;
- agent source ;
- cible ;
- produit ;
- phase ;
- dépendances ;
- raison.

Le Planner ne doit jamais exécuter le plan.

---

## 2.8 CriticAgent

**Dossier :** `kaggriculture_agents/critic/`

### Rôle

Contrôle le plan avant exécution.

```text
FarmState + Plan
        ↓
   CriticAgent
        ↓
     Critique
```

### Vérifications

Le Critic vérifie notamment :

1. structure ;
2. actions ;
3. cibles ;
4. cohérence avec l'état ;
5. budget ;
6. ressources ;
7. workers ;
8. dépendances ;
9. temps ;
10. stockage ;
11. conflits ;
12. cohérence économique ;
13. scénarios adversariaux.

### Statuts

```text
APPROVED
NEEDS_REVISION
REJECTED
```

### Révision active

Le Critic peut tenter de réparer un plan avant de le rejeter :

```text
Planner
  ↓
Plan
  ↓
Critic
  ├── APPROVED
  └── problème
        ↓
      repair
        ↓
  revised Plan
        ↓
      Critic
```

Le Coordinator doit privilégier le plan révisé lorsqu'il est approuvé.

---

## 2.9 CoordinatorAgent

**Dossier :** `kaggriculture_agents/coordinator/`

### Rôle

Transforme un plan approuvé en `ExecutionSchedule`.

```text
FarmState + Plan + Critique
            ↓
      CoordinatorAgent
            ↓
      ExecutionSchedule
```

### Responsabilités

Il détermine notamment :

- le worker associé à une tâche ;
- le tour prévu ;
- le statut du schedule ;
- les étapes bloquées.

### Allocation

L'allocation actuelle est gloutonne et déterministe, notamment selon la distance de Manhattan entre worker et cible.

Ce n'est pas encore une optimisation globale de type Hungarian/ILP.

### Statuts

```text
READY
PARTIAL
BLOCKED
```

### Ne fait pas

Le Coordinator ne :

- reconstruit pas la stratégie économique ;
- ne remplace pas Planner ;
- ne critique pas de nouveau le plan ;
- ne modifie pas `FarmState` ;
- n'exécute pas Kaggriculture.

---

## 2.10 ExecutorAgent

**Dossier :** `kaggriculture_agents/executor/`

### Rôle

Premier et seul maillon de la chaîne autorisé à transformer le schedule en actions réellement soumises.

```text
ExecutionSchedule
        ↓
ExecutorAgent
        ↓
ExecutionResult.turn_actions
```

### Interface Kaggriculture

Le moteur appelle :

```python
agent(obs)
```

et attend :

```python
{
    "farmer": ["PASS"],
    "hands": [["PASS"], ["PASS"]],
    "market": []
}
```

### Contraintes

Un worker ne peut faire qu'une action par tour.

Si le worker doit se déplacer, l'Executor peut produire un mouvement d'un pas. L'action métier sera reproposée lors d'une observation ultérieure.

### Tours futurs

Les étapes d'un schedule qui ne correspondent pas au tour courant sont marquées `FUTURE_TURN` et seront naturellement reproposées lorsque le pipeline sera recalculé.

### Idempotence

L'Executor mémorise les batches déjà exécutés afin d'éviter une double soumission accidentelle.

### Modes

```python
executor.execute(state, schedule)
```

ou :

```python
executor.execute(state, schedule, dry_run=True)
```

---

# 3. Pipeline réel dans `main.py`

L'ordre du pipeline est :

```text
1. Perception
2. Crop
3. Animal
4. Market
5. Investment
6. Economy
7. Planner
8. Critic
9. Coordinator
10. DailyPlan
11. Executor
12. actions finales
```

Le `Blackboard` collecte les résultats intermédiaires afin de permettre la traçabilité.

Les instances des agents sont créées une fois et réutilisées pendant l'épisode. Le blackboard est recréé à chaque observation.

---

# 4. DailyPlan et replanification

La version V5.9 utilise une planification opérationnelle dynamique.

Un plan figé peut devenir obsolète après :

- `PLANT` ;
- `HARVEST` ;
- déplacement ;
- modification des stocks ;
- changement de position d'un worker ;
- action animale.

Le système reconstruit donc un `DailyPlan` à partir de l'état réellement observé.

### Ordre journalier

```text
1. déplacement
2. entretien / travaux
   ├── WATER
   ├── FEED
   ├── CARE
   ├── FERTILIZE
   ├── COLLECT_FERTILIZER
   ├── DIG/DUG
   ├── PLANT
   └── opérations animales
3. récolte
4. marché en fin de journée
```

Les actions de marché sont également séparées :

```text
début de journée → achats/recrutements
fin de journée   → ventes
```

Les ventes sont recalculées à partir de l'état réellement obtenu après les travaux.

---

# 5. Gestion des dépendances

Le Planner doit comprendre les chaînes de ressources.

Exemples :

```text
BUY_SEED
   ↓
PLANT
```

```text
COLLECT_FERTILIZER
   ↓
FERTILIZE
```

```text
HARVEST
   ↓
SELL
```

Une ressource absente au début du tour peut donc être acceptable si une proposition précédente du même portefeuille la produit ou l'achète.

---

# 6. Structure du dépôt

```text
.
├── main.py
├── local_kaggle_test.py
├── local_kaggle_batch.py
├── analyze_trace.py
├── analyze_forensic.py
├── VERSION
├── STRATEGY_V5.8.3.md
├── CHANGELOG_V5.9.md
├── CHANGELOG_V5.9.1.md
├── CHANGELOG_V5.9.2.md
│
├── core/
│   ├── blackboard.py
│   ├── messages.py
│   └── state.py
│
├── kaggriculture_agents/
│   ├── perception/
│   ├── crops/
│   ├── animals/
│   ├── market/
│   ├── investment/
│   ├── economy/
│   ├── planner/
│   ├── critic/
│   ├── coordinator/
│   └── executor/
│
├── utils/
│   ├── geometry.py
│   ├── logging.py
│   └── trace.py
│
└── tests/
```

---

# 7. Installation locale

## Prérequis

Python **3.10+**.

Le moteur de simulation utilise :

```text
kaggle-environments
```

Les tests utilisent :

```text
pytest
```

L'archive actuelle ne fournit pas encore de `requirements.txt`.

## Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install kaggle-environments pytest
```

## Windows

```powershell
python -m venv .venv
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install kaggle-environments pytest
```

---

# 8. Exécuter localement

Le point d'entrée principal est :

```python
from main import agent
```

Le test complet du moteur est :


```bash
python local_kaggle_test.py \
  --steps 720 \
  --seed 7 \
  --opponent random
```

```bash
python local_kaggle_test.py \
  --steps 20 \
  --seed 1 \
  --opponent pass
```

Les adversaires disponibles sont :

```text
pass
random
starter
```

Le script génère notamment `replay.json`.

---

# 9. Exécuter plusieurs simulations

```bash
python local_kaggle_batch.py \
  --opponent random \
  --seeds 0 1 2 3 4
```

Ou :

```bash
python local_kaggle_batch.py \
  --opponent starter \
  --seeds 0 1 2 3 4 \
  --steps 720
```

Avec une trace :

```bash
python local_kaggle_batch.py \
  --opponent random \
  --seeds 0 \
  --steps 720 \
  --trace-file trace.jsonl
```

---



# 10. Traces et débogage

Le projet contient :

```text
analyze_trace.py
analyze_forensic.py
utils/trace.py
utils/logging.py
```

Une trace permet d'étudier une décision complète :

```text
obs
 ↓
FarmState
 ↓
Crop
 ↓
Animal
 ↓
Market
 ↓
Investment
 ↓
Economy
 ↓
Plan
 ↓
Critique
 ↓
Schedule
 ↓
Execution
 ↓
actions
```

Lorsqu'un résultat est mauvais, il faut identifier **à quel niveau** la mauvaise décision a été introduite avant de modifier `main.py`.

---

# 11. Gestion des erreurs

Le pipeline possède un mécanisme de repli.

Si la perception échoue ou si une exception survient dans le pipeline, l'orchestrateur retourne les actions neutres par défaut plutôt qu'une action potentiellement incohérente.

Cela permet de préserver le contrat :

```python
agent(obs) -> dict
```

même en cas d'erreur interne.

-