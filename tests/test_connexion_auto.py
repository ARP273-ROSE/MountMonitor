# -*- coding: utf-8 -*-
"""Connection at launch (--connect / connect_on_launch): first attempt, retries
while the mount does not answer, stop at the first success or when the user
takes over, never a dialog.

    xvfb-run -a python -m pytest -q tests/test_connexion_auto.py
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix='mm-test-auto-')
os.environ.setdefault('QT_QPA_PLATFORM', 'xcb' if os.environ.get('DISPLAY') else 'offscreen')

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

pytest.importorskip('PyQt6')
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import reporting  # noqa: E402

Path(_TMP, 'reglages_rapports.json').write_text('{"envoi_autorise": false}', encoding='utf-8')
reporting.init(_TMP, application='mountmonitor-essais', version='0')


def _port_ferme():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()                       # plus personne n'ecoute : connexion refusee
    return port


@pytest.fixture
def reglages(monkeypatch):
    from src.config.settings import Settings
    s = Settings()
    avant = {k: s.get(k) for k in ('mount_protocol', 'mount_ip', 'mount_port', 'ascom_driver',
                                    'connect_on_launch', 'connect_retry_s', 'serial_port')}
    # Les relances passent par QTimer.singleShot : on les note au lieu d'attendre.
    planifies = []
    monkeypatch.setattr(QTimer, 'singleShot', staticmethod(lambda ms, f: planifies.append((ms, f))))
    yield s, planifies
    for k, v in avant.items():
        s.set(k, v)


def _fenetre(**kw):
    from src.gui.main_window import MainWindow
    return MainWindow(**kw)


def test_par_defaut_aucune_connexion_au_lancement(reglages):
    s, planifies = reglages
    s.set('connect_on_launch', False)
    win = _fenetre()
    assert not win._connexion_auto_active
    assert not any(f == win._connexion_automatique for _, f in planifies)
    win.hide()


def test_monture_muette_puis_nouvel_essai(reglages):
    s, planifies = reglages
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _port_ferme())
    s.set('connect_retry_s', 30)
    win = _fenetre(auto_connect=True)
    assert win._connexion_auto_active
    assert (1500, win._connexion_automatique) in planifies
    planifies.clear()
    win._connexion_automatique()                       # 1er essai : refuse
    assert not win._connected
    assert win._essais_connexion == 1
    assert (30000, win._connexion_automatique) in planifies   # relance dans 30 s
    win._connexion_automatique()                       # 2e essai
    assert win._essais_connexion == 2
    win.hide()


def test_la_monture_repond_et_les_essais_s_arretent(reglages):
    s, planifies = reglages
    s.set('mount_protocol', 'simulation')
    win = _fenetre(auto_connect=True)
    win._connexion_automatique()
    assert win._connected
    assert not win._connexion_auto_active
    planifies.clear()
    win._connexion_automatique()                       # une relance en retard ne refait rien
    assert win._essais_connexion == 1 and not planifies
    win._disconnect()
    win.hide()


def test_reglage_connect_on_launch_equivaut_a_l_option(reglages):
    s, planifies = reglages
    s.set('connect_on_launch', True)
    win = _fenetre()
    assert win._connexion_auto_active
    assert (1500, win._connexion_automatique) in planifies
    win.hide()


def test_un_clic_de_l_utilisateur_arrete_les_essais(reglages):
    s, planifies = reglages
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _port_ferme())
    win = _fenetre(auto_connect=True)
    win._connexion_automatique()
    assert win._connexion_auto_active
    win._toggle_connection()                           # il clique sur Connecter (refuse aussi)
    assert not win._connexion_auto_active
    planifies.clear()
    win._connexion_automatique()                       # la relance deja planifiee ne fait rien
    assert win._essais_connexion == 1 and not planifies
    win.hide()


def test_ascom_sans_pilote_n_ouvre_pas_le_selecteur(reglages, monkeypatch):
    s, planifies = reglages
    s.set('mount_protocol', 'ascom'); s.set('ascom_driver', '')
    import src.gui.preferences_dialog as pd
    monkeypatch.setattr(pd, '_ascom_choose', lambda *a: pytest.fail('selecteur ASCOM ouvert'))
    win = _fenetre(auto_connect=True)
    win._connexion_automatique()
    assert not win._connexion_auto_active and not win._connected
    win.hide()


def test_delai_minimum_de_5_s(reglages):
    s, planifies = reglages
    s.set('mount_protocol', 'lx200'); s.set('mount_ip', '127.0.0.1'); s.set('mount_port', _port_ferme())
    s.set('connect_retry_s', 0)
    win = _fenetre(auto_connect=True)
    planifies.clear()
    win._connexion_automatique()
    assert (5000, win._connexion_automatique) in planifies
    win.hide()


def test_option_connect_reconnue():
    import main
    sys_argv = sys.argv
    try:
        sys.argv = ['main.py', '--connect']
        assert main.parse_args().connect is True
        sys.argv = ['main.py']
        assert main.parse_args().connect is False
    finally:
        sys.argv = sys_argv
