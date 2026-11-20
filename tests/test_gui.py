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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

pytest.importorskip('PyQt6')
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

import reporting  # noqa: E402

Path(_TMP, 'reglages_rapports.json').write_text('{"envoi_autorise": false}', encoding='utf-8')
reporting.init(_TMP, application='mountmonitor-essais', version='0')


def test_frozen_style_font_and_palette_complete():
    from PyQt6.QtGui import QPalette
    from src.gui.theme import COLOURS, apply_dark_theme
    APP.setStyleSheet('')
    apply_dark_theme(APP)
    p = APP.palette()
    G, R = QPalette.ColorGroup, QPalette.ColorRole
    assert p.color(G.Active, R.Window).name() == COLOURS['fenetre']
    assert p.color(G.Disabled, R.Text).name() == COLOURS['desactive']
    assert APP.font().family() == 'Source Sans 3'
    APP.setStyleSheet('')
    assert APP.style().name().lower() == 'fusion'


@pytest.mark.parametrize('language, report', [('en', '&Report a problem...'),
                                             ('fr', '&Signaler un problème...'),
                                             ('nl', '&Probleem melden...')])
def test_window_in_simulation_with_kit_menu(language, report, monkeypatch):
    from src.utils import i18n
    from src.config.settings import Settings
    settings = Settings()
    before = settings.get('language')
    settings.set('language', language)          # the window applies this setting
    from src.gui.main_window import MainWindow
    win = MainWindow(sim_mode='all')
    win.show()
    for _ in range(30):
        APP.processEvents()
    texts = []
    for action in win.menuBar().actions():
        if action.menu():
            texts += [a.text() for a in action.menu().actions()]
    assert report in texts, texts
    assert win._kit_help.act_auto is not None
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    win._show_about()                                   # logo + text in the language
    win.hide()                       # no closeEvent: nothing is saved
    settings.set('language', before)
    i18n.set_language('en')


def test_report_consent_checkbox(monkeypatch):
    from src.gui.main_window import MainWindow
    win = MainWindow(sim_mode='all')
    win._kit_help.act_auto.setChecked(True)
    assert reporting.consentement() is True
    win._kit_help.act_auto.setChecked(False)
    assert reporting.consentement() is False
    win.hide()


def test_file_dialog_complete_on_linux(monkeypatch):
    import interface_kit
    monkeypatch.setenv('KIT_DIALOGUES', 'qt')
    assert interface_kit.installer_dialogues_fichiers()


def test_check_from_command_line():
    r = subprocess.run([sys.executable, '-B', str(ROOT / 'main.py'), '--check'],
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'OK' in r.stdout
