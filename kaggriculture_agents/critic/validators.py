"""
validators.py — Vérifications STRUCTURELLES du plan (spec sections 8-9,
24-25), indépendantes de toute simulation de ressources/budget/temps
(voir analyzers.py / conflicts.py pour ces dernières).

validate_structure() / validate_actions() / validate_targets() ne lisent
jamais `state` : elles ne portent que sur la forme du `Plan` lui-même.
validate_state_consistency() est la seule à comparer le plan à l'état
actuel de la ferme (spec section 24, ex: case verrouillée).

Toutes ces fonctions sont pures : `state` et `plan` ne sont jamais modifiés
(spec section 7 : le CriticAgent est un validateur, pas un exécuteur).
"""

from typing import Dict, List

from .constants import (
    ACTIONS_BY_SOURCE,
    CODE_DUPLICATE_STEP_ID,
    CODE_EMPTY_ACTION,
    CODE_INVALID_PHASE,
    CODE_INVALID_PRIORITY,
    CODE_MISSING_TARGET,
    CODE_TARGET_LOCKED,
    CODE_UNEXPECTED_TARGET,
    CODE_UNKNOWN_ACTION,
    CODE_UNKNOWN_SOURCE_AGENT,
    KNOWN_SOURCE_AGENTS,
    MARKET_ACTIONS,
    SEVERITY_ERROR,
    WORKER_REQUIRED_ACTIONS,
)
from .models import CriticIssue


# --------------------------------------------------------------------------- #
# Validité structurelle (spec section 8)
# --------------------------------------------------------------------------- #
def validate_structure(plan) -> List[CriticIssue]:
    issues: List[CriticIssue] = []

    seen_ids: Dict[str, List[str]] = {}
    for step in plan.steps:
        seen_ids.setdefault(step.step_id, []).append(step.step_id)

        if not step.action:
            issues.append(CriticIssue(
                code=CODE_EMPTY_ACTION, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' n'a pas d'action définie.",
                step_id=step.step_id,
            ))

        if not isinstance(step.phase, int) or step.phase < 0:
            issues.append(CriticIssue(
                code=CODE_INVALID_PHASE, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' a une phase invalide : {step.phase!r} "
                        f"(attendu : entier >= 0).",
                step_id=step.step_id, expected=">= 0", actual=step.phase,
            ))

        if not (0.0 <= step.priority <= 1.0):
            issues.append(CriticIssue(
                code=CODE_INVALID_PRIORITY, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' a une priorité hors bornes : {step.priority!r} "
                        f"(attendu : entre 0.0 et 1.0).",
                step_id=step.step_id, expected="[0.0, 1.0]", actual=step.priority,
            ))

    for step_id, occurrences in seen_ids.items():
        if len(occurrences) > 1:
            issues.append(CriticIssue(
                code=CODE_DUPLICATE_STEP_ID, severity=SEVERITY_ERROR,
                message=f"L'identifiant de step '{step_id}' apparaît {len(occurrences)} fois : "
                        f"chaque step_id doit être unique (utilisé par depends_on).",
                step_id=step_id, expected="unique", actual=len(occurrences),
            ))

    return issues


# --------------------------------------------------------------------------- #
# Actions connues (spec section 9)
# --------------------------------------------------------------------------- #
def validate_actions(plan) -> List[CriticIssue]:
    issues: List[CriticIssue] = []

    for step in plan.steps:
        if step.source_agent not in KNOWN_SOURCE_AGENTS:
            issues.append(CriticIssue(
                code=CODE_UNKNOWN_SOURCE_AGENT, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' référence un source_agent inconnu : "
                        f"'{step.source_agent}' (attendus : {sorted(KNOWN_SOURCE_AGENTS)}).",
                step_id=step.step_id, expected=sorted(KNOWN_SOURCE_AGENTS), actual=step.source_agent,
            ))
            continue

        if step.action not in ACTIONS_BY_SOURCE[step.source_agent]:
            issues.append(CriticIssue(
                code=CODE_UNKNOWN_ACTION, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' propose l'action '{step.action}', inconnue pour "
                        f"source_agent='{step.source_agent}' "
                        f"(attendues : {sorted(ACTIONS_BY_SOURCE[step.source_agent])}).",
                step_id=step.step_id,
                expected=sorted(ACTIONS_BY_SOURCE[step.source_agent]), actual=step.action,
            ))

    return issues


# --------------------------------------------------------------------------- #
# Cibles (spec section 9)
# --------------------------------------------------------------------------- #
def validate_targets(plan) -> List[CriticIssue]:
    """
    Cohérence action <-> target (spec section 9, exemple "HARVEST avec
    target=worker est potentiellement invalide") : ici, le contrat
    PlanStep n'autorise qu'une position ou None, donc la seule
    incohérence détectable structurellement est l'ABSENCE ou la PRÉSENCE
    d'un target là où l'action l'exige/l'exclut (voir
    constants.WORKER_REQUIRED_ACTIONS / constants.MARKET_ACTIONS).
    """
    issues: List[CriticIssue] = []

    for step in plan.steps:
        if step.action in WORKER_REQUIRED_ACTIONS and step.target is None:
            issues.append(CriticIssue(
                code=CODE_MISSING_TARGET, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' ({step.action}) nécessite qu'un worker soit sur "
                        f"une case, mais aucun target n'est renseigné.",
                step_id=step.step_id, expected="position (x, y)", actual=None,
            ))

        if step.action in MARKET_ACTIONS and step.target is not None:
            issues.append(CriticIssue(
                code=CODE_UNEXPECTED_TARGET, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' ({step.action}) est une action marché : elle ne "
                        f"porte jamais de position, mais target={step.target!r} est renseigné.",
                step_id=step.step_id, expected=None, actual=step.target,
            ))

    return issues


# --------------------------------------------------------------------------- #
# Cohérence avec FarmState (spec sections 24-25)
# --------------------------------------------------------------------------- #
def validate_state_consistency(state, plan) -> List[CriticIssue]:
    """
    Compare chaque target du plan à l'état actuel du terrain : une case
    verrouillée (state.land.locked_tiles) ne peut recevoir aucune action
    de worker, quelle que soit la proposition qui l'a suggérée (spec
    section 24).
    """
    issues: List[CriticIssue] = []
    locked_tiles = set(state.land.locked_tiles)

    for step in plan.steps:
        if step.target is not None and step.target in locked_tiles:
            issues.append(CriticIssue(
                code=CODE_TARGET_LOCKED, severity=SEVERITY_ERROR,
                message=f"Le step '{step.step_id}' ({step.action}) cible la case {step.target}, "
                        f"actuellement verrouillée (quadrant non débloqué).",
                step_id=step.step_id, resource="land",
                expected="case déverrouillée", actual=step.target,
            ))

    return issues