#!/usr/bin/env python3
"""Verifie l'accord entre l'installeur et l'application.

Deux points qui ne se voient qu'a l'usage, et tard :

  - `AppMutex` dans installer.iss doit porter exactement le nom du verrou
    pose par l'application. S'ils divergent, l'installeur croit que rien ne
    tourne, n'arrive pas a remplacer les fichiers ouverts, et l'utilisateur
    se retrouve avec une installation qui dit « terminee » mais un logiciel
    qui repart dans l'ancienne version.
  - `[InstallDelete]` doit effacer le dossier applicatif avant la copie.
    Inno ecrase ce qu'il apporte, jamais ce qu'il n'apporte plus ; or la mise
    a jour automatique deballe une archive dans ce meme dossier.

Controle statique, sans dependance.
"""

import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).parent


def main():
    import json
    iss = (RACINE / 'installer.iss').read_text(encoding='utf-8', errors='replace')
    fiche = json.loads((RACINE / 'kit.json').read_text(encoding='utf-8'))
    # Le verrou est pose par le point d'entree, quel que soit son nom : c'est
    # kit.json qui le dit, comme pour tout le reste du dispositif.
    source = (RACINE / fiche['point_entree']).read_text(encoding='utf-8')
    attendu = f"{fiche['nom_fichier']}EnCours"
    fautes = []

    trouve = re.search(r'^AppMutex\s*=\s*(\S+)\s*$', iss, re.MULTILINE)
    if not trouve:
        fautes.append("installer.iss ne declare aucun AppMutex : une "
                      "installation par-dessus l'application ouverte echouera "
                      "sans le dire.")
    else:
        nom = trouve.group(1).replace('{#AppName}', fiche['nom_fichier'])
        if nom != attendu:
            fautes.append(f"AppMutex resout en « {nom} », attendu « {attendu} ».")
        if f"'{nom}'" not in source and f'"{nom}"' not in source:
            fautes.append(f"AppMutex vaut « {nom} » dans installer.iss, mais "
                          f"le point d'entree ne pose pas ce verrou-la.")
        if 'CreateMutexW' not in source:
            fautes.append("Le point d'entree n'appelle pas CreateMutexW : le "
                          "verrou nomme n'existe pas, AppMutex ne verra rien.")

    if '[InstallDelete]' not in iss:
        fautes.append("installer.iss n'a pas de section [InstallDelete] : "
                      "l'ancienne version n'est pas nettoyee avant la copie.")
    else:
        for dossier in (r'{app}\app', r'{app}\python'):
            if dossier not in iss:
                fautes.append(f"[InstallDelete] n'efface pas {dossier}.")

    for faute in fautes:
        print("  " + faute)
    if fautes:
        print(f"\n{len(fautes)} desaccord(s) entre l'installeur et l'application.")
        return 1
    print("Installeur et application d'accord : verrou nomme et nettoyage en place.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
