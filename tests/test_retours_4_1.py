# -*- coding: utf-8 -*-
"""Retours sur la 4.1.0 (19/11/2026) : durée affichée, échelle
verticale, panneau de droite, dérive d'horloge, bouton armé."""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gui.graph_widgets import (derive_horloge, largeur_affichee,  # noqa: E402
                                   nom_largeur, pas_des_reperes,
                                   plage_verticale, LARGEURS_S)


def test_une_demi_heure_et_une_heure_proposees():
    assert 1800 in LARGEURS_S and 3600 in LARGEURS_S
    assert largeur_affichee(1800) == 1800.0
    assert largeur_affichee(None) == 120.0
    assert largeur_affichee("x") == 120.0
    assert largeur_affichee(-5) == 120.0
    assert nom_largeur(1800) == "30 min" and nom_largeur(30) == "30 s"


def test_reperes_d_heure_lisibles_sur_une_heure():
    for largeur in LARGEURS_S:
        assert largeur / pas_des_reperes(largeur) <= 10
    assert pas_des_reperes(120) == 30


def test_echelle_donnees_ignore_la_tolerance():
    v = np.array([0.02, -0.03, 0.05, 0.0])
    bas, haut = plage_verticale("data", v, tolerance=0.25)
    assert haut < 0.25 and bas > -0.25          # lignes de tolérance hors cadre
    assert bas <= v.min() and haut >= v.max()
    bas, haut = plage_verticale("tolerance", v, tolerance=0.25)
    assert haut == pytest.approx(0.3)
    bas, haut = plage_verticale("maximum", v, tolerance=0.25)
    assert haut >= 0.25
    bas, haut = plage_verticale("minmax", v, 0.25, min_val=-0.4, max_val=0.1)
    assert haut == pytest.approx(0.48)


def test_echelle_donnees_constantes():
    bas, haut = plage_verticale("data", np.zeros(10), tolerance=1.0)
    assert haut - bas > 0


def test_derive_stable_malgre_le_bruit_et_les_pics():
    rng = np.random.default_rng(1)
    t = np.arange(0, 2400, 0.5)
    v = -10 + 12.0 * t / 3600 + rng.normal(0, 15, len(t))   # 12 ms/h
    v[::97] += 600                                          # boucles lentes
    d = [derive_horloge(t[:n], v[:n]) for n in range(3600, len(t), 7)]
    assert all(abs(x - 12.0) < 5 for x in d)
    # d'un échantillon au suivant, la valeur ne saute plus
    assert max(abs(a - b) for a, b in zip(d, d[1:])) < 1.0


def test_derive_absente_sans_assez_de_donnees():
    t = np.arange(0, 60, 0.5)
    assert derive_horloge(t, t * 0) is None


@pytest.fixture
def fenetre(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.main_window import MainWindow
    w = MainWindow()
    monkeypatch.setattr(w._settings, "save", lambda: None)   # pas le vrai fichier
    yield w
    w.close()
    app.processEvents()


def test_menu_du_graphe_et_echelle_appliquee(fenetre):
    from src.gui.graph_widgets import TrackingGraph
    w = fenetre
    assert not w._ra_graph._plot.plotItem.getViewBox().menuEnabled()
    w._set_vertical_zoom("data")
    t = np.arange(0, 300, 0.5) + 1e6
    v = 0.03 * np.sin(t)
    w._ra_graph.set_tolerance(0.25)
    w._ra_graph.update_data(t, v, largeur_s=120)
    (_, _), (y0, y1) = w._ra_graph._plot.getViewBox().viewRange()
    assert y1 < 0.25
    w._set_largeur(1800)
    assert w._largeur() == 1800.0


def test_bouton_arme_dit_qu_il_attend_la_nuit(fenetre, monkeypatch):
    from src.models.mount_data import MountStatus
    from src.utils.i18n import T
    w = fenetre
    w._prev_mount_status = MountStatus.TRACKING
    monkeypatch.setattr(w, "_fait_jour", lambda: True)
    monkeypatch.setattr(w, "_start_logging", lambda: None)
    w._armer()
    assert w._logging_armed
    assert w._btn_logging.text() == T("btn_armed_night")
    w._desarmer()
    assert w._btn_logging.text() == T("btn_start_log")


def test_panneau_droit_historique_extensible(fenetre):
    from PyQt6.QtWidgets import QSizePolicy
    p = fenetre._status_panel
    assert p._log_text.maximumHeight() > 10000
    from PyQt6.QtWidgets import QFrame
    cadre = p.findChild(QFrame, "valeurs")
    assert cadre.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed


def test_fichiers_ecrits_sur_disque_toutes_les_5_s(tmp_path, monkeypatch):
    from src.logging_module import file_logger as fl
    appels = []
    monkeypatch.setattr(fl.os, "fsync", lambda fd: appels.append(fd))
    lg = fl.FileLogger.__new__(fl.FileLogger)
    f = open(tmp_path / "x.dat", "w")
    for nom in ("_log_file", "_dti_file", "_sei_file", "_fft_file", "_env_file"):
        setattr(lg, nom, None)
    lg._dat_file = f
    lg._write_count, lg._flush_interval = 0, 20
    lg._dernier_flush = fl.time.monotonic() - 6
    assert lg._safe_write(f, "a\n")
    assert appels, "pas d'écriture forcée sur le disque après 5 s"
    f.close()


def test_options_automatiques_au_premier_onglet_et_au_clic_droit(fenetre, monkeypatch):
    from src.gui.preferences_dialog import PreferencesDialog
    from src.utils.i18n import T
    from PyQt6.QtWidgets import QGroupBox
    d = PreferencesDialog(fenetre._settings, fenetre)
    titres = [g.title() for g in d.findChildren(QGroupBox)]
    assert T("pref_unattended") in titres
    d.close()
    # « La nuit seulement » décoché en plein jour, monture qui suit : départ immédiat
    from src.models.mount_data import MountStatus
    w = fenetre
    w._prev_mount_status = MountStatus.TRACKING
    partis = []
    monkeypatch.setattr(w, "_start_logging", lambda: partis.append(1))
    monkeypatch.setattr(w._settings, "set", lambda k, v: None)
    jour = {"v": True}
    monkeypatch.setattr(w, "_fait_jour", lambda: jour["v"])
    w._armer()
    assert not partis
    jour["v"] = False
    w._option_auto("close_at_sunrise", False)
    assert partis
