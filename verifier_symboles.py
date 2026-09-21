#!/usr/bin/env python3
"""Cherche les noms utilisés mais jamais importés.

Python ne s'en aperçoit qu'à l'exécution de la ligne fautive. Une classe
définie au fond d'une méthode rarement appelée peut donc rester des mois sans
rien dire, puis faire tomber l'application le jour où cette méthode devient
automatique.

C'est exactement ce qui est arrivé : `RefreshWorker(QObject)` vivait dans une
fonction déclenchée par un clic de menu, et `QObject` n'avait jamais été
importé. Le jour où la relecture des flux est passée au démarrage, le
logiciel a planté à chaque ouverture — chez quelqu'un d'autre.

Ce contrôle est statique et sans dépendance : il lit les fichiers, il ne les
exécute pas.

    python verifier_symboles.py            # tout le dossier
    python verifier_symboles.py fichier.py
"""

import ast
import pathlib
import re
import sys

# Ce que Python fournit sans rien importer.
INTEGRES = set(dir(__builtins__)) | {
    '__file__', '__name__', '__doc__', 'self', 'cls',
}

# Un nom de classe : initiale majuscule, et au moins une minuscule — ce qui
# écarte les constantes en capitales.
#
# Un premier jet exigeait une majuscule interne, à la manière de
# « MainWindow ». C'était passer à côté de « QObject », précisément le nom qui
# manquait : un contrôle qui ne voit pas le défaut qu'il est censé attraper ne
# sert à rien.
MOTIF_CLASSE = re.compile(r'^[A-Z][A-Za-z0-9_]*$')


def _ressemble_a_une_classe(nom: str) -> bool:
    return bool(MOTIF_CLASSE.match(nom)) and any(c.islower() for c in nom)


def noms_definis(arbre: ast.AST) -> set[str]:
    """Tout ce que le fichier définit ou importe, où que ce soit."""
    connus = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Import, ast.ImportFrom)):
            for alias in noeud.names:
                connus.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            connus.add(noeud.name)
            for arg in getattr(noeud, 'args', ast.arguments(
                    posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])).args:
                connus.add(arg.arg)
        elif isinstance(noeud, ast.Name) and isinstance(noeud.ctx, ast.Store):
            connus.add(noeud.id)
        elif isinstance(noeud, ast.arg):
            connus.add(noeud.arg)
        elif isinstance(noeud, ast.ExceptHandler) and noeud.name:
            connus.add(noeud.name)
        elif isinstance(noeud, ast.Global):
            connus.update(noeud.names)
    return connus


def verifier(chemin: pathlib.Path) -> list[tuple[int, str]]:
    """Renvoie [(ligne, nom)] des classes utilisées sans jamais être définies."""
    try:
        source = chemin.read_text(encoding='utf-8')
        arbre = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    connus = noms_definis(arbre) | INTEGRES
    manquants = {}
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Name) and isinstance(noeud.ctx, ast.Load)
                and _ressemble_a_une_classe(noeud.id) and noeud.id not in connus):
            manquants.setdefault(noeud.id, noeud.lineno)
    return sorted((ligne, nom) for nom, ligne in manquants.items())


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
    fautes = 0
    for chemin in cibles:
        if chemin.name == pathlib.Path(__file__).name:
            continue
        for ligne, nom in verifier(chemin):
            print(f"{chemin.name}:{ligne}: {nom} est utilisé mais jamais importé")
            fautes += 1
    if fautes:
        print(f"\n{fautes} nom(s) manquant(s) : l'application tombera en les atteignant.")
        return 1
    print(f"{len(cibles)} fichier(s) verifie(s) : aucun nom manquant.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
