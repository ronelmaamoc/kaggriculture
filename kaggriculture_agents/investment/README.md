# InvestmentAgent

Agent d'amorçage et d'investissement. Il transforme les besoins économiques
non couverts par les agents de production en intentions `BUY_SEED`,
`BUY_PRODUCT`, `BUY_ANIMAL`, `BUY_LAND` et `HIRE`. Il ne retourne jamais
directement le dictionnaire Kaggriculture : Economy -> Planner -> Critic ->
Coordinator -> Executor restent responsables de la décision et de l'exécution.
