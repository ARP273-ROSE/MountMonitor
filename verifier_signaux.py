#!/usr/bin/env python3
"""Cherche les signaux Qt declares avec un type qui coute cher.

Un signal declare `pyqtSignal(list)` ou `pyqtSignal(dict)` n'est pas un
simple passage de reference : PyQt convertit la valeur en type Qt a l'envoi,
puis la reconvertit a l'arrivee, element par element.

Mesure faite sur cette application : 341 ms pour transmettre les soixante et
onze mille pistes de la bibliotheque en `list`, contre zero en `object`.
C'etait le plus gros gel du demarrage, et il n'apparaissait dans le profil
d'aucune fonction — le temps se passait dans Qt, entre l'emission et la
reception.

`object` transmet l'objet Python tel quel. Il convient des qu'on ne cherche
pas a se connecter depuis du C++, ce qui est toujours le cas ici.

Une declaration reste legitime en `list` quand la charge est courte et
connue : quelques chemins de fichiers deposes dans la fenetre, par exemple.
Ce controle signale donc des suspects, pas des fautes : la liste des
exceptions assumees est en bas du fichier.

    python verifier_signaux.py            # tout le dossier
    python verifier_signaux.py fichier.py
"""

import ast
import pathlib
import sys

TYPES_COUTEUX = {'list', 'dict'}

# Signaux dont la charge est courte par construction, et qu'il est inutile
# de reecrire. Format : (fichier, nom du signal).
# Mesure faite pour trancher : transmettre une piste de trente-deux champs
# coute 67 us en `dict` contre 48 us en `object`. La conversion ne se paie
# que sur le nombre d'elements ; un seul enregistrement ne pese rien, et
# changer le type changerait aussi le partage de l'objet entre l'emetteur et
# le receveur. On les laisse.
TOLERES = {
    ('poller.py', 'mount_info_ready'),         # une fiche de session
    ('main_window.py', 'files_dropped'),       # chemins d'un glisser-deposer
    ('main_window.py', 'tracks_dropped'),      # identifiants d'une selection
    ('library_watcher.py', 'scan_requested'),  # quelques dossiers
    ('player.py', 'track_changed'),            # une piste
    ('player.py', 'radio_changed'),            # une station
    ('player.py', 'audio_info_changed'),       # un format audio
    ('player.py', '_stream_url_resolved'),     # une adresse et ses entetes
    ('first_run.py', 'finished'),              # un bilan de premier lancement
    ('first_run.py', 'analyse_terminee'),      # un bilan d'analyse
    ('harmonizer.py', 'finished'),             # un bilan d'harmonisation
    ('migration.py', 'finished'),              # un bilan de migration
}


def suspects(chemin: pathlib.Path):
    try:
        arbre = ast.parse(chemin.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return []

    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Assign):
            continue
        appel = noeud.value
        if not (isinstance(appel, ast.Call)
                and getattr(appel.func, 'id', getattr(appel.func, 'attr', '')) == 'pyqtSignal'):
            continue
        types = [a.id for a in appel.args if isinstance(a, ast.Name)]
        if not any(t in TYPES_COUTEUX for t in types):
            continue
        for cible in noeud.targets:
            nom = getattr(cible, 'id', None)
            if nom and (chemin.name, nom) not in TOLERES:
                trouves.append((noeud.lineno, nom, ', '.join(types)))
    return trouves


# Dossiers a ne pas parcourir : rien d'utile, et beaucoup de bruit.
EXCLUS = {'__pycache__', '.git', 'dist', 'build', 'installer_out',
          '.venv', 'venv', 'node_modules', '.build_cache'}


def fichiers_python(racine: pathlib.Path):
    """Tout le code du depot, sous-dossiers compris.

    Ne parcourir que la racine laissait passer les projets dont le code vit
    dans un paquet — c'est-a-dire la plupart. Le controle rendait « aucun
    defaut » sans avoir rien lu.
    """
    for chemin in sorted(racine.rglob('*.py')):
        if EXCLUS.isdisjoint(chemin.parts):
            yield chemin


def main(argv):
    cibles = ([pathlib.Path(a) for a in argv[1:]]
              or list(fichiers_python(pathlib.Path(__file__).parent)))
    total = 0
    for chemin in cibles:
        if chemin.name == pathlib.Path(__file__).name:
            continue
        for ligne, nom, types in suspects(chemin):
            print(f"{chemin.name}:{ligne}: {nom} = pyqtSignal({types}) — "
                  f"`object` transmet sans convertir")
            total += 1
    if total:
        print(f"\n{total} signal(aux) a verifier. Si la charge est courte et "
              f"le restera, ajoutez-les a TOLERES avec la raison.")
        return 1
    print(f"{len(cibles)} fichier(s) verifie(s) : aucun signal couteux.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
