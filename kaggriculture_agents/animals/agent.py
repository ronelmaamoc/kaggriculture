"""
agent.py — AnimalAgent, point d'entrée public du module.

API publique :

    animal_agent = AnimalAgent()
    proposals = animal_agent.decide(state)   # state: FarmState -> list[AnimalProposal]

AnimalAgent lit uniquement FarmState (jamais `obs` directement) et ne
modifie jamais l'état reçu. Il ne produit et n'exécute AUCUNE action
Kaggriculture : seulement des AnimalProposal, consommées plus tard par les
agents de planification / arbitrage (EconomyAgent, PlannerAgent...).

Correction (revue d'archive) : cette classe manquait — le fichier
`agent.py` ne contenait jusqu'ici que les fonctions `find_*_tasks`, qui
appartiennent à `analyzers.py` et y ont été déplacées. `agent.py` ne
contient plus désormais que l'orchestration, exactement comme
`kaggriculture_agents/crops/agent.py`.
"""

from typing import List

from .analyzers import (
    find_care_tasks,
    find_expansion_opportunities,
    find_feed_tasks,
    find_fertilizer_tasks,
    find_harvest_tasks,
    find_animal_investment_tasks,
)
from .models import AnimalProposal


class AnimalAgent:
    """Agent spécialisé : formule des intentions de production animale."""

    def decide(self, state) -> List[AnimalProposal]:
        proposals: List[AnimalProposal] = []
        proposals += find_feed_tasks(state)
        proposals += find_harvest_tasks(state)
        proposals += find_fertilizer_tasks(state)
        proposals += find_care_tasks(state)
        proposals += find_expansion_opportunities(state)
        proposals += find_animal_investment_tasks(state)

        proposals = self._resolve_local_conflicts(proposals)
        # Shared named resources are bounded before the global Planner sees
        # them. This avoids generating N FEED/PICKUP proposals when the shed
        # only contains 1 unit, which previously produced large defensive
        # rejection counts.
        feed_cap = int(getattr(state.resources, "shed", {}).get("WHEAT", 0))
        pickup_stock = {
            animal: int(getattr(state.resources, "shed", {}).get(animal, 0))
            for animal in ("GOOSE", "COW", "SHEEP")
        }
        out = []
        for proposal in sorted(proposals, key=lambda p: (-p.urgency, -p.score, str(p.target))):
            if proposal.action == "FEED":
                if feed_cap <= 0:
                    continue
                feed_cap -= 1
            elif proposal.action == "PICKUP" and proposal.animal_type:
                if pickup_stock.get(proposal.animal_type, 0) <= 0:
                    continue
                pickup_stock[proposal.animal_type] -= 1
            out.append(proposal)
        return self._sort_proposals(out)

    @staticmethod
    def _resolve_local_conflicts(proposals: List[AnimalProposal]) -> List[AnimalProposal]:
        """
        Résolution purement LOCALE aux animaux (l'arbitrage global entre
        agents, et entre plusieurs propositions visant la même case, sera
        fait plus tard par le Coordinator).

        Aucune des 5 actions animales n'invalide une autre localement :
        - FEED reste nécessaire même si l'animal est prêt à être récolté
          (survie indépendante de la production, cf. README.md) ;
        - CARE et COLLECT_FERTILIZER n'entrent en conflit avec rien ;
        - EXPANSION_OPPORTUNITY ne vise que des cases vides (empty_structures),
          jamais une case déjà occupée par un animal.
        Cette méthode existe pour garder une structure symétrique à
        CropAgent, prête à accueillir une règle si le jeu en justifie une.
        """
        return proposals

    @staticmethod
    def _sort_proposals(proposals: List[AnimalProposal]) -> List[AnimalProposal]:
        """Tri déterministe : score décroissant, puis urgency décroissante, puis position."""
        return sorted(proposals, key=lambda p: (-p.score, -p.urgency, p.target))
