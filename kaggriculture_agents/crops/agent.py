"""
agent.py — CropAgent, point d'entrée public du module.

API publique :

    crop_agent = CropAgent()
    proposals = crop_agent.decide(state)   # state: FarmState -> list[CropProposal]

CropAgent lit uniquement FarmState (jamais `obs` directement) et ne modifie
jamais l'état reçu. Il ne produit et n'exécute AUCUNE action Kaggriculture :
seulement des CropProposal, consommées plus tard par les agents de
planification / arbitrage.
"""

from typing import List

from .analyzers import find_fertilize_tasks, find_harvest_tasks, find_plant_tasks, find_water_tasks, find_seed_purchase_tasks, find_weed_tasks
from .models import CropProposal


class CropAgent:
    """Agent spécialisé : formule des intentions de production agricole."""

    def decide(self, state) -> List[CropProposal]:
        proposals: List[CropProposal] = []
        proposals += find_harvest_tasks(state)
        proposals += find_weed_tasks(state)
        proposals += find_water_tasks(state)
        proposals += find_plant_tasks(state)
        proposals += find_fertilize_tasks(state)
        proposals += find_seed_purchase_tasks(state)

        proposals = self._resolve_local_conflicts(proposals)
        proposals = self._apply_operational_horizon(proposals, state)
        return self._sort_proposals(proposals)

    @staticmethod
    def _apply_operational_horizon(proposals: List[CropProposal], state) -> List[CropProposal]:
        """Réduit le portefeuille de candidats à ce que les workers peuvent
        réellement traiter à court terme.

        V5.8 générait une proposition pour presque chaque case libre. Le
        Planner pouvait alors construire 30--50 étapes futures, alors que le
        moteur n'exécute que quelques actions par tour. Le trace forensic a
        montré que cette sur-génération provoquait des déplacements lointains
        et beaucoup de rejets.

        Règle V5.8.2 : un seul horizon opérationnel par worker et par type
        d'action. Les tâches les plus urgentes restent prioritaires ; les
        autres seront régénérées au tour suivant. Cela ne supprime aucune
        capacité du jeu : on limite seulement les intentions simultanées.
        """
        workers = list(getattr(getattr(state, "workers", None), "all_workers", []) or [])
        n_workers = max(1, len(workers))

        # Une action productive par worker et par tour : inutile de planifier
        # plusieurs dizaines de cibles concurrentes. Les tâches urgentes
        # peuvent garder un petit buffer pour le tour suivant.
        caps = {
            "HARVEST": n_workers,
            "WATER": n_workers,
            "DUG": n_workers,
            "PLANT": n_workers,
            # FERTILIZE consumes a shared named resource. Never emit more
            # fertilizer tasks than the current physical stock.
            "FERTILIZE": min(n_workers, int(getattr(state.resources, "shed", {}).get("FERTILIZER", 0))),
        }

        def distance(p):
            d = getattr(p, "estimated_distance", None)
            return float(d) if d is not None else 9999.0

        kept = []
        grouped = {}
        for proposal in proposals:
            grouped.setdefault(proposal.action, []).append(proposal)

        for action, group in grouped.items():
            cap = caps.get(action)
            if cap is None or len(group) <= cap:
                kept.extend(group)
                continue

            # Pour WATER, le risque passe avant la distance ; pour HARVEST,
            # l'urgence puis la valeur ; pour les autres, le score local
            # reste le critère principal et la proximité départage.
            if action == "WATER":
                ordered = sorted(
                    group,
                    key=lambda p: (
                        -float(p.urgency),
                        -float(getattr(p, "score", 0.0)),
                        distance(p),
                        str(p.target),
                    ),
                )
            else:
                ordered = sorted(
                    group,
                    key=lambda p: (
                        -float(getattr(p, "score", 0.0)),
                        distance(p),
                        -float(p.urgency),
                        str(p.target),
                    ),
                )
            kept.extend(ordered[:cap])

        return kept

    @staticmethod
    def _resolve_local_conflicts(proposals: List[CropProposal]) -> List[CropProposal]:
        """
        Résolution purement LOCALE aux cultures (l'arbitrage global entre
        agents sera fait plus tard par le Coordinator) :

        - une case déjà proposée en HARVEST n'a pas besoin d'être proposée en
          FERTILIZE (la culture va être récoltée, fertiliser est inutile).
        """
        harvest_targets = {p.target for p in proposals if p.action == "HARVEST"}
        return [
            p for p in proposals
            if not (p.action == "FERTILIZE" and p.target in harvest_targets)
        ]

    @staticmethod
    def _sort_proposals(proposals: List[CropProposal]) -> List[CropProposal]:
        """Tri déterministe : score décroissant, puis urgency décroissante, puis position."""
        return sorted(proposals, key=lambda p: (-p.score, -p.urgency, p.target))
