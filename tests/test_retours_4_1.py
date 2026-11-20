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


# ── Retours du 20/11/2026 (comparaison avec MM3) ─────────────────────────

def test_echelle_ecart_type_regle_mm3():
    from src.gui.graph_widgets import echelle_ecart_type
    assert echelle_ecart_type(0.3) == (1.0, 0.2)        # log10(0.99) -> 0
    haut, pas = echelle_ecart_type(0.04)                # log10(0.132) -> -1
    assert haut == pytest.approx(0.1) and pas == pytest.approx(0.02)
    assert echelle_ecart_type(1.6)[0] == 10.0
    for sd in (0.001, 0.02, 0.13, 0.31, 0.95, 2.9, 40.0):
        assert echelle_ecart_type(sd)[0] >= sd          # la courbe tient toujours
    assert echelle_ecart_type(0)[0] > 0


def test_ecarts_centres_sur_la_mediane_visible():
    from src.core.data_processor import ecarts_a_la_mediane
    v = np.linspace(10.0, 10.0 + 20 / 54000, 101)       # dérive de 20" d'AD
    e = ecarts_a_la_mediane(v, 54000.0, 24.0)
    assert np.median(e) == pytest.approx(0.0, abs=1e-9)
    assert e[0] == pytest.approx(-10.0) and e[-1] == pytest.approx(10.0)
    # passage de 0 h : pas de saut de 24 h
    w = np.array([23.99999, 0.00001, 0.00002])
    assert np.ptp(ecarts_a_la_mediane(w, 3600.0, 24.0)) < 0.2


def test_ligne_du_sismometre_cr_lf_ou_seul():
    from src.core.seismometer import valeur_de_ligne, _FIN
    lignes = _FIN.split(b"512\r\n498\n503\r-12,5\rX\r")
    vals = [valeur_de_ligne(l) for l in lignes]
    assert vals[:4] == [512.0, 498.0, 503.0, -12.5]
    assert valeur_de_ligne(b"abc") is None


def test_refraction_mode_lu_par_wsg(monkeypatch):
    from src.core.lx200_protocol import LX200Connection
    c = LX200Connection.__new__(LX200Connection)
    envoyes = []
    def envoyer(cmd):
        envoyes.append(cmd)
        return {":WSG#": "2", ":GREF#": "1"}[cmd]
    monkeypatch.setattr(c, "_send_command", envoyer)
    assert c.get_refraction_mode() == "continuously_updating"
    assert c.is_refraction_enabled() is True
    assert envoyes == [":WSG#", ":GREF#"]


def test_controles_dans_l_ordre_de_mm3_et_refraction_separee(fenetre):
    from src.gui.preferences_dialog import PreferencesDialog
    from src.utils.i18n import T
    from PyQt6.QtWidgets import QCheckBox
    d = PreferencesDialog(fenetre._settings, fenetre)
    attendus = [T(k) for k in ("check_refr_status_label", "check_refraction_label",
                               "check_gps_label", "check_dual_label", "check_tracking_label")]
    grille = d._check_refr_status.parentWidget().layout()
    ordre = []
    for ligne in range(1, grille.rowCount()):
        it = grille.itemAtPosition(ligne, 0)
        if it and isinstance(it.widget(), QCheckBox):
            ordre.append(it.widget().text())
    assert ordre[:5] == attendus
    d.close()
    # correction de réfraction coupée : un seul avertissement, pas le mode
    w = fenetre
    msgs = []
    w._status_panel.add_message = lambda m, c=None: msgs.append(m)
    w._juger_controles({"refraction": False, "mode": "not_updating"}, True)
    assert any(T("chk_refr_status_ko").split("{")[0] in m for m in msgs)
    assert not any("not updating" in m for m in msgs)


def test_ra_en_secondes_de_temps_ou_en_secondes_d_arc(fenetre, monkeypatch):
    w = fenetre
    vals = {"ra_in_degrees": False, "tolerance_ra_arcsec": 1.5}
    orig = w._settings.get
    monkeypatch.setattr(w._settings, "get", lambda k: vals.get(k, orig(k)))
    assert w._tolerance_ra_affichee() == pytest.approx(0.1)
    vals["ra_in_degrees"] = True
    assert w._tolerance_ra_affichee() == pytest.approx(1.5)


def test_courbe_verte_au_dessus_dans_le_graphe_du_temps(fenetre):
    g = fenetre._time_graph
    assert g._pc_loop_curve.zValue() > max(g._mount_loop_curve.zValue(), g._diff_curve.zValue())


# ── Retours du 20/11/2026 soir (4.3.0 sur sa monture) ────────────────────

def test_vitesse_solaire_n_est_plus_prise_pour_siderale():
    from src.core.mount_connection import classer_vitesse
    assert classer_vitesse("60.2") == "sidereal"
    assert classer_vitesse("60.3") == "solar"          # passait pour sidéral
    assert classer_vitesse("62.4#") == "lunar"
    assert classer_vitesse("Solar") == "solar"         # ASCOM
    assert classer_vitesse("59.1") is None
    assert classer_vitesse(None) is None


def test_alerte_vitesse_unique_et_historique_sans_repetition(fenetre, monkeypatch):
    from src.utils.i18n import T
    w = fenetre
    vals = {"check_tracking_rate": True, "check_tracking_rate_value": "sidereal",
            "check_refraction_status": False, "check_refraction_enabled": False,
            "check_gps_sync": False, "check_dual_tracking": False, "mount_alert_popup": True}
    orig = w._settings.get
    monkeypatch.setattr(w._settings, "get", lambda k: vals.get(k, orig(k)))
    msgs = []
    w._status_panel.add_message = lambda m, c=None: msgs.append(m)
    for _ in range(3):                                  # contrôle périodique
        w._juger_controles({"rate": "60.3"}, True)
    assert sum(T("val_solar") in m for m in msgs) == 1  # une ligne, pas trois
    boite = w._boite_alerte
    assert boite.isVisible() and T("val_solar") in boite.text()
    w._juger_controles({"rate": "60.2"}, True)          # corrigé au clavier
    assert not boite.isVisible()


def test_sismometre_centre_comme_mm3():
    from src.core.seismometer import Seismometer
    s = Seismometer(offset=300)
    recus = []
    s.set_callback(lambda t, v: recus.extend(v))

    class Port:
        def __init__(self):
            self.donnees = [b"-354\r\n-344\r\n-256\r\n"]
            self.in_waiting = 0
        def read(self, n):
            s._running = bool(self.donnees) and s._running
            return self.donnees.pop(0) if self.donnees else b""
    s._serial = Port()
    s._running = True
    s._read_loop()
    assert s.get_recent_data(3) == [-54.0, -44.0, 44.0]


def test_graphes_alignes_a_droite(fenetre):
    from src.gui.graph_widgets import LARGEUR_AXE_DROIT, LARGEUR_AXE_GAUCHE
    for g in (fenetre._ra_graph, fenetre._dec_graph, fenetre._time_graph, fenetre._seismic_graph):
        pi = g._plot.getPlotItem()
        assert pi.getAxis('right').fixedWidth == LARGEUR_AXE_DROIT
        assert pi.getAxis('left').fixedWidth == LARGEUR_AXE_GAUCHE
