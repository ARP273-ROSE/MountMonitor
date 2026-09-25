#!/usr/bin/env python3
"""Verifie, sur la vraie fenetre, que les graphes defilent au present.

Remplit les tampons de trois nuits enchainees, rafraichit, et lit ce que
pyqtgraph affiche reellement : la plage de la vue ET celle des graduations.
MainWindow ne se construit pas sous pytest (Qt tombe), d'ou ce script.

    QT_QPA_PLATFORM=offscreen python3 outils/verifier_defilement.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                  # noqa: E402
from PyQt6.QtWidgets import QApplication            # noqa: E402

app = QApplication([])

from src.config.settings import Settings            # noqa: E402
from src.gui.main_window import MainWindow          # noqa: E402

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
reglages.set("horizontal_zoom", 1)
fen = MainWindow()
fen._settings = reglages
fen.resize(1400, 900)

p = fen._processor
debut = 1790000000.0                  # une date reelle, en secondes
for k in range(3):                    # trois nuits de 8 h a 1,9 Hz
    for t in np.arange(0, 8 * 3600, 1 / 1.9)[::3] + debut + k * 86400:
        p.ra_buffer.append(float(t), 0.05 * np.sin(t / 7))
        p.dec_buffer.append(float(t), 0.1 * np.cos(t / 11))
        p.seismic_buffer.append(float(t), 3 * np.sin(t))
        p.time_diff_buffer.append(float(t), 1.0)

for zoom, attendu in ((1, 120.0), (5, 24.0)):
    reglages.set("horizontal_zoom", zoom)
    fen._refresh_graphs()
    for nom, g in (("AD", fen._ra_graph), ("DEC", fen._dec_graph),
                   ("temps", fen._time_graph), ("sismo", fen._seismic_graph)):
        (x0, x1), (y0, y1) = g._plot.getViewBox().viewRange()
        ax = g._plot.getAxis('bottom').range
        v(f"zoom {zoom} {nom} : vue [{x0:.0f} ; {x1:.0f}] s",
          abs(x0 + attendu) < 1e-6 and abs(x1) < 1e-6)
        v(f"zoom {zoom} {nom} : graduation [{ax[0]:.0f} ; {ax[1]:.0f}] s",
          abs(ax[0] + attendu) < 1e-6 and abs(ax[1]) < 1e-6)
    xs, _ = fen._ra_graph._data_curve.getData()
    v(f"zoom {zoom} : la courbe AD tient dans la fenetre ({len(xs)} pts)",
      xs[-1] == 0.0 and xs[1] >= -attendu)
    (_, _), (y0, y1) = fen._ra_graph._plot.getViewBox().viewRange()
    v(f"zoom {zoom} : echelle AD a la mesure du signal (±{y1:.2f}\")", y1 < 5)

reglages.set("horizontal_zoom", 1)
fen._refresh_graphs()
reperes = [(l.value(), lab.toPlainText())
           for l, lab in zip(fen._ra_graph._time_fixes, fen._ra_graph._time_fix_labels)
           if l.isVisible()]
v(f"reperes toutes les 30 s dans la fenetre : {reperes}",
  len(reperes) == 4 and all(-120 <= x <= 0 for x, _ in reperes)
  and all(len(txt) == 8 and txt[2] == ':' for _, txt in reperes))

print(f"\n{ok} OK, {ko} ECHEC")
fen.close()
sys.exit(1 if ko else 0)
