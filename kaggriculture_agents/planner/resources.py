"""
resources.py — Suivi des ressources et du budget pendant la construction
du plan, sans jamais modifier `FarmState` (spec section 42 : "Le ledger
doit être une copie logique des ressources").

Deux ledgers distincts, volontairement séparés :

    ResourceLedger  -> ressources NOMMÉES et dénombrables (graines par
                       type, WHEAT, FERTILIZER), lues depuis
                       `state.resources.seeds` / `state.resources.shed`.

    BudgetLedger    -> trésorerie, avec un revenu réalisé à l'acceptation
                       d'une vente (SELL, spec sections 19-20).

Ces deux ledgers ne se recouvrent pas : voir constants.py
(CASH_CONSUMING_ACTIONS / RESOURCE_CONSUMPTION) pour la justification
détaillée de "quelle action consomme quoi".
"""

from dataclasses import dataclass, field
from typing import Dict

from .constants import CASH_CONSUMING_ACTIONS, CASH_REALIZING_ACTIONS, RESOURCE_CONSUMPTION


class ResourceLedger:
    """
    Copie logique des ressources dénombrables de `FarmState`. `consume()`
    ne modifie jamais `state` : uniquement sa propre copie interne.
    """

    def __init__(self, state):
        self._available: Dict[str, float] = {}
        for crop_type, quantity in state.resources.seeds.items():
            self._available[f"SEED_{crop_type}"] = quantity
        self._available["WHEAT"] = state.resources.shed.get("WHEAT", 0)
        self._available["FERTILIZER"] = state.resources.shed.get("FERTILIZER", 0)
        for animal in ("GOOSE", "COW", "SHEEP"):
            self._available[f"ANIMAL_{animal}"] = state.resources.shed.get(animal, 0)
        for inv in state.resources.inventories:
            for animal in ("GOOSE", "COW", "SHEEP"):
                self._available[f"INVENTORY_{animal}"] = self.available(f"INVENTORY_{animal}") + inv.get(animal, 0)

    def _resource_key(self, ep):
        getter = RESOURCE_CONSUMPTION.get((ep.source_agent, ep.action))
        return getter(ep) if getter else None

    def available(self, resource_key: str) -> float:
        return self._available.get(resource_key, 0.0)

    def can_afford(self, ep) -> bool:
        """Vérifie les ressources physiques consommées par l'étape."""
        key = self._resource_key(ep)
        if key is None:
            return True
        return self.available(key) >= max(1.0, float(getattr(ep, "quantity", 1.0)))

    def consume(self, ep) -> None:
        quantity = max(1.0, float(getattr(ep, "quantity", 1.0)))

        # Les achats enrichissent le ledger, même quand l'ordre a été émis
        # par InvestmentAgent plutôt que Crop/AnimalAgent.
        if ep.action == "BUY_SEED" and ep.product:
            key = f"SEED_{ep.product}"
            self._available[key] = self.available(key) + quantity
            return
        if ep.action == "BUY_PRODUCT" and ep.product:
            self._available[ep.product] = self.available(ep.product) + quantity
            return
        if ep.action == "BUY_ANIMAL" and ep.product:
            self._available[f"ANIMAL_{ep.product}"] = self.available(f"ANIMAL_{ep.product}") + quantity
            return

        # Production interne : un portefeuille animal/culture peut produire
        # une ressource consommée plus tard dans LE MEME plan. C'est essentiel
        # pour animal -> fertilisant -> FERTILIZE et wheat -> FEED.
        if ep.action == "HARVEST":
            if ep.source_agent == "crop" and ep.product:
                self._available[ep.product] = self.available(ep.product) + quantity
            elif ep.source_agent == "animal" and ep.product:
                product = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(ep.product)
                if product:
                    self._available[product] = self.available(product) + quantity
            return
        if ep.action == "COLLECT_FERTILIZER":
            self._available["FERTILIZER"] = self.available("FERTILIZER") + quantity
            return

        # PICKUP transfère réellement une unité du shed vers l'inventaire
        # logique du worker.
        if ep.action == "PICKUP" and ep.product:
            shed_key = f"ANIMAL_{ep.product}"
            inv_key = f"INVENTORY_{ep.product}"
            self._available[shed_key] = self.available(shed_key) - quantity
            self._available[inv_key] = self.available(inv_key) + quantity
            return

        # PLACE consomme une unité de l'inventaire du worker.
        if ep.action == "PLACE" and ep.product:
            key = f"INVENTORY_{ep.product}"
            self._available[key] = self.available(key) - quantity
            return

        key = self._resource_key(ep)
        if key is None:
            return
        self._available[key] = self.available(key) - quantity


@dataclass
class BudgetLedger:
    """
    Trésorerie disponible pendant la construction du plan. Contrairement à
    `EconomyAgent.BudgetAnalysis`, le Planner ne réserve pas de fraction de
    la trésorerie (`RESERVE_RATIO`) : ce sont deux préoccupations
    distinctes (EconomyAgent = prudence financière globale de la ferme,
    Planner = faisabilité d'un plan donné). Documenté comme choix assumé,
    pas comme un oubli -- voir README.md.
    """
    balance: float
    spent: float = field(default=0.0, init=False)

    def can_afford(self, ep) -> bool:
        if ep.action not in CASH_CONSUMING_ACTIONS:
            return True
        return ep.cost <= self.balance

    def apply(self, ep) -> None:
        if ep.action in CASH_CONSUMING_ACTIONS:
            self.balance -= ep.cost
            self.spent += ep.cost
        if ep.action in CASH_REALIZING_ACTIONS:
            self.balance += ep.expected_revenue