"""REAL screenshots of the window for the manual, in the three languages.

    python docs/manuel/captures.py          (from the repository root; Xvfb)

Simulation mode (--sim-all): no mount, no hardware. Each language runs in its
own process; settings are only changed in memory (nothing is saved), and the
report consent is "no" in a throwaway folder.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "captures"


def wait_for(app, delay):
    end = time.time() + delay
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def one_language(language: str):
    sys.path.insert(0, str(ROOT))
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import reporting
    folder = Path(tempfile.mkdtemp(prefix="mm-captures-"))
    (folder / "reglages_rapports.json").write_text('{"envoi_autorise": false}', encoding="utf-8")
    reporting.init(folder, application="mountmonitor-captures")
    # settings and session logs in the throwaway folder, never the real ones
    from src.config import paths
    paths.data_folder = lambda: folder
    paths.logs_folder = lambda: folder / "Logs"
    paths.settings_file = lambda: folder / "mountmonitor_settings.json"
    from src.config.settings import Settings
    Settings().set("language", language)
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)
    from src.gui.main_window import MainWindow
    w = MainWindow(sim_mode="all")
    w.resize(1500, 900)
    w.show()
    wait_for(app, 30.0)                  # simulated mount: data flows by itself
    w.grab().save(str(OUTPUT_DIR / f"{language}-principal.png"))
    w.hide()
    print(f"{language}: screenshot written")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] in ("en", "fr", "nl"):
        one_language(sys.argv[1])
        os._exit(0)
    for language in ("en", "fr", "nl"):
        subprocess.run([sys.executable, "-B", __file__, language], check=True)


if __name__ == "__main__":
    main()
