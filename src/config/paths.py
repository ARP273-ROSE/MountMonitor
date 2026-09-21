# -*- coding: utf-8 -*-
"""Ou l'application ecrit ses donnees.

Lancee depuis les sources — ce que fait son auteur — MountMonitor ecrit a cote
de son code : les journaux dans `Logs/`, les reglages a la racine. C'est
pratique, et rien ne le remet en cause.

Installee, c'est intenable. Le dossier d'installation appartient a
l'installeur : il en efface le contenu avant de poser une nouvelle version,
precisement pour qu'aucun fichier d'une version passee n'y survive. Les
journaux d'une nuit d'acquisition et les reglages de la monture y
disparaitraient a la premiere mise a jour.

Installee, l'application ecrit donc dans `%LOCALAPPDATA%\\MountMonitor`, qui ne
depend d'aucune version.

Rien n'est deplace : les deux cas ne se rencontrent jamais sur une meme
machine, et un deplacement automatique de donnees d'acquisition est
exactement le genre d'operation qu'on ne fait pas dans le dos de quelqu'un.
"""

import os
import sys
from pathlib import Path

_RACINE_PROJET = Path(__file__).resolve().parent.parent.parent


def est_empaquete() -> bool:
    """Vrai si l'on tourne depuis le paquet autonome (python embarque a cote).

    Le paquet range le code dans `app/` et l'interpreteur dans `python/`, cote
    a cote. C'est la signature la plus sure : elle ne depend ni d'une variable
    d'environnement ni d'un drapeau qu'on pourrait oublier de poser.
    """
    return (_RACINE_PROJET.parent / 'python' / 'python.exe').exists()


def dossier_donnees() -> Path:
    """Dossier ou ecrire journaux, reglages et rapports."""
    if not est_empaquete():
        return _RACINE_PROJET

    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA')
                    or Path.home() / 'AppData' / 'Local')
    else:
        base = Path(os.environ.get('XDG_DATA_HOME')
                    or Path.home() / '.local' / 'share')
    dossier = base / 'MountMonitor'
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def dossier_journaux() -> Path:
    """Dossier des fichiers de session (.log, .dat, .dti, .sei, .fft, .env)."""
    journaux = dossier_donnees() / 'Logs'
    journaux.mkdir(parents=True, exist_ok=True)
    return journaux


def fichier_reglages() -> Path:
    return dossier_donnees() / 'mountmonitor_settings.json'
