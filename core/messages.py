"""
core/messages.py — Représentation des échanges entre agents (spec
section 4).

INSPECTION PRÉALABLE : chaque agent du pipeline a déjà un contrat d'entrée/
sortie fortement typé et propre à son domaine (`CropProposal`,
`AnimalProposal`, `MarketProposal`, `EconomyProposal`, `Plan`, `Critique`,
`ExecutionSchedule`, `ExecutionResult`...). `main.py` appelle donc les
agents DIRECTEMENT avec ces types (`crop_agent.decide(state)`, etc.) —
`AgentMessage` ne remplace jamais cet appel direct et n'est jamais passé en
paramètre à un agent : ce serait réinventer un bus de messages générique là
où un appel de méthode typé suffit très bien, et casserait le typage fort
déjà en place. Son unique rôle est la TRAÇABILITÉ : envelopper chaque
résultat de transition pour le journaliser / l'inspecter (voir
`core/blackboard.py` et `utils/logging.py`), utile pour le mémoire
(reconstituer après coup la séquence exacte d'une décision).
"""

from dataclasses import dataclass
from typing import Optional

# --- Vocabulaire des transitions réellement présentes dans le pipeline ----
# (spec section 4). Un `message_type` hors de cet ensemble est accepté --
# `MESSAGE_TYPES` sert de documentation/validation légère, pas de carcan.
MESSAGE_TYPES = (
    "FARM_STATE",           # PerceptionAgent -> FarmState
    "CROP_PROPOSALS",       # CropAgent -> list[CropProposal]
    "ANIMAL_PROPOSALS",     # AnimalAgent -> list[AnimalProposal]
    "MARKET_PROPOSALS",     # MarketAgent -> list[MarketProposal]
    "ECONOMY_PROPOSALS",    # EconomyAgent -> list[EconomyProposal]
    "PLAN",                 # PlannerAgent -> Plan
    "CRITIQUE",              # CriticAgent -> Critique
    "EXECUTION_SCHEDULE",   # CoordinatorAgent -> ExecutionSchedule
    "EXECUTION_RESULT",     # ExecutorAgent -> ExecutionResult
)


@dataclass(frozen=True)
class AgentMessage:
    sender: str            # nom de l'agent émetteur, ex: "crop_agent"
    receiver: str           # nom de l'agent destinataire, ex: "economy_agent" (ou "blackboard")
    message_type: str       # voir MESSAGE_TYPES
    payload: object          # l'objet réel produit (CropProposal[], Plan, Critique...) — jamais copié/modifié
    turn: int                # state.time.step au moment de l'émission


class MessageLog:
    """
    Journal en mémoire des `AgentMessage` d'un tour (même esprit que
    `kaggriculture_agents.executor.logger.ExecutionLogger` : liste en mémoire,
    déterministe, testable — pas d'écriture disque par défaut).
    """

    def __init__(self) -> None:
        self._messages: list = []

    def record(self, sender: str, receiver: str, message_type: str, payload: object, turn: int) -> AgentMessage:
        message = AgentMessage(sender=sender, receiver=receiver, message_type=message_type, payload=payload, turn=turn)
        self._messages.append(message)
        return message

    @property
    def messages(self) -> tuple:
        return tuple(self._messages)

    def of_type(self, message_type: str) -> tuple:
        return tuple(m for m in self._messages if m.message_type == message_type)

    def last(self, message_type: Optional[str] = None) -> Optional[AgentMessage]:
        candidates = self._messages if message_type is None else [m for m in self._messages if m.message_type == message_type]
        return candidates[-1] if candidates else None

    def clear(self) -> None:
        self._messages.clear()
