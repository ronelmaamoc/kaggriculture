# V5.9.1

- Prevent same-turn target races in the dynamic worker scheduler.
- At most one state-changing worker task is emitted per board target per turn.
- Operational priority is now explicit: FEED/WATER > HARVEST > CARE/DIG > production/investment.
- HOLD proposals are removed before planner rejection accounting because HOLD is not an executable Kaggriculture action.
- Deterministic selection preserves movement while arbitrating state-changing targets.
