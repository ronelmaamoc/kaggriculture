"""
error_handler.py — Classification récupérable / non récupérable (spec section 17).

Une erreur récupérable (ex: ACTION_REJECTED sur UN step) ne doit pas
arrêter le reste du tour — voir spec section 16, exemple A/B/C ->
PARTIAL avec [A, C] exécutés. Une erreur non récupérable (panne du
transport vers Kaggriculture, état d'environnement incohérent) arrête
proprement l'exécution du reste des steps dus ce tour (spec section 17).
"""

from .constants import NON_RECOVERABLE_CODES


def is_recoverable(error_code: str) -> bool:
    return error_code not in NON_RECOVERABLE_CODES


def is_critical(error_code: str) -> bool:
    return not is_recoverable(error_code)
