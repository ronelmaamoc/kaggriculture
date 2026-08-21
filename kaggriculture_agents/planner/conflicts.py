"""
conflicts.py — Élimination des doublons inter-agents et résolution des
conflits de cible AVANT ordonnancement.

Les conflits de ressources partagées (graines, budget) et de workers sont
gérés dynamiquement pendant la construction du plan (voir resources.py et
agent.py) : ils dépendent de l'ORDRE de sélection, contrairement aux
conflits traités ici, qui sont statiques (ne dépendent que de l'ensemble
des propositions reçues).
"""

from typing import List, Sequence, Tuple

from .constants import EXCLUSIVE_TARGET_ACTIONS
from .dependencies import proposal_id
from .models import RejectedProposal


def deduplicate_proposals(proposals: Sequence) -> Tuple[List, List[RejectedProposal]]:
    """
    Élimine les propositions qui décrivent la MÊME opportunité économique
    vue par deux agents différents (spec section 10, 17-18) :

        CropAgent   : PLANT <crop_type> at (x, y)
        MarketAgent : PRODUCE <crop_type>   (pas de target : signal générique)

    PRODUCE est toujours écarté au profit de PLANT quand les deux
    coexistent pour le même produit : PLANT porte une cible concrète
    (exécutable), PRODUCE est une justification économique générique de la
    même opportunité, pas une seconde plantation (spec section 18).
    """
    plant_products = {
        ep.product for ep in proposals
        if ep.source_agent == "crop" and ep.action == "PLANT"
    }

    kept: List = []
    rejected: List[RejectedProposal] = []
    for ep in proposals:
        is_duplicate_produce = (
            ep.source_agent == "market" and ep.action == "PRODUCE" and ep.product in plant_products
        )
        if is_duplicate_produce:
            rejected.append(RejectedProposal(
                proposal_id=proposal_id(ep), action=ep.action, source_agent=ep.source_agent,
                target=ep.target, product=ep.product,
                reason=f"doublon : {ep.product} est déjà couvert par une proposition PLANT du CropAgent "
                       f"(même opportunité vue par deux agents, spec section 18)",
            ))
        else:
            kept.append(ep)
    return kept, rejected


def resolve_target_conflicts(proposals: Sequence) -> Tuple[List, List[RejectedProposal]]:
    """
    Une case ne peut porter qu'une seule culture / un seul animal à la
    fois (spec section 25-26, "target conflict") : quand plusieurs
    propositions EXCLUSIVES (voir constants.EXCLUSIVE_TARGET_ACTIONS)
    visent la même case, seule celle au `economic_score` le plus élevé est
    conservée (départage déterministe par risque croissant puis produit).
    """
    groups: dict = {}
    others: List = []
    for ep in proposals:
        if ep.action in EXCLUSIVE_TARGET_ACTIONS and ep.target is not None:
            groups.setdefault((ep.action, ep.target), []).append(ep)
        else:
            others.append(ep)

    kept: List = list(others)
    rejected: List[RejectedProposal] = []
    for (_action, _target), group in groups.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        ordered = sorted(group, key=lambda ep: (-ep.economic_score, ep.risk, str(ep.product)))
        winner, losers = ordered[0], ordered[1:]
        kept.append(winner)
        for loser in losers:
            rejected.append(RejectedProposal(
                proposal_id=proposal_id(loser), action=loser.action, source_agent=loser.source_agent,
                target=loser.target, product=loser.product,
                reason=f"conflit de cible avec {proposal_id(winner)} (score économique plus élevé : "
                       f"{winner.economic_score:.2f} contre {loser.economic_score:.2f})",
            ))
    return kept, rejected