"""
agent.py — CriticAgent, point d'entrée public du module.

API publique :

    critic = CriticAgent()
    critique = critic.evaluate(state, plan)   # -> Critique

CriticAgent lit uniquement FarmState et le Plan déjà produit par
PlannerAgent (jamais `obs` directement, jamais d'appel aux agents
précédents ni à leurs modules internes -- même convention de découplage
que tout le reste du projet, voir constants.py). Il ne modifie ni
FarmState ni Plan, et n'exécute AUCUNE action Kaggriculture : seulement
une Critique, destinée à un futur CoordinatorAgent / ExecutorAgent (hors
scope ici) ou à une boucle de révision Planner <-> Critic (également hors
scope de cette version, spec section 36).

Algorithme (spec section 35) :

    1. plan vide -> court-circuit : APPROVED, score 0.0 (spec section 28)
    2. validate_structure / validate_actions / validate_targets
    3. validate_state_consistency (cases verrouillées)
    4. analyze_budget (impossibilité absolue + dépassement ponctuel)
    5. analyze_resources (ressources nommées)
    6. analyze_workers (capacité par phase)
    7. analyze_dependencies (ordre, dépendance manquante, cycles)
    8. analyze_time (tours restants)
    9. analyze_storage (pression sur le shed)
    10. detect_target_conflicts (cible exclusive, doublons)
    11. analyze_economics (cohérence profit, double comptage)
    12. séparer issues (ERROR/CRITICAL) et warnings (INFO/WARNING)
    13. déterminer le statut (rules.py), le score et la confiance (scoring.py)
    14. produire l'explication et la Critique
"""

from typing import List

from . import analyzers, conflicts, repair, rules, scoring, validators
from .constants import SEVERITIES_BLOCKING_APPROVAL
from .models import Critique, CriticIssue, CritiqueStatus
from .adversarial import stress_test


class CriticAgent:
    """Agent de validation : vérifie qu'un Plan est cohérent, faisable et sûr avant transmission."""

    def evaluate(self, state, plan) -> Critique:
        if not plan.steps:
            return Critique(
                status=CritiqueStatus.APPROVED,
                issues=(), warnings=(),
                score=0.0, confidence=1.0,
                explanation="Plan vide : aucune action réalisable n'a été retenue par le PlannerAgent.", stress_results=(), robust_score=1.0,
            )

        all_issues: List[CriticIssue] = []
        all_issues += validators.validate_structure(plan)
        all_issues += validators.validate_actions(plan)
        all_issues += validators.validate_targets(plan)
        all_issues += validators.validate_state_consistency(state, plan)

        all_issues += analyzers.analyze_budget(state, plan)
        all_issues += analyzers.analyze_resources(state, plan)
        all_issues += analyzers.analyze_workers(state, plan)
        all_issues += analyzers.analyze_dependencies(state, plan)
        all_issues += analyzers.analyze_time(state, plan)
        all_issues += analyzers.analyze_storage(state, plan)
        all_issues += conflicts.detect_target_conflicts(plan)
        all_issues += analyzers.analyze_economics(state, plan)
        stress = stress_test(state, plan)
        worst = min((r.score for r in stress), default=float(plan.expected_profit))
        if plan.expected_profit > 0 and worst < 0:
            all_issues.append(CriticIssue(code="ADVERSARIAL_WORST_CASE", severity="WARNING",
                message=f"Le plan devient déficitaire dans un scénario stressé (worst={worst:.1f}$).", expected=0.0, actual=worst))

        issues = tuple(i for i in all_issues if i.severity in SEVERITIES_BLOCKING_APPROVAL)
        warnings = tuple(i for i in all_issues if i.severity not in SEVERITIES_BLOCKING_APPROVAL)

        status = rules.determine_status(all_issues)
        score = scoring.calculate_critique_score(all_issues)
        confidence = scoring.calculate_confidence(all_issues)

        # Révision active : le Critic tente de corriger le plan avant de le
        # déclarer non exécutable. Il ne se contente donc plus d'un rejet.
        revised_plan = plan
        revision_notes = ()
        if all_issues:
            revised_plan, revision_notes = repair.revise_plan(state, plan, all_issues)
            if revised_plan.steps != plan.steps:
                revised_issues = []
                revised_issues += validators.validate_structure(revised_plan)
                revised_issues += validators.validate_actions(revised_plan)
                revised_issues += validators.validate_targets(revised_plan)
                revised_issues += validators.validate_state_consistency(state, revised_plan)
                revised_issues += analyzers.analyze_budget(state, revised_plan)
                revised_issues += analyzers.analyze_resources(state, revised_plan)
                revised_issues += analyzers.analyze_workers(state, revised_plan)
                revised_issues += analyzers.analyze_dependencies(state, revised_plan)
                revised_issues += analyzers.analyze_time(state, revised_plan)
                revised_issues += analyzers.analyze_storage(state, revised_plan)
                revised_issues += conflicts.detect_target_conflicts(revised_plan)
                revised_issues += analyzers.analyze_economics(state, revised_plan)
                revised_status = rules.determine_status(revised_issues)
                if revised_status == CritiqueStatus.APPROVED:
                    issues = ()
                    warnings = tuple(revised_issues)
                    explanation = self._explain(CritiqueStatus.APPROVED, revised_plan, issues, warnings)
                    if revision_notes:
                        explanation += " Révision active : " + "; ".join(revision_notes) + "."
                    return Critique(
                        status=CritiqueStatus.APPROVED, issues=issues, warnings=warnings,
                        score=scoring.calculate_critique_score(revised_issues),
                        confidence=scoring.calculate_confidence(revised_issues),
                        explanation=explanation, revised_plan=revised_plan,
                        recommendations=revision_notes, stress_results=stress,
                        robust_score=max(0.0, min(1.0, 1.0 + worst / max(1.0, abs(plan.expected_profit)))),
                    )

        explanation = self._explain(status, plan, issues, warnings)
        return Critique(
            status=status, issues=issues, warnings=warnings,
            score=score, confidence=confidence, explanation=explanation,
            revised_plan=revised_plan, recommendations=revision_notes, stress_results=stress,
            robust_score=max(0.0, min(1.0, 1.0 + worst / max(1.0, abs(plan.expected_profit)))),
        )

    @staticmethod
    def _explain(status: CritiqueStatus, plan, issues, warnings) -> str:
        num_steps = len(plan.steps)
        if status == CritiqueStatus.APPROVED:
            base = f"Plan de {num_steps} step(s) approuvé."
        elif status == CritiqueStatus.NEEDS_REVISION:
            base = (
                f"Plan de {num_steps} step(s) nécessite une révision : "
                f"{len(issues)} problème(s) corrigeable(s) détecté(s)."
            )
        else:
            base = (
                f"Plan de {num_steps} step(s) rejeté : "
                f"{len(issues)} violation(s) critique(s) ou bloquante(s) détectée(s)."
            )

        details = [f"{i.code} ({i.severity})" for i in issues]
        if details:
            base += " Problèmes : " + "; ".join(details) + "."
        if warnings:
            base += f" {len(warnings)} avertissement(s) supplémentaire(s) (non bloquant(s))."
        return base