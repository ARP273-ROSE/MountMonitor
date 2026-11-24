#!/usr/bin/env python3
"""MountMonitor - Modern telescope mount monitoring for astrophotography.

MountMonitor 4: successor of MountMonitor v3.40 (Java) by Nicolàs de Hilster,
developed jointly with him.
Now in Python/PyQt6/pyqtgraph with dark astronomy theme.

Usage:
    python main.py                    # Normal mode (requires mount)
    python main.py --sim-mount        # Simulate mount
    python main.py --sim-seismometer  # Simulate seismometer
    python main.py --sim-all          # Simulate everything (demo mode)
"""

import sys
import os
import logging
import argparse
from pathlib import Path

# Ensure the project root is in the path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))


def setup_logging(log_level: str = "INFO"):
    """Configure application logging."""
    from src.config.paths import logs_folder
    log_dir = logs_folder()
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                log_dir / "mountmonitor_app.log",
                maxBytes=500 * 1024,  # 500KB
                backupCount=3,
                encoding='utf-8',
            ),
        ],
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MountMonitor - Real-time telescope mount monitoring"
    )
    parser.add_argument(
        '--sim-mount', action='store_true',
        help='Simulate mount connection (for testing)'
    )
    parser.add_argument(
        '--sim-seismometer', action='store_true',
        help='Simulate seismometer data (for testing)'
    )
    parser.add_argument(
        '--sim-all', action='store_true',
        help='Simulate everything (demo mode)'
    )
    parser.add_argument(
        '--connect', action='store_true',
        help='Connect to the mount at launch and retry until it answers '
             '(unattended start; recording follows the arming setting)'
    )
    parser.add_argument(
        '--log-level', default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    return parser.parse_args()


_NATIVE_CRASH_FILE = "_crash_natif.log"
_watchdog = None


def _init_reporting(app):
    """Set up incident reporting, and collect those from the previous run.

    Three things happen here:

      - `relever_crash_natif` reads the trace left by a crash that raised no
        Python exception — a segmentation fault in Qt, for example. Without
        it, that kind of death leaves nothing at all;
      - the queue is resumed: a report written while the house had no
        network goes out on the next launch;
      - the exception handler sends whatever was not caught.

    Everything depends on consent, asked once, after the window opens: until
    it has been given, nothing leaves the machine.
    """
    global _watchdog
    try:
        import reporting
        from src.config.paths import data_folder
    except Exception:
        logging.getLogger(__name__).debug("Reporting unavailable", exc_info=True)
        return

    data = data_folder()
    reporting.init(data)

    # Trace of crashes without an exception: written continuously to a file,
    # collected at the next start.
    native_path = data / _NATIVE_CRASH_FILE
    # Collect the previous session's trace BEFORE reopening the file:
    # opening it for writing empties it, and the trace of a native crash was
    # lost before being read.
    try:
        reporting.relever_crash_natif(native_path)
        reporting.reprendre_file_en_fond()
    except Exception:
        logging.getLogger(__name__).debug("Report queue not resumed", exc_info=True)

    try:
        import faulthandler
        _init_reporting._file = open(native_path, 'w', encoding='utf-8')
        faulthandler.enable(file=_init_reporting._file, all_threads=True)
    except Exception:
        logging.getLogger(__name__).debug("faulthandler unavailable", exc_info=True)

    # Freeze watchdog: a timer beats on the GUI thread, a background thread
    # watches the clock. If the beat stops, the window is frozen, and the GUI
    # thread's stack then shows which operation was not moved off it.
    # Without this a freeze leaves no trace: the app gets killed and nothing
    # can be said about it.
    # The heartbeat is essential: without it, the watchdog never sees the GUI
    # thread go by and concludes it froze after ten seconds, on every launch.
    # That is what happened from 1.8.1 to 1.13.0: six false alerts reported
    # from a machine where everything was fine, with as the only trace a
    # stack showing the GUI thread idle in app.exec().
    try:
        from PyQt6.QtCore import QTimer
        _watchdog = reporting.Vigie(seuil=10.0, periode=2.0)
        _watchdog.demarrer()
        _heartbeat = QTimer(app)
        _heartbeat.timeout.connect(_watchdog.battre)
        _heartbeat.start(2000)
        app._watchdog_heartbeat = _heartbeat   # otherwise the timer is garbage-collected
    except Exception:
        logging.getLogger(__name__).debug("Watchdog not started", exc_info=True)


def _ask_report_consent(window):
    """Ask the question once only, then report the start."""
    try:
        import reporting
    except Exception:
        return
    try:
        if reporting.consentement() is None:
            from PyQt6.QtWidgets import QMessageBox
            box = QMessageBox(window)
            box.setWindowTitle("MountMonitor")
            box.setIcon(QMessageBox.Icon.Question)
            # Asked in ONE language -- the one the user reads. It used to be
            # French and English stacked in the same box, which meant the
            # Dutch user got neither and everyone else read it twice. The
            # window language is already set by the time this is shown.
            from src.utils.i18n import T
            box.setText(T("consent_question"))
            box.setInformativeText(T("consent_detail"))
            yes_btn = box.addButton(T("consent_oui"),
                                  QMessageBox.ButtonRole.AcceptRole)
            box.addButton(T("consent_non"),
                            QMessageBox.ButtonRole.RejectRole)
            box.exec()
            reporting.definir_consentement(box.clickedButton() is yes_btn)
        reporting.signaler_demarrage()
    except Exception:
        logging.getLogger(__name__).debug("Consent not requested", exc_info=True)


def updater_is_installed() -> bool:
    try:
        import updater
        return bool(updater.is_packaged())
    except Exception:
        return False


def _early_language():
    """Apply the user's language before any dialog can appear.

    The crash dialog is shown at line ~246, the main window is built at
    ~319: without this, a crash report asked its question in the
    auto-detected language rather than the one the user chose.
    """
    try:
        from src.config.settings import Settings
        from src.utils.i18n import set_language
        set_language(Settings().get("language"))
    except Exception:
        pass


def _self_check() -> int:
    """--check : the application and its dependencies load.

    Run by the package builds (Windows, macOS, Linux) with the embedded
    interpreter. No window, no mount, nothing written next to the program.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv[:1])
        import interface_kit
        import reporting  # noqa: F401
        import updater  # noqa: F401
        import kit_aide  # noqa: F401
        import pyqtgraph  # noqa: F401
        import numpy  # noqa: F401
        from src.gui import main_window  # noqa: F401
        from src.gui.theme import apply_dark_theme
        apply_dark_theme(app)
        assert app.style().name().lower() == 'fusion' or app.styleSheet()
        del app, interface_kit
    except Exception as exc:
        print(f"MountMonitor : ECHEC / FAILED -- {type(exc).__name__}: {exc}")
        return 1
    print("MountMonitor : OK")
    return 0


def main():
    """Application entry point."""
    if "--check" in sys.argv[1:]:
        return _self_check()

    # Need to import logging.handlers before setup
    import logging.handlers

    args = parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("MountMonitor starting...")

    _early_language()

    # Determine simulation mode
    if args.sim_all:
        sim_mode = "all"
    elif args.sim_mount:
        sim_mode = "mount"
    elif args.sim_seismometer:
        sim_mode = "seismometer"
    else:
        sim_mode = "none"

    if sim_mode != "none":
        logger.info(f"Simulation mode: {sim_mode}")

    # Create Qt application
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("MountMonitor")
    app.setOrganizationName("ARP273")

    # One instance at a time. Two copies querying the same mount on the same
    # LX200 port means two interleaved command streams: the mount answers
    # one with what the other was waiting for.
    from PyQt6.QtCore import QLockFile, QDir
    _lock_file = QLockFile(str(Path(QDir.tempPath()) / 'mountmonitor.lock'))
    _lock_file.setStaleLockTime(30000)
    # Relaunched by an update or a language change: the old instance may
    # still be closing (night report, poller): wait for it, up to a minute.
    _wait_ms = 60000 if os.environ.pop('KIT_RELANCE', None) else 200
    if not _lock_file.tryLock(_wait_ms):
        from PyQt6.QtWidgets import QMessageBox
        from src.utils.i18n import T
        QMessageBox.information(None, "MountMonitor", T("deja_ouvert"))
        return 0
    app._instance_lock = _lock_file

    # Named mutex, visible to the installer (AppMutex in installer.iss).
    # QLockFile is only visible from Qt: without this one, installing a new
    # version over the running application does not replace the files in
    # use, yet still ends by announcing "finished".
    if sys.platform == 'win32':
        try:
            import ctypes
            app._installer_mutex = ctypes.windll.kernel32.CreateMutexW(
                None, False, 'MountMonitorEnCours')
        except Exception:
            logger.debug("Named mutex not created", exc_info=True)

    # Incident reporting. Initialised before everything else: what interests
    # us most is precisely the starts that never complete.
    _init_reporting(app)

    # Apply dark theme
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)
    # Real, complete file dialog on Linux (sidebar, tree), the portal's
    # "native" dialog often being stripped down there (shared kit).
    try:
        import interface_kit
        interface_kit.installer_dialogues_fichiers()
    except Exception:
        logger.debug("Kit file dialogs not installed", exc_info=True)

    # Install crash reporter
    from src.logging_module.crash_reporter import CrashReporter
    from src.config.paths import data_folder
    crash_reporter = CrashReporter(data_folder())
    crash_reporter.install()

    # Check for previous crash — offer to report on GitHub.
    # Not on an unattended start (--connect): a modal box here would hold the
    # window -- and the connection -- until someone clicks. The report is kept
    # and offered at the next ordinary launch.
    if args.connect and crash_reporter.has_crash_report():
        logger.warning("Previous crash report kept: --connect start, no dialog")
    elif crash_reporter.has_crash_report():
        report = crash_reporter.get_crash_report()
        if report:
            from PyQt6.QtWidgets import QMessageBox
            from src.logging_module.crash_reporter import anonymize_path, GITHUB_REPO

            exc_type = report.get('exception_type', 'Unknown')
            exc_msg = anonymize_path(report.get('exception_message', ''))

            from src.utils.i18n import T
            msg = QMessageBox()
            msg.setWindowTitle(T("crash_titre"))
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(
                f"{T('crash_texte')}\n\n"
                f"{T('crash_erreur')}: {exc_type}\n{exc_msg}"
            )
            msg.setInformativeText(
                f"{T('crash_question')}\n\n{T('crash_anonyme')}"
            )

            send_btn = msg.addButton(
                T("crash_signaler"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            dismiss_btn = msg.addButton(
                T("crash_ignorer"),
                QMessageBox.ButtonRole.RejectRole,
            )
            msg.exec()

            if msg.clickedButton() == send_btn:
                import webbrowser
                from urllib.parse import quote
                body = crash_reporter.format_github_issue(report)
                title = quote(f"Crash: {exc_type}", safe='')
                encoded_body = quote(body, safe='')
                url = (
                    f"https://github.com/{GITHUB_REPO}/issues/new"
                    f"?title={title}&body={encoded_body}"
                )
                webbrowser.open(url)

        crash_reporter.clear_crash_report()

    # Machine inventory: in a background thread, after the window is shown.
    #
    # On Windows it relies on four `wmic` calls, each with up to five seconds
    # of waiting. Run here, before the window was created, they delayed the
    # opening by as much — black screen, not a word. And `wmic` has been
    # removed from recent Windows versions: on those machines the four calls
    # fail, after costing the launch of four processes.
    #
    # The result only feeds one log line. It has no reason to hold up the
    # display.
    def _take_inventory():
        try:
            from src.utils.hardware_detect import detect_hardware
            hw = detect_hardware()
            logger.info(f"Hardware: {hw.cpu_name}, {hw.cpu_cores_physical} cores, "
                        f"{hw.ram_total_mb}MB RAM, GPU: {hw.gpu_name}")
        except Exception:
            logger.debug("Machine inventory unavailable", exc_info=True)

    import threading
    threading.Thread(target=_take_inventory, daemon=True,
                     name='inventaire-machine').start()

    # Create and show main window
    from src.gui.main_window import MainWindow
    window = MainWindow(sim_mode=sim_mode, auto_connect=args.connect)
    window.show()

    # Offer desktop shortcut on first launch -- from source only: the
    # installed application already has the installer's shortcuts.
    if not updater_is_installed():
        from src.config.settings import Settings
        _settings = Settings()
        from shortcut_helper import offer_shortcut
        offer_shortcut("MountMonitor", "main.py", "logo.ico",
                       get_config=lambda k: _settings.get(k),
                       set_config=lambda k, v: (_settings.set(k, v), _settings.save()))

    _ask_report_consent(window)

    logger.info("MountMonitor ready")
    code = app.exec()

    # Immediate exit, without tearing down the interpreter.
    #
    # Once the loop ends, Python destroys its objects in an order Qt cannot
    # handle: the GUI library is freed while objects still refer to it, and
    # the process dies of a segmentation fault. On Windows this shows up as
    # "the program has stopped working" when the window is closed — reported
    # as a crash, although all the work is done. Session files are closed by
    # the window itself before getting there.
    try:
        if _watchdog is not None:
            _watchdog.arreter()
    except Exception:
        pass
    try:
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    sys.exit(main())
