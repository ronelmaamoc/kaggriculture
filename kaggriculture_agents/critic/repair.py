"""Révision active des plans par CriticAgent."""
from dataclasses import replace
from typing import Iterable, List, Tuple
from .constants import CASH_CONSUMING_ACTIONS, CASH_REALIZING_ACTIONS, RESOURCE_CONSUMPTION, CODE_BUDGET_IMPOSSIBLE, CODE_RESOURCE_OVERUSE, CODE_TARGET_CONFLICT, CODE_TARGET_LOCKED
from .models import CriticIssue
from ..planner.models import Plan, PlanStep

def _value_key(step: PlanStep):
    return (float(step.expected_profit), float(step.priority), -float(step.estimated_cost))

def _resource_key(step):
    getter = RESOURCE_CONSUMPTION.get((step.source_agent, step.action))
    return getter(step) if getter else None

def revise_plan(state, plan: Plan, issues: Iterable[CriticIssue]) -> Tuple[Plan, Tuple[str, ...]]:
    """Répare un plan en privilégiant les actions à meilleure valeur économique."""
    issue_list=list(issues); steps=list(plan.steps); remove_ids=set(); notes=[]
    for issue in issue_list:
        if issue.code == CODE_TARGET_LOCKED and issue.step_id:
            remove_ids.add(issue.step_id); notes.append(f"suppression {issue.step_id}: cible verrouillée")
        elif issue.code == CODE_TARGET_CONFLICT and issue.actual:
            candidates=[s for s in steps if s.step_id in issue.actual]
            if candidates:
                keep=max(candidates,key=_value_key)
                for s in candidates:
                    if s.step_id != keep.step_id: remove_ids.add(s.step_id)
                notes.append(f"conflit: conservation de {keep.step_id}")
    for issue in issue_list:
        if issue.code == CODE_RESOURCE_OVERUSE and issue.resource:
            consumers=[s for s in steps if _resource_key(s)==issue.resource and s.step_id not in remove_ids]
            try: available=int(float(str(issue.expected).split('<=',1)[1]))
            except Exception: available=0
            for s in sorted(consumers,key=_value_key)[:max(0,len(consumers)-available)]:
                remove_ids.add(s.step_id); notes.append(f"ressource {issue.resource}: retrait de {s.step_id}")
    for issue in issue_list:
        if issue.code == CODE_BUDGET_IMPOSSIBLE:
            money=float(state.resources.money)
            sellers=sum(s.expected_revenue for s in steps if s.action in CASH_REALIZING_ACTIONS and s.step_id not in remove_ids)
            spenders=[s for s in steps if s.action in CASH_CONSUMING_ACTIONS and s.step_id not in remove_ids]
            total=sum(s.estimated_cost for s in spenders)
            for s in sorted(spenders,key=_value_key):
                if total <= money+sellers: break
                remove_ids.add(s.step_id); total-=s.estimated_cost; notes.append(f"budget: retrait de {s.step_id}")
    steps=[s for s in steps if s.step_id not in remove_ids]

    # Recommandation active : vendre avant les dépenses indépendantes.
    sales=[s for s in steps if s.action in CASH_REALIZING_ACTIONS and not s.depends_on]
    rest=[s for s in steps if s not in sales]
    ordered=sales+rest

    # Répartition worker : au lieu de rejeter une phase surchargée, on la décale.
    max_workers=max(1,len(state.workers.all_workers)); load={}; rebuilt=[]
    for s in sorted(ordered,key=lambda x:(x.phase,-x.priority,x.step_id)):
        phase=s.phase
        if s.worker_required:
            while load.get(phase,0)>=max_workers: phase+=1
            load[phase]=load.get(phase,0)+1
        rebuilt.append(replace(s,phase=phase))
    steps=rebuilt

    # Les dépendances supprimées ne doivent plus bloquer l'étape dépendante.
    ids={s.step_id for s in steps}
    steps=[replace(s,depends_on=tuple(d for d in s.depends_on if d in ids)) for s in steps]
    return _rebuild(plan,steps),tuple(notes)

def _rebuild(original,steps):
    return Plan(steps=tuple(steps), total_score=sum(s.priority for s in steps), total_cost=sum(s.estimated_cost for s in steps), expected_profit=sum(s.expected_profit for s in steps), confidence=(sum(s.confidence for s in steps)/len(steps) if steps else 1.0), explanation=f"Plan révisé activement par CriticAgent: {len(steps)} step(s).", rejected=original.rejected)
