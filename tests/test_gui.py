# -*- coding: utf-8 -*-
"""Interface under Xvfb: the real window in simulation, the fixed look, the
kit wired in, in the three languages.

    xvfb-run -a python -m pytest -q tests/test_gui.py

Settings, logs and report consent are diverted to a throwaway folder; the
report consent there is "no": nothing leaves the machine during the tests.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix='mm-test-')
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb' if os.environ.get('DISPLAY') else 'offscreen')

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

pytest.importorskip('PyQt6')
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

import reporting  # noqa: E402

Path(_TMP, 'reglages_rapports.json').write_text('{"envoi_autorise": false}', encoding='utf-8')
reporting.init(_TMP, application='mountmonitor-essais', version='0')


def test_style_fige_police_et_palette_completes():
    from PyQt6.QtGui import QPalette
    from src.gui.theme import COULEURS, apply_dark_theme
    APP.setStyleSheet('')
    apply_dark_theme(APP)
    p = APP.palette()
    G, R = QPalette.ColorGroup, QPalette.ColorRole
    assert p.color(G.Active, R.Window).name() == COULEURS['fenetre']
    assert p.color(G.Disabled, R.Text).name() == COULEURS['desactive']
    assert APP.font().family() == 'Source Sans 3'
    APP.setStyleSheet('')
    assert APP.style().name().lower() == 'fusion'


@pytest.mark.parametrize('langue, signaler', [('en', '&Report a problem...'),
                                             ('fr', '&Signaler un problème...'),
                                             ('nl', '&Probleem melden...')])
def test_fenetre_en_simulation_avec_le_menu_du_kit(langue, signaler, monkeypatch):
    from src.utils import i18n
    from src.config.settings import Settings
    reglages = Settings()
    avant = reglages.get('language')
    reglages.set('language', langue)          # la fenêtre applique ce réglage
    from src.gui.main_window import MainWindow
    win = MainWindow(sim_mode='all')
    win.show()
    for _ in range(30):
        APP.processEvents()
    textes = []
    for action in win.menuBar().actions():
        if action.menu():
            textes += [a.text() for a in action.menu().actions()]
    assert signaler in textes, textes
    assert win._aide_kit.act_auto is not None
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    win._show_about()                                   # logo + texte dans la langue
    win.hide()                       # sans closeEvent : rien n'est enregistré
    reglages.set('language', avant)
    i18n.set_language('en')


def test_case_d_accord_des_rapports(monkeypatch):
    from src.gui.main_window import MainWindow
    win = MainWindow(sim_mode='all')
    win._aide_kit.act_auto.setChecked(True)
    assert reporting.consentement() is True
    win._aide_kit.act_auto.setChecked(False)
    assert reporting.consentement() is False
    win.hide()


def test_boite_de_fichiers_complete_sous_linux(monkeypatch):
    import interface_kit
    monkeypatch.setenv('KIT_DIALOGUES', 'qt')
    assert interface_kit.installer_dialogues_fichiers()


def test_check_en_ligne_de_commande():
    r = subprocess.run([sys.executable, '-B', str(RACINE / 'main.py'), '--check'],
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'OK' in r.stdout
