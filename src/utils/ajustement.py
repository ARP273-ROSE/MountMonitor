# -*- coding: utf-8 -*-
"""Une pente, ou rien — mais jamais une exception.

`numpy.polyfit` leve `LinAlgError: SVD did not converge` des que
l'ajustement est degenere : tous les instants egaux, des valeurs non finies,
moins de deux points distincts. Cela arrive pour de vrai — un fichier de
session tronque, une session tenant dans la meme seconde — et cela tombait au
milieu de la construction du rapport de nuit, dont l'ouverture n'est pas
protegee : l'application disparaissait.

Un rapport qui ne peut pas calculer une derive doit l'ecrire, pas mourir.
"""

import logging

import numpy as np

log = logging.getLogger(__name__)


def pente(temps, valeurs):
    """Pente d'une droite ajustee, en unite de `valeurs` par unite de `temps`.

    Renvoie ``None`` quand la question n'a pas de reponse plutot que d'en
    inventer une : c'est au texte du rapport de dire « non calculable ».
    """
    try:
        t = np.asarray(temps, dtype=np.float64)
        y = np.asarray(valeurs, dtype=np.float64)
    except (TypeError, ValueError):
        return None

    if t.size < 2 or t.size != y.size:
        return None
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(y))):
        return None
    # Sans etendue en temps, la droite n'est pas definie : une infinite de
    # pentes passent par le meme instant.
    if float(np.ptp(t)) <= 0:
        return None

    try:
        coefficients = np.polyfit(t, y, 1)
    except (np.linalg.LinAlgError, ValueError, TypeError):
        log.debug("Ajustement impossible sur %d points", t.size, exc_info=True)
        return None

    valeur = float(coefficients[0])
    return valeur if np.isfinite(valeur) else None
