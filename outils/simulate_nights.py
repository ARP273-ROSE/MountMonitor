#!/usr/bin/env python3
"""Replays three nights in a row, to check that the program chains them.

This scenario needs a real window: instantiating it under pytest brings Qt
down, so it lives here rather than in the test suite. The suite keeps the
guard that prevents the loop (test_daylight_guard_prevents_loop).

    QT_QPA_PLATFORM=offscreen python3 outils/simulate_nights.py
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
for key in ("autostart_on_tracking", "pause_when_not_tracking", "close_at_sunrise"):
    settings.set(key, True)

w = MainWindow()
w._settings = settings
w._site = lambda: (43.9317, 5.7122, 650)   # Observatoire de Haute-Provence
w._connected = True
w._prev_mount_status = MountStatus.PARKED

sun = [+10.0]
E.sun_altitude = lambda *a, **k: sun[0]

w._arm()
v("day 0: armed, and does not record in broad daylight",
  w._logging_armed and not w._logging_active)

files = []
for night in (1, 2, 3):
    print(f"--- night {night} ---")
    sun[0] = -20.0
    w._on_status_changed(MountStatus.TRACKING)
    v("  in the evening: recording", w._writes_samples())
    file = str(w._file_logger.dat_path)
    files.append(file)

    w._on_status_changed(MountStatus.PARKED)
    w._pause()
    v("  park in the middle of the night: paused, session open",
      w._logging_paused and w._logging_active)
    w._on_status_changed(MountStatus.TRACKING)
    v("  resumes in the SAME file", str(w._file_logger.dat_path) == file)

    w._watch_dawn()
    sun[0] = +10.0
    w._watch_dawn()
    v("  sunrise: closed and report written", not w._logging_active)
    v("  and re-arms for the evening", w._logging_armed)

    w._on_status_changed(MountStatus.TRACKING)
    v("  the mount tracks in broad daylight: nothing starts",
      not w._logging_active and w._logging_armed)
    time.sleep(1.1)          # so that the file timestamp changes

print("--- summary ---")
v("three distinct files, one per night", len(set(files)) == 3)
for f in files:
    print("     ", os.path.basename(f))
v("still armed at the end", w._logging_armed and not w._logging_active)
print()
print(f"RESULT: {ok} OK, {failed} FAILED")
sys.exit(1 if failed else 0)
