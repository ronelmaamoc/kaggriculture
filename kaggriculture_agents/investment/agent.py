"""InvestmentAgent — amorçage et investissements multi-tour.

Responsabilité: combler les besoins que les agents de production ne peuvent
pas déduire seuls quand une ressource n'existe pas encore: graines, blé,
fertilisant, terrain, structures, animaux et workers.
"""
from typing import List
from ..crops.constants import CROP_INFO
from ..animals.constants import ANIMAL_INFO
from ..market.constants import MARKET_PRODUCT_INFO
from .models import InvestmentProposal

LAND_COSTS = (1000, 2000, 4000)
RESERVE_RATIO = 0.20

class InvestmentAgent:
    """Agent d'investissement orienté croissance.

    Les captures du leader montrent une politique « all-in capacité » au
    début : plusieurs hands sont recrutés immédiatement, puis le capital
    libéré par les premières récoltes sert à débloquer le terrain, augmenter
    la main-d'œuvre et lancer l'élevage. Les achats de graines restent sous la
    responsabilité de CropAgent ; ici on orchestre uniquement capacité,
    terrain, structures/animaux et consommables de survie.
    """

    _STARTUP_HANDS = 4          # farmer + 4 hands visibles dans le visuel J1
    _MIDGAME_HANDS = 4          # cap opérationnel aligné avec le scheduler (farmer + 4 hands)

    @staticmethod
    def _fib(n: int) -> int:
        a, b = 1, 1
        if n <= 1:
            return 1
        for _ in range(2, n):
            a, b = b, a + b
        return b

    @classmethod
    def _hire_cost(cls, hire_number: int) -> float:
        return float(cls._fib(max(1, hire_number)))

    @staticmethod
    def _first_revenue_seen(state) -> bool:
        return (
            state.time.day >= 3
            or state.resources.money > 3000.0
            or any(int(state.resources.shed.get(k, 0)) > 0 for k in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"))
        )

    def decide(self, state, crop_proposals=(), animal_proposals=(), market_proposals=()) -> List[InvestmentProposal]:
        money = float(state.resources.money)
        proposals: List[InvestmentProposal] = []
        first_revenue = self._first_revenue_seen(state)
        current_hands = len(state.workers.hands)
        hires_today = int(state.player.hires_today)

        # ------------------------------------------------------------------
        # 1. Capacité de travail : HIRE est JOURNALIER dans Kaggriculture.
        #    Les hands disparaissent en fin de journée, donc la capacité doit
        #    être reconstruite au début de chaque jour. Le pipeline reçoit
        #    l'état réel : si des hands sont déjà présents, aucun doublon.
        #
        #    J0-J2 : 4 hands (farmer + 4 hands). Dès la première rentrée,
        #    passer à 6 hands. Les coûts HIRE sont calculés avec le compteur
        #    `hires_today`, qui se réinitialise lui aussi chaque jour.
        # ------------------------------------------------------------------
        target_hands = self._MIDGAME_HANDS if first_revenue and state.time.day >= 3 else self._STARTUP_HANDS
        if current_hands < target_hands and state.time.day < 30:
            missing = target_hands - current_hands
            for offset in range(1, missing + 1):
                hire_number = hires_today + offset
                cost = self._hire_cost(hire_number)
                if money < cost:
                    break
                proposals.append(InvestmentProposal(
                    action="HIRE", product=f"HAND_{current_hands + offset}", quantity=1,
                    cost=cost, expected_profit=-cost,
                    urgency=0.99 if not first_revenue else 0.82,
                    score=0.99 if not first_revenue else 0.88,
                    reason=(
                        "capacité journalière : recruter un hand au début de la journée "
                        "pour paralléliser plantation, désherbage, arrosage et récolte"
                        if not first_revenue else
                        "réinvestissement journalier : reconstruire la capacité de travail "
                        "et maintenir jusqu'à 6 hands après la première rentrée"
                    ),
                ))
                money -= cost

        # ------------------------------------------------------------------
        # 2. Expansion foncière CALENDRIER : J5, J10, J14.
        # ------------------------------------------------------------------
        unlocked = len(state.land.unlocked_quadrants)
        thresholds = {1: 5, 2: 10, 3: 14}
        if unlocked < 4:
            required_day = thresholds.get(unlocked)
            # Do not buy expensive land when too little horizon remains to
            # recover the investment. This prevents J27/J28 capital collapse.
            expansion_horizon_ok = state.time.remaining_days >= 10
            if required_day is not None and state.time.day >= required_day and expansion_horizon_ok:
                cost = float(LAND_COSTS[min(unlocked - 1, len(LAND_COSTS) - 1)])
                reserve = max(250.0, money * 0.10)
                if money >= cost + reserve:
                    proposals.append(InvestmentProposal(
                        action="BUY_LAND", cost=cost, expected_profit=0.0, urgency=0.99, score=0.98,
                        reason=f"calendrier d'expansion : acheter le quadrant #{unlocked + 1} à J{state.time.day} (seuil J{required_day})",
                    ))
                    money -= cost

        # ------------------------------------------------------------------
        # 3. Placement d'un animal déjà acheté : filet de sécurité idempotent.
        # ------------------------------------------------------------------
        animal_has_place = any(getattr(p, "action", None) == "PLACE" for p in animal_proposals)
        if not animal_has_place:
            for animal, info in ANIMAL_INFO.items():
                if int(state.resources.shed.get(animal, 0)) <= 0:
                    continue
                for pos, kind in state.animals.empty_structures:
                    if kind != info["structure_kind"]:
                        continue
                    buy_id = f"animal:BUY_ANIMAL:None:{animal}"
                    proposals.append(InvestmentProposal(
                        action="PLACE", product=animal, target=pos, quantity=1, cost=0.0,
                        expected_profit=info["max_held"] * float(state.market.prices.get(info["product"], info["base_price"])),
                        urgency=0.99, score=0.99, dependencies=(buy_id,),
                        reason=f"installation immédiate de {animal} acheté dans le {kind} disponible",
                    ))
                    break

        # ------------------------------------------------------------------
        # 4. Blé de survie : si des animaux existent, acheter suffisamment de
        #    nourriture pour ne jamais sacrifier un cycle animal.
        # ------------------------------------------------------------------
        animals = len(state.animals.animals)
        wheat = int(state.resources.shed.get("WHEAT", 0))
        if animals and wheat < max(4, animals * 2):
            qty = max(1, min(12, animals * 2 - wheat))
            price = float(state.market.prices.get("WHEAT", 25))
            cost = qty * price
            if money >= cost:
                proposals.append(InvestmentProposal(
                    action="BUY_PRODUCT", product="WHEAT", quantity=qty, cost=cost,
                    expected_profit=-cost, urgency=1.0, score=0.99,
                    reason="sécuriser le stock quotidien de blé pour nourrir tous les animaux",
                ))
                money -= cost

        # ------------------------------------------------------------------
        # 5. Fertilisant : petit buffer uniquement quand la ferme produit.
        # ------------------------------------------------------------------
        fert = int(state.resources.shed.get("FERTILIZER", 0))
        # Si des animaux sont présents ou qu'une proposition de collecte est
        # disponible, l'achat marché n'est qu'un fallback. L'EconomyAgent
        # valorisera ensuite explicitement la boucle animal -> fertilisant ->
        # culture et pourra faire remonter l'achat uniquement si le besoin
        # dépasse la production interne.
        internal_fert_source = bool(state.animals.animals) or any(
            getattr(p, "action", None) == "COLLECT_FERTILIZER" for p in animal_proposals
        )
        if state.crops.crops and fert < 2 and not internal_fert_source:
            price = float(state.market.prices.get("FERTILIZER", 100))
            if money >= price:
                proposals.append(InvestmentProposal(
                    action="BUY_PRODUCT", product="FERTILIZER", quantity=1, cost=price,
                    expected_profit=-price, urgency=0.35, score=0.30,
                    reason="buffer de fertilisant pour soutenir les cultures à forte valeur",
                ))
                money -= price

        return sorted(proposals, key=lambda p: (-p.urgency, -p.score, p.action, str(p.product)))

