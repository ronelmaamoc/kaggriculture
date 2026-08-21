# Stratégie Kaggriculture V5.8.3 — Planification journalière opérationnelle

## Principe

La décision n'est plus reconstruite comme une nouvelle mission indépendante à chaque heure.
Au premier tour d'une journée, les agents Perception → Crop → Animal → Market → Investment → Economy → Planner → Critic construisent le portefeuille du jour.
Le Coordinator construit alors un **DailyPlan** persistant pour les workers.

### Ordre journalier

1. **Matin : déplacement planifié** vers les zones de travail.
2. **Entretien + travaux fixes :** WATER, FEED, CARE, FERTILIZE, COLLECT_FERTILIZER, DUG, PLANT et opérations de cycle animal (BUILD/PICKUP/PLACE quand elles sont dans le plan).
3. **Récolte :** HARVEST cultures et animaux prêts.
4. **Fin de journée : marché dynamique**, calculé sur l'état réellement obtenu : ventes et ajustements de marché.

Un worker ne reçoit qu'une action par tour. Les déplacements sont donc des créneaux explicites du DailyPlan et ne sont plus un coût caché découvert par l'Executor.

## Affectation

- Les tâches sont regroupées par proximité et priorité.
- Les dépendances entre tâches worker sont conservées sur le même worker quand c'est possible.
- La charge inclut **travail + distance estimée**.
- Le système estime le nombre de workers nécessaires pour la journée, avec un plafond opérationnel de 5 (farmer + 4 hands).
- Un recrutement recommandé est mémorisé au début de journée ; les nouveaux workers sont intégrés à la planification au prochain état observé.

## Marché

- Début de journée : achats/recrutements nécessaires au programme fixe.
- Pendant la journée : pas de vente opportuniste qui détournerait le plan fixe.
- Fin de journée : les SELL sont recalculés à partir du stock et du prix observés **après les travaux du jour**.

## Mémoire inter-journée

Le lendemain est construit à partir de l'état réellement observé : récoltes effectuées, cultures restantes, eau, animaux nourris/soignés, stocks et argent. Une prédiction de la veille n'est pas considérée comme un fait.

## Animaux

AnimalAgent est inclus dans le portefeuille journalier au même titre que CropAgent. FEED/CARE/COLLECT_FERTILIZER/HARVEST et les étapes de cycle animal compatibles avec le plan sont affectées à des workers précis et placées dans la séquence quotidienne.
