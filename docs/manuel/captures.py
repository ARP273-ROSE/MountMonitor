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

RACINE = Path(__file__).resolve().parents[2]
SORTIE = Path(__file__).resolve().parent / "captures"


def attendre(app, delai):
    fin = time.time() + delai
    while time.time() < fin:
        app.processEvents()
        time.sleep(0.02)


def une_langue(langue: str):
    sys.path.insert(0, str(RACINE))
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import reporting
    dossier = Path(tempfile.mkdtemp(prefix="mm-captures-"))
    (dossier / "reglages_rapports.json").write_text('{"envoi_autorise": false}', encoding="utf-8")
    reporting.init(dossier, application="mountmonitor-captures")
    # settings and session logs in the throwaway folder, never the real ones
    from src.config import paths
    paths.dossier_donnees = lambda: dossier
    paths.dossier_journaux = lambda: dossier / "Logs"
    paths.fichier_reglages = lambda: dossier / "mountmonitor_settings.json"
    from src.config.settings import Settings
    Settings().set("language", langue)
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)
    from src.gui.main_window import MainWindow
    w = MainWindow(sim_mode="all")
    w.resize(1500, 900)
    w.show()
    attendre(app, 30.0)                  # simulated mount: data flows by itself
    w.grab().save(str(SORTIE / f"{langue}-principal.png"))
    w.hide()
    print(f"{langue}: screenshot written")


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] in ("en", "fr", "nl"):
        une_langue(sys.argv[1])
        os._exit(0)
    for langue in ("en", "fr", "nl"):
        subprocess.run([sys.executable, "-B", __file__, langue], check=True)


if __name__ == "__main__":
    main()
