# -*- coding: utf-8 -*-
"""Trilingual interface: no displayed text hard-coded in one language.

Every displayed text goes through T("key") (src/utils/i18n.py, three
languages) — or, in the 10micron log dialog, through _tr(en, fr) whose
Dutch lives in _NL. This test catches:

  - a literal passed as-is to a widget (setText, QLabel, QMessageBox, addItem...);
  - a _tr() pair whose English has no Dutch counterpart;
  - a kit_aide text missing a language.

    python -m pytest -q tests/test_textes_en_dur.py
"""
import ast
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

SOURCES = [RACINE / 'main.py', RACINE / 'kit_aide.py', *sorted((RACINE / 'src' / 'gui').glob('*.py'))]
METHODES = {'setText', 'setWindowTitle', 'setToolTip', 'setPlaceholderText',
            'addAction', 'addMenu', 'setTitle', 'showMessage', 'setStatusTip',
            'addTab', 'setLabelText', 'addItem', 'addItems', 'setInformativeText',
            'setDetailedText', 'setWhatsThis', 'setTabText', 'setHorizontalHeaderLabels',
            'setHeaderLabels', 'setSpecialValueText', 'setSuffix', 'setPrefix', 'addRow',
            'insertItem', 'setItemText'}
CONSTRUCTEURS = {'QLabel', 'QPushButton', 'QCheckBox', 'QGroupBox', 'QAction',
                 'QRadioButton', 'QMenu', 'QToolButton', 'QProgressDialog'}
BOITES = {'information', 'warning', 'critical', 'question', 'about'}
# the same in every language: product names, units, protocols
TECHNIQUES = {'mountmonitor', 'fft', 'hz', 'lx', 'tcp', 'ip', 'ascom', 'max', 'min', 'ok'}
BALISE = re.compile(r'<[^>]*>|&[a-z]+;|&#\d+;')
MOT = re.compile(r"[A-Za-zÀ-ÿ]{2,}")


def _litteraux(noeud):
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return [noeud.value]
    if isinstance(noeud, ast.JoinedStr):
        return [v.value for v in noeud.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(noeud, ast.BinOp):
        return _litteraux(noeud.left) + _litteraux(noeud.right)
    if isinstance(noeud, (ast.List, ast.Tuple)):
        return [x for e in noeud.elts for x in _litteraux(e)]
    return []


def _nom(appel):
    f = appel.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')


def test_aucun_texte_affiche_en_dur():
    fautes = []
    for fichier in SOURCES:
        for n in ast.walk(ast.parse(fichier.read_text(encoding='utf-8'))):
            if not isinstance(n, ast.Call):
                continue
            nom = _nom(n)
            if nom in METHODES or nom in CONSTRUCTEURS:
                args = n.args[:1]
            elif nom in BOITES and getattr(getattr(n.func, 'value', None), 'id', '') == 'QMessageBox':
                args = n.args[1:3]
            else:
                continue
            for a in args:
                mots = [m for t in _litteraux(a) for m in MOT.findall(BALISE.sub(' ', t))
                        if m.lower() not in TECHNIQUES]
                if mots:
                    fautes.append(f"{fichier.name}:{n.lineno} {nom} -> {' '.join(mots)[:80]}")
    assert not fautes, "Displayed texts without translation:\n  " + "\n  ".join(fautes)


def test_le_dialogue_log10m_parle_neerlandais():
    from src.gui import log10m_dialog
    manquants = []
    arbre = ast.parse((RACINE / 'src' / 'gui' / 'log10m_dialog.py').read_text(encoding='utf-8'))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == '_tr':
            en = n.args[0]
            if not (isinstance(en, ast.Constant) and isinstance(en.value, str)):
                manquants.append(f"ligne {n.lineno} : texte calculé (f-string)")
            elif en.value not in log10m_dialog._NL:
                manquants.append(f"ligne {n.lineno} : {en.value!r}")
    assert not manquants, manquants


def test_textes_du_menu_aide_dans_les_trois_langues():
    import kit_aide
    for cle, jeu in kit_aide.TEXTES.items():
        for lg in ('en', 'fr', 'nl'):
            assert jeu.get(lg), (cle, lg)
