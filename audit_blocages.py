#!/usr/bin/env python3
"""Cherche ce qui peut figer la fenetre.

Une operation lente appelee depuis un gestionnaire d'evenements bloque la
boucle Qt, donc l'affichage entier. On repere ici les appels couteux — base
de donnees, reseau, systeme de fichiers, sous-processus — qui ne sont pas
deja dans un fil de fond.

Le controle est statique : il lit le code, il ne l'execute pas. Il signale
des suspects, pas des certitudes, et il a deux angles morts connus, payes
tous les deux :

  - il ne voit que les fonctions dont le nom annonce un evenement. Le
    recensement des episodes de podcasts, qui testait deux mille trois cents
    fichiers sur le fil graphique, s'appelait `_telecharger_tous_les_manquants`
    et passait donc au travers ;
  - il ne voit que du code Python. Le plus gros gel du demarrage se passait
    *dans Qt*, entre l'emission d'un signal et sa reception — voir
    verifier_signaux.py.

Pour le reste, la mesure prime : un battement de coeur dans la boucle
d'evenements et une sonde qui echantillonne la pile du fil graphique disent
ce qu'aucune lecture de code ne dira.

    python audit_blocages.py            # tout le dossier
    python audit_blocages.py fichier.py
"""
import ast
import pathlib
import sys

# Ce qui coute cher, par famille.
# « get » et « join » sont ecartes : dict.get et str.join portent les memes
# noms que requests.get et Thread.join, et noyaient les vrais suspects sous
# des centaines de faux.
COUTEUX = {
    'base': {'execute', 'fetchall', 'fetchone', 'commit', 'checkpoint',
             'executemany', 'backup_database'},
    'réseau': {'urlopen', 'post', 'urlretrieve'},
    'fichiers': {'isfile', 'exists', 'getsize', 'listdir', 'walk', 'glob',
                 'rglob', 'copy2', 'copy', 'move', 'rmtree', 'disk_usage',
                 'getmtime'},
    'processus': {'run', 'check_output', 'call', 'Popen'},
    'attente': {'sleep'},
}
TOUS = {nom: famille for famille, noms in COUTEUX.items() for nom in noms}

# Une fonction dont le nom commence ainsi repond a un evenement : elle
# s'execute sur le fil graphique.
PREFIXES_EVENEMENT = ('_on_', 'on_', 'paint', 'mouse', 'key', 'close',
                      'show', 'drag', 'drop', 'resize', 'event')


def analyser(chemin: pathlib.Path):
    try:
        source = chemin.read_text(encoding='utf-8')
        arbre = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    suspects = []
    for fonction in ast.walk(arbre):
        if not isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not fonction.name.startswith(PREFIXES_EVENEMENT):
            continue

        # Les corps de fonctions imbriquees sont ecartes : y mettre le travail
        # couteux, puis les lancer dans un fil, c'est justement la bonne facon
        # de faire.
        interieurs = set()
        for interne in ast.walk(fonction):
            if (isinstance(interne, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and interne is not fonction):
                interieurs.update(id(n) for n in ast.walk(interne))

        for noeud in ast.walk(fonction):
            if id(noeud) in interieurs or not isinstance(noeud, ast.Call):
                continue
            cible = noeud.func
            appele = (cible.attr if isinstance(cible, ast.Attribute)
                      else cible.id if isinstance(cible, ast.Name) else '')
            if appele in TOUS:
                suspects.append((noeud.lineno, fonction.name, appele, TOUS[appele]))
    return suspects


def main(argv):
    cibles = [pathlib.Path(a) for a in argv[1:]] or sorted(
        pathlib.Path(__file__).parent.glob('*.py'))
    total = 0
    for chemin in cibles:
        if chemin.name == pathlib.Path(__file__).name:
            continue
        suspects = analyser(chemin)
        if not suspects:
            continue
        print(f"\n=== {chemin.name} ===")
        for ligne, fonction, appel, famille in sorted(suspects):
            print(f"  {chemin.name}:{ligne:5d}  {fonction:34s} {appel:16s} ({famille})")
            total += 1
    print(f"\n{total} appel(s) couteux sur le fil graphique — a juger un par un.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
