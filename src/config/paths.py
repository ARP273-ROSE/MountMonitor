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
    python = _RACINE_PROJET.parent / 'python'
    # Windows : python/python.exe ; macOS et Linux : python/bin/python3.
    return (python / 'python.exe').exists() or (python / 'bin' / 'python3').exists()


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
    _reprendre_anciennes_donnees(dossier)
    return dossier


_REPRISE_FAITE = False


def _reprendre_anciennes_donnees(dossier: Path) -> None:
    """Versions <= 1.31 sous macOS et Linux : le paquet ne se reconnaissait pas,
    et reglages, rapports et journaux de session s'ecrivaient dans `app/`.
    On les recopie une fois dans le dossier de donnees, sans rien effacer, et
    sans jamais ecraser ce qui s'y trouve deja."""
    global _REPRISE_FAITE
    if _REPRISE_FAITE or sys.platform == 'win32':
        return
    _REPRISE_FAITE = True
    import shutil
    for nom in ('mountmonitor_settings.json', 'reglages_rapports.json', 'Logs'):
        ancien, neuf = _RACINE_PROJET / nom, dossier / nom
        if not ancien.exists():
            continue
        try:
            if ancien.is_dir():
                for f in ancien.rglob('*'):
                    cible = neuf / f.relative_to(ancien)
                    if f.is_dir():
                        cible.mkdir(parents=True, exist_ok=True)
                    elif not cible.exists():
                        cible.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, cible)
            elif not neuf.exists():
                shutil.copy2(ancien, neuf)
        except OSError:
            pass


def dossier_journaux() -> Path:
    """Dossier des fichiers de session (.log, .dat, .dti, .sei, .fft, .env)."""
    journaux = dossier_donnees() / 'Logs'
    journaux.mkdir(parents=True, exist_ok=True)
    return journaux


def fichier_reglages() -> Path:
    return dossier_donnees() / 'mountmonitor_settings.json'
