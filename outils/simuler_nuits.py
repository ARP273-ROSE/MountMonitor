#!/usr/bin/env python3
"""Rejoue trois nuits d'affilee, pour verifier que le programme les enchaine.

Ce scenario demande une vraie fenetre : l'instancier sous pytest fait tomber
Qt, si bien qu'il vit ici plutot que dans la suite de tests. La suite garde
le garde-fou qui empeche la boucle (test_le_garde_fou_de_jour_empeche_la_boucle).

    QT_QPA_PLATFORM=offscreen python3 outils/simuler_nuits.py
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication            # noqa: E402

app = QApplication([])

import src.core.ephemerides as E                    # noqa: E402
from src.config.settings import Settings            # noqa: E402
from src.gui.main_window import MainWindow          # noqa: E402
from src.models.mount_data import MountStatus       # noqa: E402

ok = ko = 0


def v(nom, cond):
    global ok, ko
    print(("  OK    " if cond else "  ECHEC ") + nom)
    if cond:
        ok += 1
    else:
        ko += 1


reglages = Settings()
reglages.set("mount_protocol", "simulation")
for cle in ("autostart_on_tracking", "pause_when_not_tracking", "close_at_sunrise"):
    reglages.set(cle, True)

w = MainWindow()
w._settings = reglages
w._site = lambda: (49.3061, 2.7553, 57)
w._connected = True
w._prev_mount_status = MountStatus.PARKED

soleil = [+10.0]
E.hauteur_soleil = lambda *a, **k: soleil[0]

w._armer()
v("jour 0 : arme, et n'enregistre pas en plein jour",
  w._logging_armed and not w._logging_active)

fichiers = []
for nuit in (1, 2, 3):
    print(f"--- nuit {nuit} ---")
    soleil[0] = -20.0
    w._on_status_changed(MountStatus.TRACKING)
    v("  le soir : enregistre", w._ecrit_echantillons())
    fichier = str(w._file_logger.dat_path)
    fichiers.append(fichier)

    w._on_status_changed(MountStatus.PARKED)
    w._suspendre()
    v("  park en pleine nuit : suspendu, session ouverte",
      w._logging_suspendu and w._logging_active)
    w._on_status_changed(MountStatus.TRACKING)
    v("  reprend dans le MEME fichier", str(w._file_logger.dat_path) == fichier)

    w._surveiller_aube()
    soleil[0] = +10.0
    w._surveiller_aube()
    v("  lever : cloture et rapport ecrit", not w._logging_active)
    v("  et se rearme pour le soir", w._logging_armed)

    w._on_status_changed(MountStatus.TRACKING)
    v("  la monture suit en plein jour : rien ne demarre",
      not w._logging_active and w._logging_armed)
    time.sleep(1.1)          # pour que l'horodatage du fichier change

print("--- bilan ---")
v("trois fichiers distincts, un par nuit", len(set(fichiers)) == 3)
for f in fichiers:
    print("     ", os.path.basename(f))
v("toujours arme a la fin", w._logging_armed and not w._logging_active)
print()
print(f"RESULTAT : {ok} OK, {ko} ECHEC")
sys.exit(1 if ko else 0)
