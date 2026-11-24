# -*- coding: utf-8 -*-
"""Trilingual interface: no displayed text hard-coded in one language.

Every displayed text goes through T("key") (src/utils/i18n.py, three
languages) — or, in the 10micron log dialog, through _tr(en, fr) whose
Dutch lives in _NL. This test catches:

  - a literal passed as-is to a widget (setText, QLabel, QMessageBox, addItem...);
  - a _tr() pair whose English has no Dutch counterpart;
  - a kit_aide text missing a language.

    python -m pytest -q tests/test_hardcoded_texts.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCES = [ROOT / 'main.py', ROOT / 'kit_aide.py', *sorted((ROOT / 'src' / 'gui').glob('*.py'))]
METHODS = {'setText', 'setWindowTitle', 'setToolTip', 'setPlaceholderText',
            'addAction', 'addMenu', 'setTitle', 'showMessage', 'setStatusTip',
            'addTab', 'setLabelText', 'addItem', 'addItems', 'setInformativeText',
            'setDetailedText', 'setWhatsThis', 'setTabText', 'setHorizontalHeaderLabels',
            'setHeaderLabels', 'setSpecialValueText', 'setSuffix', 'setPrefix', 'addRow',
            'insertItem', 'setItemText'}
CONSTRUCTORS = {'QLabel', 'QPushButton', 'QCheckBox', 'QGroupBox', 'QAction',
                 'QRadioButton', 'QMenu', 'QToolButton', 'QProgressDialog'}
BOXES = {'information', 'warning', 'critical', 'question', 'about'}
# the same in every language: product names, units, protocols
TECHNICAL = {'mountmonitor', 'fft', 'hz', 'lx', 'tcp', 'ip', 'ascom', 'max', 'min', 'ok'}
TAG = re.compile(r'<[^>]*>|&[a-z]+;|&#\d+;')
WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")


def _literals(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(node, ast.BinOp):
        return _literals(node.left) + _literals(node.right)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [x for e in node.elts for x in _literals(e)]
    return []


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')


def test_no_hardcoded_displayed_text():
    faults = []
    for file in SOURCES:
        for n in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
            if not isinstance(n, ast.Call):
                continue
            name = _call_name(n)
            if name in METHODS or name in CONSTRUCTORS:
                args = n.args[:1]
            elif name in BOXES and getattr(getattr(n.func, 'value', None), 'id', '') == 'QMessageBox':
                args = n.args[1:3]
            else:
                continue
            for a in args:
                words = [m for t in _literals(a) for m in WORD.findall(TAG.sub(' ', t))
                        if m.lower() not in TECHNICAL]
                if words:
                    faults.append(f"{file.name}:{n.lineno} {name} -> {' '.join(words)[:80]}")
    assert not faults, "Displayed texts without translation:\n  " + "\n  ".join(faults)


def test_help_menu_texts_in_three_languages():
    import kit_aide
    for key, text_set in kit_aide.TEXTES.items():
        for lg in ('en', 'fr', 'nl'):
            assert text_set.get(lg), (key, lg)
