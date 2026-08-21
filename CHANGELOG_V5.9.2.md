# V5.9.2

## Corrections

- Le Planner accepte désormais une ressource absente de l'état courant lorsqu'elle est explicitement produite/achetée par une autre proposition du même portefeuille ; le ResourceLedger tranche ensuite selon l'ordre réel. Cela supprime les faux rejets de chaînes comme `COLLECT_FERTILIZER -> FERTILIZE` et `BUY_SEED -> PLANT`.
- `HOLD` n'est plus émis par MarketAgent : conserver un stock est l'absence de `SELL`, pas une action Kaggriculture à planifier.
- Les signaux `PRODUCE` sont filtrés dès EconomyAgent lorsqu'un `PLANT` concret du CropAgent couvre déjà le même produit.
- Les corrections V5.9.1 sur les races de cibles et la replanification restent inchangées.

## Objectif

Réduire les rejets Planner sans dégrader la stratégie productive validée par le benchmark V5.9.1.


## V5.9.4
- Fixed static feasibility for PICKUP -> PLACE resource chaining.
- Restored V5.9.2 animal proposal path; V5.9.3 gating was too destructive to the crop/economy portfolio.
- Added a 10-day minimum remaining-horizon gate for BUY_LAND.
