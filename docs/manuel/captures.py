"""REAL screenshots of the windows for the manual, in the three languages.

    QT_QPA_PLATFORM=offscreen python docs/manuel/captures.py   (repository root)

Simulation mode (--sim-all): no mount, no hardware, a neutral site. Each
language runs in its own process; settings live in a throwaway folder
(nothing of the user's is read or written), and the report consent is "no".

Written for each language (prefix en-, fr-, nl-):
    principal.png            main window after a few minutes of simulation
    pref-general.png, pref-processing.png, pref-auxiliary.png, pref-misc.png
    fft.png                  FFT window
    alerte.png               the mount-settings alert window
    rapport.png              the night report window of the simulated session
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "captures"
RUN_S = float(os.environ.get("MM_CAPTURE_RUN_S", "180"))


def wait_for(app, delay):
    end = time.time() + delay
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def one_language(language: str):
    sys.path.insert(0, str(ROOT))
    from PyQt6.QtWidgets import QApplication, QTabWidget
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
    settings = Settings()
    settings.set("language", language)
    settings.set("observatory_name", "Example Observatory")
    settings.set("mount_name", "GM1000HPS")
    settings.set("close_at_sunrise", False)        # record in daylight too
    from src.utils.i18n import set_language, T
    set_language(language)
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)
    from src.gui.main_window import MainWindow
    w = MainWindow(sim_mode="all")
    w.resize(1500, 900)
    w.show()

    def shot(widget, name):
        app.processEvents()
        widget.grab().save(str(OUTPUT_DIR / f"{language}-{name}.png"))

    wait_for(app, 8.0)
    w._start_logging()
    wait_for(app, RUN_S)              # simulated mount: data flows by itself
    shot(w, "principal")

    w._show_fft()
    wait_for(app, 5.0)
    if w._fft_window is not None:
        w._fft_window.resize(1000, 640)
        wait_for(app, 2.5)
        shot(w._fft_window, "fft")
        w._fft_window.hide()

    from src.gui.preferences_dialog import PreferencesDialog
    d = PreferencesDialog(w._settings, w)
    d.resize(700, 760)
    d.show()
    tabs = d.findChild(QTabWidget)
    for index, name in enumerate(("general", "processing", "auxiliary", "misc")):
        tabs.setCurrentIndex(index)
        wait_for(app, 0.5)
        shot(d, f"pref-{name}")
    d.reject()

    w._settings.set("mount_alert_popup", True)
    w._mount_alert([
        T("chk_refraction_ko").format(a=T("refraction_not_updating"),
                                      e=T("refraction_continuous")),
        T("chk_corr_ko").format(v="0.120"),
    ])
    box = getattr(w, "_alert_box", None)
    if box is not None:
        wait_for(app, 0.5)
        shot(box, "alerte")
        box.hide()

    dat = getattr(w._file_logger, "dat_path", None)
    w._stop_logging()
    if dat:
        from src.logging_module.log_parser import parse_dat_file
        from src.gui.analysis_dialog import AnalysisDialog
        session = parse_dat_file(Path(dat))
        dialog = AnalysisDialog(session, w)
        dialog.resize(1000, 760)
        dialog.show()
        wait_for(app, 2.0)
        shot(dialog, "rapport")
        dialog.hide()
    w.hide()
    print(f"{language}: screenshots written")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] in ("en", "fr", "nl"):
        one_language(sys.argv[1])
        os._exit(0)
    for language in ("en", "fr", "nl"):
        subprocess.run([sys.executable, "-B", __file__, language], check=True)


if __name__ == "__main__":
    main()
