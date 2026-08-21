"""
scoring.py — Calcul des grandeurs de plan (profit net, score global,
confiance). Fonctions pures : aucun accès à FarmState, aucune décision de
sélection (ça, c'est agent.py).
"""

from typing import Dict, Sequence

from .constants import (
    CONFIDENCE_PENALTY_CAP,
    CONFIDENCE_PENALTY_PER_REJECTION,
    PROFIT_NORMALIZATION_CAP,
    W_PROFIT,
    W_RISK,
    W_URGENCY,
)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return _clip01(value / cap)


def calculate_action_priority(ep) -> tuple:
    """Alias explicite de constants.selection_key, exposé ici pour le contrat scoring.py attendu (spec section 43)."""
    from .constants import selection_key
    return selection_key(ep)


def calculate_net_expected_profit(steps: Sequence, risks: Sequence[float] = ()) -> float:
    """
    Valeur nette du plan (spec section 30-31) : la somme des `expected_profit`
    de chaque step SAUF ceux qui sont référencés comme dépendance par un
    autre step retenu. Une récolte dont le produit est ensuite vendu dans le
    même plan ne doit pas compter deux fois la même valeur -- seule la
    vente (le step terminal de la chaîne) est comptée ; la récolte qui la
    rend possible est considérée comme un passage obligé, pas une valeur
    supplémentaire.

    Exemple (spec section 31) : HARVEST_MELON (profit=0 contributif) +
    SELL_MELON (revenue=500) -> valeur nette = 500, pas 1000.
    """
    referenced_as_dependency = set()
    for step in steps:
        referenced_as_dependency.update(step.depends_on)

    return sum(
        step.expected_profit for step in steps
        if step.step_id not in referenced_as_dependency
    )


def calculate_resource_pressure(initial_available: Dict[str, float], remaining_available: Dict[str, float]) -> float:
    """
    Fraction moyenne, sur toutes les ressources NOMMÉES suivies par
    resources.ResourceLedger, de ce qui a été consommé par le plan.
    0.0 = aucune ressource nommée entamée, 1.0 = toutes épuisées. Ignore
    les ressources dont la quantité initiale était nulle (rien à consommer).
    """
    ratios = []
    for key, initial in initial_available.items():
        if initial <= 0:
            continue
        remaining = remaining_available.get(key, 0.0)
        consumed = max(0.0, initial - remaining)
        ratios.append(_clip01(consumed / initial))
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)


def calculate_urgency_score(accepted_proposals: Sequence) -> float:
    """Urgence moyenne des propositions retenues (0.0 si le plan est vide : aucune urgence à combler)."""
    if not accepted_proposals:
        return 0.0
    return sum(ep.urgency for ep in accepted_proposals) / len(accepted_proposals)


def calculate_avg_risk(accepted_proposals: Sequence) -> float:
    """Risque moyen des propositions retenues (0.0 si le plan est vide : aucun risque pris)."""
    if not accepted_proposals:
        return 0.0
    return sum(ep.risk for ep in accepted_proposals) / len(accepted_proposals)


def calculate_plan_score(net_expected_profit: float, avg_urgency: float, avg_risk: float) -> float:
    """
    plan_score = W_PROFIT*profit_norm + W_URGENCY*avg_urgency - W_RISK*avg_risk

    Version v1 volontairement simple (voir constants.py : `strategic_value`
    et `idle_time` ne sont pas modélisés, faute de données fiables dans
    FarmState pour les estimer sans inventer d'hypothèses).
    """
    profit_norm = _normalize(net_expected_profit, PROFIT_NORMALIZATION_CAP)
    raw = W_PROFIT * profit_norm + W_URGENCY * _clip01(avg_urgency) - W_RISK * _clip01(avg_risk)
    return _clip01(raw)


def calculate_plan_confidence(steps: Sequence, rejected_count: int) -> float:
    """
    Confiance globale (spec section 55) : moyenne des `confidence` des
    steps retenus, légèrement pénalisée par le nombre de propositions
    écartées (données incomplètes / contraintes non satisfaites), plafonnée
    pour ne jamais s'effondrer uniquement à cause du volume de rejets.
    Un plan vide n'a rien à être incertain -- confiance neutre de 1.0.
    """
    if not steps:
        return 1.0
    base = sum(step.confidence for step in steps) / len(steps)
    penalty = min(CONFIDENCE_PENALTY_CAP, CONFIDENCE_PENALTY_PER_REJECTION * rejected_count)
    return _clip01(base - penalty)