# Kaggriculture Strategy V5.9.0

## Correctifs opérationnels

- Replanification worker à chaque observation au lieu de figer le plan pour toute la journée.
- Le plan opérationnel repart de l'heure et des positions réelles courantes.
- Priorité opérationnelle aux actions de survie (`FEED`, `WATER`) puis récolte et production.
- Suppression des fenêtres horaires artificielles qui retardaient les actions urgentes.
- Limitation des tâches `FERTILIZE` au stock réel de fertilisant.
- Limitation des tâches `FEED`/`PICKUP` aux ressources réellement disponibles.
- Cap workers aligné sur le scheduler : farmer + 4 farm hands maximum.
- Validation d'exécution dynamique : une cible récoltée/détruite plus tôt dans le même tour est invalidée pour les steps suivants.
- Correction de la validation `DIG`/`DUG`.
- Ajout de tests de régression V5.9.

## Limitation connue de l'environnement de validation local

Le conteneur de développement utilisé pour produire cette archive ne contient pas `kaggle_environments`. Les tests unitaires indépendants de Kaggle ont été exécutés avec succès ; le benchmark `local_kaggle_batch.py` doit être relancé dans l'environnement Kaggle/venv du projet.
