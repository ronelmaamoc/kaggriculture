

## Révision active

Le CriticAgent n'est pas un simple filtre. Lorsqu'il détecte des violations
réparables ou une contrainte forte, il tente de construire un `revised_plan` :
réduction des actions à faible valeur en cas de pénurie, résolution des conflits
de cible, réallocation des phases workers et priorité aux ventes indépendantes
avant les dépenses. Le Coordinator consomme `critique.revised_plan` lorsque la
révision est validée. Le rejet reste réservé aux plans qui restent réellement
non réparables après cette tentative.
