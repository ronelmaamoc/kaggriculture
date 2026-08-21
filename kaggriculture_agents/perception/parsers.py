"""
parsers.py — Extraction des données BRUTES depuis `obs`.

Règle : un parser ne fait que lire `obs` et retourner des structures simples
(dict / list / tuples). Il ne calcule aucune information dérivée (âge, risque,
catégorisation...) : ça, c'est le rôle de `analyzers.py`.

Toutes les fonctions sont tolérantes à une observation partielle : un champ
manquant retourne une valeur sûre (dict vide, liste vide, 0) plutôt que de
lever une exception, SAUF si un champ structurellement indispensable manque
(ex: "farms" absent), auquel cas on lève une erreur explicite — voir
`agent.py` pour la politique de validation globale.

Référence de la structure réelle de `obs` : README.md / AGENTS.md du projet
Kaggriculture. À ne jamais deviner : si un doute existe sur une clé, vérifier
ces fichiers avant de l'ajouter ici.
"""

from typing import Any, Dict, List, Tuple

from .constants import ANIMAL_STRUCTURE_KINDS, TILE_KIND_WEED, TILE_LOCKED

Position = Tuple[int, int]


def _own_farm(obs: Dict[str, Any]) -> Dict[str, Any]:
    player = obs.get("player", 0)
    farms = obs.get("farms", [])
    if player < len(farms):
        return farms[player] or {}
    return {}


def _opponent_farm(obs: Dict[str, Any]) -> Dict[str, Any]:
    player = obs.get("player", 0)
    farms = obs.get("farms", [])
    opponent_index = 1 - player
    if 0 <= opponent_index < len(farms):
        return farms[opponent_index] or {}
    return {}


def parse_time(obs: Dict[str, Any]) -> Dict[str, int]:
    """Extrait les champs temporels bruts de obs."""
    return {
        "step": obs.get("step", 0),
        "day": obs.get("day", 0),
        "hour": obs.get("hour", 0),
    }


def parse_player(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait les infos publiques du joueur courant (sa propre farm)."""
    farm = _own_farm(obs)
    return {
        "player_index": obs.get("player", 0),
        "money": farm.get("money", 0.0),
        "hires_today": farm.get("hires_today", 0),
        "unlocked_quadrants": list(farm.get("unlocked_quadrants", [])),
        "board_size": len(farm.get("tiles", [])) or None,
    }


def parse_resources(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait les ressources privées (shed, graines, inventaires)."""
    private = obs.get("private", {}) or {}
    farm = _own_farm(obs)
    return {
        "money": farm.get("money", 0.0),
        "seeds": dict(private.get("seeds", {})),
        "shed": dict(private.get("shed", {})),
        "inventories": [dict(inv) for inv in private.get("inventories", [])],
    }


def parse_tiles(obs: Dict[str, Any]) -> Dict[str, List[Any]]:
    """
    Parcourt tiles[y][x] de la propre farm et classe chaque case dans l'un des
    seaux suivants, sans aucune interprétation supplémentaire :
      - plant_tiles: (position, tile_dict) pour kind == "PLANT"
      - weed_tiles: positions avec kind == "WEED"
      - structure_tiles: (position, tile_dict) pour kind in {COOP, PASTURE}
      - empty_tiles: positions avec tile is None
      - locked_tiles: positions avec tile == "LOCKED"
    """
    farm = _own_farm(obs)
    tiles = farm.get("tiles", [])

    plant_tiles: List[Tuple[Position, Dict[str, Any]]] = []
    weed_tiles: List[Position] = []
    structure_tiles: List[Tuple[Position, Dict[str, Any]]] = []
    empty_tiles: List[Position] = []
    locked_tiles: List[Position] = []

    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            pos: Position = (x, y)
            if tile is None:
                empty_tiles.append(pos)
            elif tile == TILE_LOCKED:
                locked_tiles.append(pos)
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == TILE_KIND_WEED:
                    weed_tiles.append(pos)
                elif kind in ANIMAL_STRUCTURE_KINDS:
                    structure_tiles.append((pos, tile))
                else:
                    # kind == "PLANT" (ou futur type inconnu : traité comme
                    # une plante brute, laissé tel quel pour l'analyzer)
                    plant_tiles.append((pos, tile))
            # tout autre type de valeur est ignoré silencieusement au niveau
            # parsing ; agent.py peut logger un avertissement si besoin.

    return {
        "plant_tiles": plant_tiles,
        "weed_tiles": weed_tiles,
        "structure_tiles": structure_tiles,
        "empty_tiles": empty_tiles,
        "locked_tiles": locked_tiles,
        "board_size": len(tiles),
    }


def parse_workers(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait les positions du farmer et des hands de la propre farm."""
    farm = _own_farm(obs)
    farmer_pos = farm.get("farmer")
    hands_pos = farm.get("hands", [])
    return {
        "farmer_position": tuple(farmer_pos) if farmer_pos else None,
        "hands_positions": [tuple(p) for p in hands_pos],
    }


def parse_market(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait prix et inventaire du marché partagé."""
    market = obs.get("market", {}) or {}
    return {
        "prices": dict(market.get("prices", {})),
        "inventory": dict(market.get("inventory", {})),
    }


def parse_town(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait la liste des boutiques débloquées (peut contenir des doublons)."""
    town = obs.get("town", {}) or {}
    return {"unlocked_shops": list(town.get("unlocked_shops", []))}


def parse_opponent(obs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrait l'état PUBLIC de l'adversaire (son shed privé n'est jamais visible
    dans obs, donc on ne peut décrire que sa farm publique).
    """
    farm = _opponent_farm(obs)
    farmer_pos = farm.get("farmer")
    return {
        "player_index": 1 - obs.get("player", 0),
        "money": farm.get("money", 0.0),
        "unlocked_quadrants": list(farm.get("unlocked_quadrants", [])),
        "farmer_position": tuple(farmer_pos) if farmer_pos else None,
        "hands_positions": [tuple(p) for p in farm.get("hands", [])],
        "tiles": farm.get("tiles", []),
    }
