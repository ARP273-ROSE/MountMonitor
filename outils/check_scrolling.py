#!/usr/bin/env python3
"""Checks, on the real window, that the graphs scroll to the present.

Fills the buffers with three chained nights, refreshes, and reads what
pyqtgraph actually displays: the view range AND the tick range.
MainWindow cannot be built under pytest (Qt falls over), hence this script.

    QT_QPA_PLATFORM=offscreen python3 outils/check_scrolling.py
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

ok = failed = 0


def v(name, cond):
    global ok, failed
    print(("  OK    " if cond else "  FAILED ") + name)
    if cond:
        ok += 1
    else:
        failed += 1


settings = Settings()
settings.set("mount_protocol", "simulation")
settings.set("horizontal_zoom", 1)
win = MainWindow()
win._settings = settings
win.resize(1400, 900)

p = win._processor
start = 1790000000.0                  # a real date, in seconds
for k in range(3):                    # three 8 h nights at 1.9 Hz
    for t in np.arange(0, 8 * 3600, 1 / 1.9)[::3] + start + k * 86400:
        p.ra_buffer.append(float(t), 0.05 * np.sin(t / 7))
        p.dec_buffer.append(float(t), 0.1 * np.cos(t / 11))
        p.seismic_buffer.append(float(t), 3 * np.sin(t))
        p.time_diff_buffer.append(float(t), 1.0)

for zoom, expected_value in ((1, 120.0), (5, 24.0)):
    settings.set("horizontal_zoom", zoom)
    win._refresh_graphs_now()
    for name, g in (("RA", win._ra_graph), ("DEC", win._dec_graph),
                   ("time", win._time_graph), ("seismo", win._seismic_graph)):
        (x0, x1), (y0, y1) = g._plot.getViewBox().viewRange()
        ax = g._plot.getAxis('bottom').range
        v(f"zoom {zoom} {name}: view [{x0:.0f} ; {x1:.0f}] s",
          abs(x0 + expected_value) < 1e-6 and abs(x1) < 1e-6)
        v(f"zoom {zoom} {name}: ticks [{ax[0]:.0f} ; {ax[1]:.0f}] s",
          abs(ax[0] + expected_value) < 1e-6 and abs(ax[1]) < 1e-6)
    xs, _ = win._ra_graph._data_curve.getData()
    v(f"zoom {zoom}: the RA curve fits in the window ({len(xs)} pts)",
      xs[-1] == 0.0 and xs[1] >= -expected_value)
    (_, _), (y0, y1) = win._ra_graph._plot.getViewBox().viewRange()
    v(f"zoom {zoom}: RA scale matches the signal (±{y1:.2f}\")", y1 < 5)

settings.set("horizontal_zoom", 1)
win._refresh_graphs_now()
ticks = [(l.value(), lab.toPlainText())
           for l, lab in zip(win._ra_graph._time_fixes, win._ra_graph._time_fix_labels)
           if l.isVisible()]
v(f"marks every 30 s within the window: {ticks}",
  len(ticks) == 4 and all(-120 <= x <= 0 for x, _ in ticks)
  and all(len(txt) == 8 and txt[2] == ':' for _, txt in ticks))

print(f"\n{ok} OK, {failed} FAILED")
win.close()
sys.exit(1 if failed else 0)
