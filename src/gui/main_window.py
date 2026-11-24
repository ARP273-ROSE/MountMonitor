"""Main window for MountMonitor.

Assembles all components: graphs, status panel, menus, toolbar.
Manages the connection lifecycle and data flow.
"""

import os
import sys
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QPushButton, QLabel, QMessageBox,
    QApplication, QStatusBar, QFileDialog,
    QDialog, QTextBrowser, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QFont, QIcon, QKeySequence

from ..core.axial import axial_speeds, RA_DEFAULT_SPEED
from .graph_widgets import (TrackingGraph, TimeGraph, SeismicGraph, AxialGraph,
                            cut_to_present, window_width,
                            shown_span, span_name, clock_drift,
                            SPANS_S)
from .fft_window import FFTWindow
from .analysis_dialog import AnalysisDialog, save_report
from .log10m_dialog import Log10mAnalysisDialog
from .status_panel import StatusPanel
from .preferences_dialog import PreferencesDialog
from .theme import Colors
from ..config.settings import Settings
from ..core.mount_connection import MountConnection
from ..core.lx200_protocol import LX200Connection
from ..core.lx200_serial import LX200SerialConnection
from ..core.ascom_connection import ASCOMConnection
from ..core.data_processor import DataProcessor, deviations_from_median
from ..core.poller import MountPoller
from ..core.ntp_client import NTPClient
from ..core.seismometer import Seismometer
from ..simulation.sim_mount import SimulatedMount
from ..simulation.sim_seismometer import SimulatedSeismometer
from ..logging_module.file_logger import FileLogger
from ..logging_module.log_parser import parse_session, list_log_sessions
from ..logging_module.crash_reporter import CrashReporter, anonymize_path, GITHUB_REPO
from ..models.mount_data import MountSample, MountStatus, SessionInfo, ConnectionProtocol
from ..utils.i18n import T, set_language, get_language, LANGUAGES
from ..utils.coordinates import format_ra, format_dec
# Updating goes through the kit's shared module, at the root: it fetches
# the application archive published in the public distribution
# repository. The old mechanism downloaded the zipball of the code
# repository, which stayed private: the API answered 404 and the update
# never triggered for anyone.
import updater

logger = logging.getLogger(__name__)


def _read_version() -> str:
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "1.0.0"



class EndOfNightJob(QThread):
    """Reads a finished session ONCE and writes its three reports, off the GUI.

    At dawn and at every park the window used to parse the .dat twice and
    write the reports on the GUI thread: about 7 s frozen for a 10 Hz night
    here, 25 s or more on a small mini-PC (a minute and a half for a long
    night), with the freeze watchdog firing. One thread is enough on two
    cores; the session comes back by a signal and the window is built then.
    """
    completed = pyqtSignal(str, object, object)     # dat path, session or None, main report path

    def __init__(self, dat_path, language: str, write: bool, parent=None):
        super().__init__(parent)
        self._path = str(dat_path)
        self._ui_language = language
        self._write = write

    def run(self):
        session, output = None, None
        try:
            session = parse_session(Path(self._path))
            if self._write:
                output = save_report(self._path, self._ui_language, session=session)
        except Exception as e:
            logger.error(f"End-of-night processing failed: {e}")
        self.completed.emit(self._path, session, output)

class MainWindow(QMainWindow):
    """Main application window."""

    # Return path from the thread that queries GitHub to the GUI thread.
    #
    # `object` and not `dict`: declared as `dict`, PyQt would copy the
    # payload field by field. Above all, the result goes through a signal
    # and never through QTimer.singleShot — a timer created in a thread
    # without an event loop never fires, and the answer would be lost
    # without the slightest message.
    update_found = pyqtSignal(object)
    # The seismometer reads in its own thread; its data crosses over by this
    # queued signal. It used to call _on_seismic_data directly from that
    # thread, writing the .sei/.dat files the GUI thread was writing too.
    seismic_received = pyqtSignal(float, object)
    fft_computed = pyqtSignal(object)        # spectra from the FFT thread
    update_progress = pyqtSignal(int)
    update_installed = pyqtSignal(bool, str)

    def __init__(self, sim_mode: str = "none", auto_connect: bool = False):
        """Initialize main window.

        Args:
            sim_mode: "none", "mount", "seismometer", or "all"
            auto_connect: connect at launch and retry until the mount answers
                (--connect; the "connect_on_launch" setting does the same)
        """
        super().__init__()
        self._version = _read_version()
        self._sim_mode = sim_mode
        self._settings = Settings()
        self._processor = DataProcessor()
        self._connection: Optional[MountConnection] = None
        self._poller: Optional[MountPoller] = None
        self._connecting = False
        # Pollers whose thread has not ended yet (stuck in a driver): kept
        # referenced, a QThread destroyed while running aborts the process.
        self._finishing_pollers: list = []
        self._ntp_client: Optional[NTPClient] = None
        self._seismometer = None
        self._file_logger = FileLogger()
        self._fft_window: Optional[FFTWindow] = None
        self._connected = False
        self._logging_active = False
        # Armed: the button has been pressed but nothing is being written yet.
        # The mount can be connected hours before the night starts, and those
        # hours are dead weight in the .dat and noise in the night report.
        self._logging_armed = False
        self._park_timer = None
        # Suspended: the session stays OPEN and the file stays the same, but
        # samples stop being written. A mount parked for three hours at 2 Hz
        # would otherwise lay down 20,000 samples of nothing, and closing the
        # session instead would split one night across two files and two
        # reports. The night is defined by the Sun, not by a park.
        self._logging_paused = False
        self._night_seen = False          # the Sun went below the horizon while recording
        # Path of the .dat that THIS run closed. While it is None, there is
        # nothing to analyse automatically.
        self._last_session = None
        self._analysis_window = None
        self._analysed_session = None
        self._dawn_timer = None
        self._arm_timer = None
        self._night_jobs: dict = {}
        self._analysis_requested: set = set()
        self._read_session = None
        # Site as the mount reports it, when it does. Plenty of setups never
        # push their site to the mount -- hence the preference fallback.
        self._mount_site = None
        self._mount_info = {}
        self._prev_mount_status = MountStatus.UNKNOWN

        # Apply language setting
        lang = self._settings.get("language")
        set_language(lang)

        # Setup UI
        self._setup_window()
        self._create_menus()
        self._create_toolbar()
        self._create_central_widget()
        self._create_statusbar()

        # Refresh timer for graph updates — 4 fps is sufficient for monitoring
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_graphs)
        # 4 fps, 2 fps from the start on a small PC; adapted while running.
        self._cadence_min = 1 if (os.cpu_count() or 2) <= 4 else 0
        self._refresh_timer.setInterval(self.RATES_MS[self._cadence_min])

        # FFT timer (slower)
        self._fft_timer = QTimer()
        self._fft_timer.timeout.connect(self._update_fft)
        self.fft_computed.connect(self._on_fft_computed)
        self._fft_timer.setInterval(2000)  # Every 2 seconds

        # Update check, in the background, at startup.
        self.update_found.connect(self._on_update_found)
        self.seismic_received.connect(self._on_seismic_data)
        self.update_progress.connect(self._on_update_progress)
        self.update_installed.connect(self._on_update_installed)
        QTimer.singleShot(3000, self._check_updates_silent)

        # Auto-connect in simulation mode
        self._connect_attempts = 0
        self._auto_connect_active = False
        if sim_mode != "none":
            QTimer.singleShot(500, self._connect)
        elif auto_connect or self._settings.get("connect_on_launch"):
            # Unattended start of the observatory PC: the window comes up
            # before the control box has finished booting, so the first
            # attempt often fails. Keep trying until it answers.
            self._auto_connect_active = True
            QTimer.singleShot(1500, self._auto_connect)

        self._apply_horizontal_zoom(1)
        self._set_vertical_zoom(self._settings.get("vertical_zoom_mode") or "data",
                                save=False)
        self._wire_graph_menus()
        self._arm_periodic_check()

        self._update_title()

    def _setup_window(self):
        """Configure the main window."""
        self.setWindowTitle(f"MountMonitor v{self._version}")

        # Set window icon
        logo_path = Path(__file__).resolve().parent.parent.parent / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        w = self._settings.get("window_width")
        h = self._settings.get("window_height")
        x = self._settings.get("window_x")
        y = self._settings.get("window_y")
        self.resize(w, h)
        if x > 0 and y > 0:
            self.move(x, y)
        self.setMinimumSize(800, 500)

    def _create_menus(self):
        """Create menu bar.

        File holds everything about the session and the application (connect,
        recording files, logs to replay, settings, quit); View what is shown
        and its resets. A one-entry Edit menu and a Reset menu mixing resets
        with file actions went away in 4.5.7."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(T("menu_file"))

        connect_action = QAction(T("btn_connect"), self)
        connect_action.setShortcut(QKeySequence("Ctrl+K"))
        connect_action.setToolTip(T("tt_connect"))
        connect_action.triggered.connect(self._connect)
        file_menu.addAction(connect_action)
        self._connect_action = connect_action

        disconnect_action = QAction(T("btn_disconnect"), self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+D"))
        disconnect_action.setToolTip(T("tt_disconnect"))
        disconnect_action.triggered.connect(self._disconnect)
        disconnect_action.setEnabled(False)
        file_menu.addAction(disconnect_action)
        self._disconnect_action = disconnect_action

        file_menu.addSeparator()

        for label, slot in [
            (T("reset_new_files"), self._new_log_files),
            (T("dump_graphs_action"), self._dump_graphs),
        ]:
            action = QAction(label, self)
            action.triggered.connect(slot)
            file_menu.addAction(action)

        file_menu.addSeparator()

        open_log_action = QAction(T("menu_open_log"), self)
        open_log_action.setShortcut(QKeySequence("Ctrl+O"))
        open_log_action.setToolTip(T("tt_open_log"))
        open_log_action.triggered.connect(self._open_log_file)
        file_menu.addAction(open_log_action)

        open_log10m_action = QAction(T("menu_open_log10m"), self)
        open_log10m_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_log10m_action.setToolTip(T("tt_open_log10m"))
        open_log10m_action.triggered.connect(self._open_log10m_files)
        file_menu.addAction(open_log10m_action)

        file_menu.addSeparator()

        pref_action = QAction(T("menu_preferences"), self)
        pref_action.setShortcut(QKeySequence("Ctrl+,"))
        pref_action.setToolTip(T("tt_prefs"))
        pref_action.triggered.connect(self._show_preferences)
        file_menu.addAction(pref_action)

        shortcut_action = QAction(T("menu_create_shortcut"), self)
        shortcut_action.triggered.connect(self._create_desktop_shortcut)
        file_menu.addAction(shortcut_action)

        file_menu.addSeparator()

        quit_action = QAction(T("menu_quit"), self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu(T("menu_view"))

        # Time span and vertical scale: same submenus as the right click on
        # a graph (_menu_graphe), checked on the current choice.
        self._fill_span_menu(view_menu.addMenu(T("time_span")))
        self._fill_vertical_menu(view_menu.addMenu(T("vertical_zoom")))

        view_menu.addSeparator()

        fft_action = QAction(T("fft_title"), self)
        fft_action.setShortcut(QKeySequence("Ctrl+F"))
        fft_action.setToolTip(T("tt_fft_win"))
        fft_action.triggered.connect(self._show_fft)
        view_menu.addAction(fft_action)

        view_menu.addSeparator()

        # Resets: what is displayed (min/max, graph buffers).
        reset_menu = view_menu.addMenu(T("menu_reset"))
        for label, slot in [
            (T("reset_minmax"), self._reset_minmax),
            (T("reset_buffers"), self._reset_buffers),
            (T("reset_both"), self._reset_both),
        ]:
            action = QAction(label, self)
            action.triggered.connect(slot)
            reset_menu.addAction(action)

        # Language menu.
        #
        # This lived in Preferences, inside the "Layout" group -- nobody looks
        # for their language under layout, so in practice the option did not
        # exist. It is a top-level menu now, and every entry is written in its
        # OWN language: someone who landed in the wrong language cannot read
        # the current one to find their way out.
        lang_menu = menubar.addMenu(T("menu_language"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        current_lang = self._settings.get("language") or "auto"
        for code, caption in [("auto", T("lang_auto"))] + list(LANGUAGES.items()):
            act = QAction(caption, self)
            act.setCheckable(True)
            act.setChecked(code == current_lang)
            act.setData(code)
            act.triggered.connect(lambda _checked, c=code: self._choose_language(c))
            self._lang_group.addAction(act)
            lang_menu.addAction(act)
            if code == "auto":
                lang_menu.addSeparator()

        # Help menu
        help_menu = menubar.addMenu(T("menu_help"))

        help_action = QAction(T("menu_help_contents"), self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self._show_help)
        help_menu.addAction(help_action)

        manual_action = QAction(T("menu_manual"), self)
        manual_action.setToolTip(T("tt_manual"))
        manual_action.triggered.connect(self._open_manual)
        help_menu.addAction(manual_action)

        online_help_action = QAction(T("menu_online_help"), self)
        online_help_action.setToolTip(T("tt_doc_online"))
        online_help_action.triggered.connect(self._show_online_help)
        help_menu.addAction(online_help_action)

        help_menu.addSeparator()

        about_action = QAction(T("menu_about"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        bug_action = QAction(T("menu_report_bug"), self)
        bug_action.setToolTip(T("tt_bug_github"))
        bug_action.triggered.connect(self._report_bug)
        help_menu.addAction(bug_action)

        # Shared kit: reporting to the collection point and the consent
        # box for automatic reports (the manual and the updates already
        # have their entries above and below; consent is asked by main.py
        # on first launch).
        try:
            from kit_aide import AideKit
            from src.config.paths import logs_folder
            self._kit_help = AideKit(
                self, self._version, get_language, [], nom_fil="mountmonitor",
                etat=lambda: {"langue": get_language(), "simulation": self._sim_mode},
                journal=logs_folder() / "mountmonitor_app.log")
            self._kit_help.remplir_menu(help_menu, avec_manuel=False, avec_maj=False)
        except Exception:
            logger.debug("Kit menu unavailable", exc_info=True)

        update_action = QAction(T("menu_check_updates"), self)
        update_action.setToolTip(T("tt_check_upd"))
        update_action.triggered.connect(self._check_updates_manual)
        help_menu.addAction(update_action)

    def _create_toolbar(self):
        """Create toolbar with main action buttons."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())
        self.addToolBar(toolbar)

        self._btn_connect = QPushButton(T("btn_connect"))
        self._btn_connect.setToolTip(T("tt_connect"))
        self._btn_connect.clicked.connect(self._toggle_connection)
        toolbar.addWidget(self._btn_connect)

        self._btn_logging = QPushButton(T("btn_start_log"))
        self._btn_logging.setToolTip(T("tt_start_logging"))
        self._btn_logging.setEnabled(False)
        self._btn_logging.clicked.connect(self._toggle_logging)
        # Right click: the automatic options, where they are needed. In the
        # Preferences alone they went unnoticed (a user observing the Sun by
        # day did not know recording could be allowed in daylight).
        self._btn_logging.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_logging.customContextMenuRequested.connect(self._logging_menu)
        toolbar.addWidget(self._btn_logging)

        toolbar.addSeparator()

        btn_fft = QPushButton("FFT")
        btn_fft.setToolTip(T("tt_fft"))
        btn_fft.clicked.connect(self._show_fft)
        toolbar.addWidget(btn_fft)
        # Settings: File menu only (Ctrl+,), no second copy in the toolbar.

    def _create_central_widget(self):
        """Create the central widget with graphs and status panel."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Left: graphs stacked vertically
        graph_splitter = QSplitter(Qt.Orientation.Vertical)
        self._graph_splitter = graph_splitter

        self._ra_graph = TrackingGraph(
            T("right_ascension"), Colors.GRAPH_RA
        )
        self._dec_graph = TrackingGraph(
            T("declination"), Colors.GRAPH_DEC
        )
        for graph in (self._ra_graph, self._dec_graph):
            graph.set_smooth(self._settings.get("smooth_curves"))
        self._time_graph = TimeGraph()
        self._seismic_graph = SeismicGraph()
        self._axial_graph = AxialGraph()

        graph_splitter.addWidget(self._ra_graph)
        graph_splitter.addWidget(self._dec_graph)
        graph_splitter.addWidget(self._time_graph)

        # Axial graph: always in the splitter, shown when the mode is on
        # (hidden when the protocol cannot read the axes, see _axial_mode)
        graph_splitter.addWidget(self._axial_graph)
        self._axial_graph.setVisible(self._axial_mode() != "off")

        # Show seismic graph only if enabled
        if self._settings.get("seismometer_enabled") or self._sim_mode in ("all", "seismometer"):
            graph_splitter.addWidget(self._seismic_graph)

        # Right: status panel
        self._status_panel = StatusPanel(max_lines=self._settings.get("history_lines"))

        # Main horizontal splitter
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter = h_splitter
        h_splitter.addWidget(graph_splitter)
        h_splitter.addWidget(self._status_panel)

        # Set proportions (graphs take ~75%, status ~25%)
        ratio = self._settings.get("graph_textbox_ratio")
        h_splitter.setSizes([ratio * 200, 200])

        main_layout.addWidget(h_splitter)

        # Panel sizes survive a restart. The read-me has long promised
        # "persistent layout"; the splitters were in fact rebuilt at their
        # default proportions every time, so every resize was lost on close.
        self._restore_panels()

    def _create_statusbar(self):
        """Create status bar."""
        self._statusbar = self.statusBar()
        self._statusbar_label = QLabel("")
        self._statusbar.addPermanentWidget(self._statusbar_label)

    def _update_title(self):
        """Update window title with connection info and date."""
        date_str = datetime.now().strftime("%d/%m/%Y")
        title = f"MountMonitor (v{self._version}) "
        if self._connected and self._processor:
            freq = self._processor.actual_frequency
            if self._sim_mode != "none":
                title += f"{freq:.1f}Hz simulation mode"
            else:
                protocol = self._settings.get("mount_protocol")
                if protocol == "lx200":
                    ip = self._settings.get("mount_ip")
                    port = self._settings.get("mount_port")
                    title += f"{freq:.1f}Hz on TCP/IP {ip}:{port}"
                elif protocol == "lx200_serial":
                    serial_port = self._settings.get("serial_port")
                    title += f"{freq:.1f}Hz on {serial_port}"
                elif protocol == "ascom":
                    driver = self._settings.get("ascom_driver") or "ASCOM"
                    title += f"{freq:.1f}Hz via {driver}"
                else:
                    title += f"{freq:.1f}Hz {protocol}"
        title += f" ({date_str})"
        self.setWindowTitle(title)

    # ── Connection management ────────────────────────────────────

    def _toggle_connection(self):
        # A click by the user ends the automatic attempts, whatever its effect.
        self._auto_connect_active = False
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _auto_connect(self):
        """Connect at launch; on failure, try again every connect_retry_s s.

        Stops at the first success, or as soon as the user takes over (click on
        Connect/Disconnect). Never opens a dialog: on an unattended start nobody
        is there to answer it."""
        if not self._auto_connect_active or self._connected:
            self._auto_connect_active = False
            return
        protocol = self._settings.get("mount_protocol")
        if protocol == "ascom" and not self._settings.get("ascom_driver"):
            # _connect would open the ASCOM Chooser and wait for a click.
            self._status_panel.add_message(T("no_ascom_driver"), Colors.STATUS_ERROR)
            self._auto_connect_active = False
            return
        if protocol == "lx200_serial" and not self._settings.get("serial_port"):
            self._status_panel.add_message(T("no_serial_port"), Colors.STATUS_ERROR)
            self._auto_connect_active = False
            return
        self._connect_attempts += 1
        self._connect()      # the answer comes back in _on_connect_result

    def _reschedule_auto_connect(self):
        if not self._auto_connect_active or self._connected:
            self._auto_connect_active = False
            return
        raw_text = self._settings.get("connect_retry_s")
        delay = max(5, int(30 if raw_text is None else raw_text))
        self._status_panel.add_message(
            T("auto_connect_retry").format(n=self._connect_attempts, s=delay),
            Colors.STATUS_WARNING)
        QTimer.singleShot(delay * 1000, self._auto_connect)

    def _connect(self):
        """Connect to the mount.

        The connection is opened in the poller thread: an unreachable mount
        (5 s timeout) or a slow ASCOM driver used to freeze the window, every
        30 s while --connect waited for the mount. The rest of the start-up
        happens in _on_connect_result."""
        if self._connected or self._connecting:
            return
        # The previous poller may still be ending (driver busy): never two
        # threads on the same mount. Retried shortly, for 10 s at most.
        busy = [p for p in self._finishing_pollers if p.isRunning()]
        if busy:
            tries = getattr(self, "_connect_waits", 0)
            if tries < 20:
                self._connect_waits = tries + 1
                QTimer.singleShot(500, self._connect)
                return
            logger.warning("Previous poller still running; connecting anyway")
        self._connect_waits = 0

        protocol = self._settings.get("mount_protocol")

        # Create appropriate connection
        if self._sim_mode in ("mount", "all") or protocol == "simulation":
            self._connection = SimulatedMount()
            self._status_panel.add_message(T("sim_mount"), Colors.STATUS_WARNING)
        elif protocol == "lx200":
            self._connection = LX200Connection(
                host=self._settings.get("mount_ip"),
                port=self._settings.get("mount_port"),
            )
        elif protocol == "lx200_serial":
            serial_port = self._settings.get("serial_port")
            if not serial_port:
                self._status_panel.add_message(
                    T("no_serial_port"), Colors.STATUS_ERROR,
                )
                return
            self._connection = LX200SerialConnection(
                port=serial_port,
                baudrate=self._settings.get("serial_baudrate") or 9600)
        elif protocol == "ascom":
            driver_id = self._settings.get("ascom_driver")
            if not driver_id:
                # Auto-open ASCOM Chooser if no driver configured
                from .preferences_dialog import _ascom_choose
                driver_id = _ascom_choose("")
                if not driver_id:
                    self._status_panel.add_message(
                        T("no_ascom_driver"), Colors.STATUS_ERROR,
                    )
                    return
                self._settings.set("ascom_driver", driver_id)
                self._save_settings()
            self._connection = ASCOMConnection(
                driver_id=driver_id,
                tenmicron_commands=bool(self._settings.get("ascom_10micron_commands")))
        else:
            self._status_panel.add_message(
                f"{T('protocol_not_impl')}: {protocol}", Colors.STATUS_ERROR
            )
            return

        self._status_panel.add_message(T("connecting"))
        self._poller = MountPoller(
            self._connection, self._processor,
            frequency_hz=self._settings.get("polling_frequency_hz"),
        )
        self._poller.set_axial_enabled(self._axial_mode() != "off")
        self._poller.set_log_tracking_only(self._settings.get("log_mode") == "tracking_only")
        self._poller.set_delay_after_slew(self._settings.get("delay_after_slew_seconds"))
        self._poller.connect_result.connect(self._on_connect_result)
        self._poller.request_done.connect(self._on_request_done)
        # Every signal is wired BEFORE the thread starts: the mount info is
        # emitted right after the connection and would otherwise be lost.
        self._poller.sample_ready.connect(self._on_sample)
        self._poller.time_sample_ready.connect(self._on_time_sample)
        self._poller.status_changed.connect(self._on_status_changed)
        self._poller.connection_lost.connect(self._on_connection_lost)
        self._poller.connection_restored.connect(self._on_connection_restored)
        self._poller.log_message.connect(self._on_log_message)
        self._poller.slew_settled.connect(self._on_slew_settled)
        self._poller.mount_info_ready.connect(self._on_mount_info)
        self._poller.environment_ready.connect(self._on_environment)
        self._poller.connect_in_thread()
        self._connecting = True
        self._poller.start()

    @pyqtSlot(object, object)
    def _on_request_done(self, callback, result):
        try:
            callback(result)
        except Exception as e:
            logger.warning(f"Mount request callback failed: {e}")

    def _mount_request(self, fn, callback=None):
        """Ask the poller thread to run fn(connection); never blocks the GUI."""
        if self._poller is not None and self._connected:
            self._poller.submit(fn, callback)

    def _release_poller(self, poller):
        """End a poller without freezing the window: it is asked to stop,
        kept until its thread ends, and its read cut after 1.5 s if a driver
        holds it. On exit (closeEvent) it is waited for, as before."""
        if poller is None:
            return
        if getattr(self, "_closing", False):
            if not poller.stop():
                logger.warning("Poller thread still busy in the driver; kept until it ends")
                self._keep_poller(poller)
            return
        poller.request_stop()
        if poller.isFinished():
            return
        self._keep_poller(poller)
        QTimer.singleShot(1500, poller.abort_read)

    def _keep_poller(self, poller):
        if poller in self._finishing_pollers:
            return
        self._finishing_pollers.append(poller)
        poller.finished.connect(lambda p=poller: self._finishing_pollers.remove(p)
                                if p in self._finishing_pollers else None)

    @pyqtSlot(bool)
    def _on_connect_result(self, ok: bool):
        self._connecting = False
        if not ok:
            self._status_panel.add_message(T("connection_failed"), Colors.STATUS_ERROR)
            poller, self._poller = self._poller, None
            self._release_poller(poller)
            self._connection = None
            if self._auto_connect_active:
                self._reschedule_auto_connect()
            return
        self._auto_connect_active = False

        self._connected = True
        self._status_panel.set_connected(True)
        pure_ascom = (isinstance(self._connection, ASCOMConnection)
                      and not self._connection.tenmicron_commands)
        self._status_panel.set_env_placeholder("env_pure_ascom" if pure_ascom else "env_none")
        self._btn_connect.setText(T("btn_disconnect"))
        self._connect_action.setEnabled(False)
        self._disconnect_action.setEnabled(True)
        self._btn_logging.setEnabled(True)

        # Configure processor
        self._processor.set_tolerances(
            self._settings.get("tolerance_ra_arcsec"),
            self._settings.get("tolerance_dec_arcsec"),
            self._settings.get("tolerance_seismic_percent"),
        )
        self._processor.set_running_range(self._settings.get("running_range_seconds"))
        self._processor.set_reference_mode(self._settings.get("reference_mode"))

        # Configure status panel tolerances
        self._status_panel.set_tolerances(
            self._settings.get("tolerance_ra_arcsec"),
            self._settings.get("tolerance_dec_arcsec"),
        )

        self._last_refresh_tick = None
        self._refresh_timer.start()

        # Start NTP if enabled
        if self._settings.get("ntp_enabled"):
            self._ntp_client = NTPClient(
                server=self._settings.get("ntp_server"),
                interval_seconds=self._settings.get("ntp_interval_seconds"),
            )
            self._ntp_client.start()

        # Start seismometer
        if self._sim_mode in ("seismometer", "all"):
            sim_sei = SimulatedSeismometer()
            sim_sei.set_callback(self.seismic_received.emit)
            sim_sei.start()
            self._seismometer = sim_sei
            self._status_panel.add_message(T("sim_seismometer"), Colors.STATUS_WARNING)
        else:
            self._apply_seismometer()

        # Logging starts on connection -- but ARMED if that is what the user
        # asked for. This call used to go straight to _start_logging, which
        # bypassed the arming entirely: connecting to a parked mount at 08:38
        # began recording at once, which is precisely what arming exists to
        # avoid.
        if (self._settings.get("autostart_on_tracking")
                and self._prev_mount_status != MountStatus.TRACKING):
            self._arm()
        else:
            self._start_logging()

        self._update_title()
        self._status_panel.add_message(T("connected"), Colors.STATUS_OK)

    def _disconnect(self):
        """Disconnect from the mount."""
        if not self._connected:
            return

        self._stop_logging()
        self._refresh_timer.stop()
        self._fft_timer.stop()

        # The poller thread closes the connection itself on its way out.
        poller, self._poller = self._poller, None
        self._release_poller(poller)

        if self._ntp_client:
            self._ntp_client.stop()
            self._ntp_client = None

        if self._seismometer:
            if hasattr(self._seismometer, 'stop'):
                self._seismometer.stop()
            self._seismometer = None
            self._current_sei_config = None

        self._connection = None
        self._connected = False
        self._status_panel.set_connected(False)
        self._btn_connect.setText(T("btn_connect"))
        self._connect_action.setEnabled(True)
        self._disconnect_action.setEnabled(False)
        self._btn_logging.setEnabled(False)

        self._update_title()
        self._status_panel.add_message(T("disconnected"))

    # ── Data handling ────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_sample(self, sample: MountSample):
        """Handle a new processed mount sample."""
        self._status_panel.update_mount_sample(sample)
        self._refresh_target(sample.status)

        # Log to file
        if self._writes_samples():
            self._file_logger.log_mount_sample(sample)

        # Update frequency display
        self._status_panel.update_frequency(
            self._processor.actual_frequency,
            self._processor.sample_count,
        )

    @pyqtSlot(object)
    def _on_time_sample(self, sample):
        """Handle time comparison data."""
        if self._ntp_client:
            sample.pc_ntp_diff_ms = self._ntp_client.offset_ms
        self._processor.process_time_sample(sample)
        if self._writes_samples():
            self._file_logger.log_time_sample(sample)

    @pyqtSlot(object)
    def _on_status_changed(self, status: MountStatus):
        """Handle mount status changes.

        Handles automatic actions on slew/park transitions:
        - Reset buffers/minmax per reset_mode
        - Close/reopen files per close_files_mode
        - Re-run mount checks after slew ends (tracking resumes)
        """
        prev_status = getattr(self, '_prev_mount_status', MountStatus.UNKNOWN)
        self._prev_mount_status = status
        self._status_panel.update_status(status)
        tracking = status not in (MountStatus.PARKED, MountStatus.IDLE, MountStatus.SLEWING)
        for graph in (self._ra_graph, self._dec_graph):
            graph.set_tracking(tracking)
        if self._logging_active:
            self._file_logger.log_event(f"Mount status: {status.name}")

        # ── Armed logger: start on tracking, suspend when tracking stops ──
        if status == MountStatus.TRACKING:
            self._cancel_park_stop()
            if self._logging_armed:
                self._start_on_tracking()
            else:
                self._resume()
        elif self._logging_armed:
            self._update_arm_button()
        elif self._logging_active and self._settings.get("pause_when_not_tracking"):
            # Any status other than TRACKING -- parked, idle, slewing --
            # starts the grace delay. Slews and autofocus finish well inside
            # it; only a real stop outlasts it.
            if self._park_timer is None and not self._logging_paused:
                delay = int(self._settings.get("pause_delay_s") or 120)
                self._park_timer = QTimer(self)
                self._park_timer.setSingleShot(True)
                self._park_timer.timeout.connect(self._pause)
                self._park_timer.start(delay * 1000)

        # Detect transition from slewing to tracking
        was_slewing = prev_status == MountStatus.SLEWING

        # Auto-reset on slewing: when the slew ENDS, as MountMonitor 3 --
        # the previous target's graph stays on screen during the slew, and
        # no sample is recorded until delay_after_slew has elapsed.
        if was_slewing and status != MountStatus.SLEWING:
            if self._settings.get("reset_mode") == "slewing":
                self._reset_both()

        if status == MountStatus.SLEWING:
            if self._settings.get("dump_mode") == "slewing":
                self._dump_graphs()

            if self._settings.get("close_files_mode") == "slewing":
                self._new_log_files()

        # Auto-dump/close on parking
        if status == MountStatus.PARKED:
            if self._settings.get("dump_mode") in ("slewing", "parking"):
                self._dump_graphs()

            if self._settings.get("close_files_mode") in ("slewing", "parking"):
                self._stop_logging()

            # Auto-analysis on park: only for a session THIS run recorded.
            # It used to fire on any PARKED status and analyse the newest
            # .dat lying on disk, so connecting to an already-parked mount
            # opened a report on a night that had nothing to do with it.
            if getattr(self, '_last_session', None) is not None:
                self._auto_analyze_on_park()


    @pyqtSlot()
    def _on_slew_settled(self):
        """Slew over and delay_after_slew elapsed: check the mount settings
        and read the new target, as MountMonitor 3 does at that moment."""
        status = getattr(self, '_prev_mount_status', MountStatus.UNKNOWN)
        if status != MountStatus.TRACKING:
            return
        self._run_mount_checks()
        self._refresh_target(status, force=True)

    #: the target is read again this often while tracking (seconds)
    TARGET_REFRESH_S = 30.0

    def _refresh_target(self, status, force: bool = False):
        """Read the mount's target (:Gr#/:Gd#, ASCOM TargetRightAscension/
        TargetDeclination) for the "Mount target coordinates" reference.

        It used to be read only when a slew ended: connecting to a mount
        already tracking, or choosing the mode during a session, left no
        target and the median was used without a word, so both references
        drew the same graph. Now read whenever tracking without one, after
        every slew, and every TARGET_REFRESH_S (a new target set without a
        slew is followed too)."""
        if self._settings.get("reference_mode") != "target" or status != MountStatus.TRACKING:
            return
        now = time.monotonic()
        last = getattr(self, '_target_asked_at', None)
        if not force and last is not None and now - last < self.TARGET_REFRESH_S:
            return
        self._target_asked_at = now
        self._mount_request(lambda c: (c.get_target_ra(), c.get_target_dec()),
                            self._receive_target)

    def _receive_target(self, target):
        from ..utils.coordinates import parse_ra, parse_dec
        target_ra, target_dec = target or (None, None)
        ra_h = parse_ra(target_ra) if target_ra else None
        dec_d = parse_dec(target_dec) if target_dec else None
        if ra_h is None or dec_d is None:
            if not getattr(self, '_target_missing_said', False):
                self._target_missing_said = True
                self._status_panel.add_message(T("ref_target_missing"), Colors.STATUS_WARNING)
            return
        self._target_missing_said = False
        if self._processor is None:
            return
        previous = self._processor.target
        self._processor.set_target_coordinates(ra_h, dec_d)
        if previous != (ra_h, dec_d):
            self._status_panel.add_message(
                T("ref_target_set").format(ra=target_ra.strip().rstrip('#'),
                                           dec=target_dec.strip().rstrip('#')))

    @pyqtSlot()
    def _on_connection_lost(self):
        self._status_panel.add_message(T("reconnecting"), Colors.STATUS_WARNING)

    @pyqtSlot()
    def _on_connection_restored(self):
        self._status_panel.add_message(T("connection_restored"), Colors.STATUS_OK)

    @pyqtSlot(str)
    def _on_log_message(self, message: str):
        self._status_panel.add_message(message)
        if self._logging_active:
            self._file_logger.log_event(message)

    @pyqtSlot(dict)
    def _on_mount_info(self, info: dict):
        """Handle initial mount info and display in status panel."""
        logger.info(f"Mount info: {info}")
        self._mount_info = info

        # Display mount info in status panel
        product = info.get('product', 'Unknown')
        firmware = info.get('firmware', 'Unknown')
        mount_id = info.get('mount_id', '')
        pier_side = info.get('pier_side')
        azimuth = info.get('azimuth')
        altitude = info.get('altitude')
        latitude = info.get('latitude')
        longitude = info.get('longitude')
        elevation = info.get('elevation')

        self._status_panel.add_message(
            f"{T('pan_mount')} : {product}", Colors.STATUS_OK
        )
        self._status_panel.add_message(
            f"{T('pan_firmware')} : {firmware}"
        )
        if mount_id:
            self._status_panel.add_message(f"{T('pan_id')} : {mount_id}")
        if pier_side and hasattr(pier_side, 'value'):
            side = {"East": T("pier_east"), "West": T("pier_west")}.get(
                pier_side.value, pier_side.value)
            self._status_panel.add_message(f"{T('pan_pier')} : {side}")
        if azimuth is not None and altitude is not None:
            self._status_panel.add_message(
                f"Az: {azimuth:.1f}\u00b0  Alt: {altitude:.1f}\u00b0"
            )
        if latitude and longitude:
            elev_str = (f"  {T('pan_elev')} {elevation:.0f} m"
                        if elevation is not None else "")
            self._status_panel.add_message(
                f"{T('pan_site')} : {latitude} {longitude}{elev_str}"
            )
            self._mount_site = (latitude, longitude, elevation)
            self._remember_site()
            self._announce_night()

        # Log to file
        if self._logging_active:
            self._file_logger.log_event(f"Mount: {product} | FW: {firmware} | ID: {mount_id}")
            if azimuth is not None:
                self._file_logger.log_event(f"Az: {azimuth:.1f} Alt: {altitude:.1f}")

        # Run mount checks
        self._run_mount_checks()

    def _on_environment(self, sample):
        """Handle environment/diagnostics data from the poller."""
        # Log to file
        if self._writes_samples():
            self._file_logger.log_environment(sample)

        # Permanent gauge in the values box; the history gets a line only
        # when the air has really changed (it got one every 30 s, 120 lines
        # an hour that pushed everything else out).
        self._status_panel.update_environment(sample)
        prev = getattr(self, "_env_logged", None)
        t, p = sample.temperature_ext, sample.pressure
        changed = prev is None or (
            (t is not None and prev[0] is not None and abs(t - prev[0]) >= 0.5)
            or (p is not None and prev[1] is not None and abs(p - prev[1]) >= 1.0))
        parts = []
        if sample.temperature_ext is not None:
            parts.append(f"{T('env_temp')} {sample.temperature_ext:.1f} \u00b0C")
        if sample.pressure is not None:
            parts.append(f"{sample.pressure:.1f} hPa")
        if sample.temperature_int is not None:
            parts.append(f"{T('env_inside')} {sample.temperature_int:.1f} \u00b0C")
        if sample.meridian_flip_minutes is not None:
            parts.append(f"{T('env_flip')} {sample.meridian_flip_minutes:.0f} min")
        if parts and changed:
            self._status_panel.add_message("  ".join(parts))
            self._env_logged = (t, p)

        # Log alignment data (less frequently visible)
        if sample.alignment_stars is not None and sample.alignment_rms is not None:
            logger.debug(
                f"Alignment: {sample.alignment_stars} terms, "
                f"RMS {sample.alignment_rms:.1f}\", "
                f"polar error {sample.polar_error_deg if sample.polar_error_deg is not None else float('nan'):.4f}\u00b0"
            )

        # Log to event file
        if self._writes_samples():
            if sample.temperature_ext is not None:
                # Each field can be None independently (the mount does not
                # always return pressure/internal temperature) — and a
                # conditional format spec in an f-string is a ValueError.
                press = (
                    f"{sample.pressure:.1f}" if sample.pressure is not None else "?"
                )
                int_temp = (
                    f"{sample.temperature_int:.1f}"
                    if sample.temperature_int is not None
                    else "?"
                )
                self._file_logger.log_event(
                    f"ENV\tTemp={sample.temperature_ext:.1f}°C "
                    f"Press={press}mbar "
                    f"IntTemp={int_temp}°C"
                )

    @pyqtSlot(float, object)
    def _on_seismic_data(self, timestamp: float, values: list[float]):
        """Handle seismometer data (GUI thread, via seismic_received)."""
        self._processor.process_seismic_data(timestamp, values)
        # Parity with the Java MountMonitor: every sample is logged in the
        # .sei (time, raw, value re-centred by the offset, current running
        # stdev). Without this call the file stayed empty.
        if self._logging_active and values:
            # The seismometer module delivers already re-centred values
            # (raw + offset, as in MM3): the raw value is rebuilt for the
            # 1st column.
            offset = float(self._settings.get("seismometer_offset") or 0.0)
            stdev_arr = self._processor.seismic_buffer.get_stdev_array()
            stdev = float(stdev_arr[-1]) if len(stdev_arr) else 0.0
            for t, v in zip(self._processor.seismic_times(timestamp, len(values)), values):
                self._file_logger.log_seismic_data(t, v - offset, v, stdev)

    # ── Graph refresh ────────────────────────────────────────────

    # Graph cadence: 4 per second where the machine allows it. On a small PC
    # (2-4 cores) it starts at 2 per second, and on any machine it slows down
    # (to 1 per second) when drawing takes too long, then speeds up again.
    RATES_MS = (250, 500, 1000)

    def _refresh_graphs(self):
        """Timer slot: skip when nobody can see the window, adapt the cadence."""
        if self.isMinimized() or not self.isVisible():
            self._last_refresh_tick = None
            return
        t0 = time.perf_counter()
        # Lateness of this tick: the painting of the previous refresh
        # happens after the slot, in the event loop, and is not timed by it;
        # a saturated loop shows as ticks arriving late.
        last = getattr(self, "_last_refresh_tick", None)
        self._last_refresh_tick = t0
        late_ms = 0.0
        if last is not None:
            late_ms = max(0.0, (t0 - last) * 1000.0 - self._refresh_timer.interval())
            if late_ms > 3000.0:             # a sleep, a modal dialog: not a cost
                late_ms = 0.0
        try:
            self._refresh_graphs_now()
        finally:
            slot_ms = (time.perf_counter() - t0) * 1000.0
            self._adapt_rate(max(2.0 * slot_ms, slot_ms + late_ms))

    def _adapt_rate(self, cost_ms: float):
        current_cfg = self._refresh_timer.interval()
        rates_ms = self.RATES_MS
        i = rates_ms.index(current_cfg) if current_cfg in rates_ms else 0
        average = 0.8 * getattr(self, "_refresh_cost", cost_ms) + 0.2 * cost_ms
        self._refresh_cost = average
        if average > 0.4 * current_cfg and i + 1 < len(rates_ms):
            self._refresh_timer.setInterval(rates_ms[i + 1])
        elif i > self._cadence_min and average < 0.1 * rates_ms[i - 1]:
            self._refresh_timer.setInterval(rates_ms[i - 1])

    def _refresh_graphs_now(self):
        """Refresh all graphs with current buffer data.

        The graphs scroll at the present: each one receives only the last
        `window_width(zoom)` seconds, at full resolution (two minutes is
        a few hundred samples). The night statistics (min/max/maximum
        standard deviation) are still computed over the whole buffer, by
        DataBuffer.
        """
        span = self._span()

        # Graph correction: shift STDEV timestamps back by half running range
        correct = self._settings.get("correct_graphs_for_range")
        half_range = self._settings.get("running_range_seconds") / 2.0 if correct else 0.0

        # Only the visible tail is copied out of each buffer (get_tail): the
        # previous version rebuilt seven 50,000-element arrays four times a
        # second to keep about a thousand points of each.
        # RA / DEC
        # Positions are drawn from the RAW coordinates, around the median of
        # what is visible (deviations_from_median), in the RA unit chosen in the
        # preferences: seconds of time (hours mode) or arcseconds of RA
        # (degrees mode, 15 times more), like MountMonitor 3. The running
        # sigma is computed on sky (x cos dec) and converted the same way.
        p = self._processor
        in_degrees = bool(self._settings.get("ra_in_degrees"))
        cos_d = max(abs(np.cos(np.radians(p.declination_deg))), 1e-3)
        k_ra = (1.0 if in_degrees else 1.0 / 15.0) / cos_d     # sky " -> unit
        self._ra_graph.set_unit('"' if in_degrees else 's')
        for raw, buf, graph, factor, wrap, k_sd, tol in (
                (p.ra_raw_buffer, p.ra_buffer, self._ra_graph,
                 54000.0 if in_degrees else 3600.0, 24.0, k_ra,
                 self._displayed_ra_tolerance()),
                (p.dec_raw_buffer, p.dec_buffer, self._dec_graph,
                 3600.0, None, 1.0, self._settings.get("tolerance_dec_arcsec"))):
            t, raw_text, _, _ = raw.get_tail(span)
            if len(t) == 0:
                continue
            v = deviations_from_median(raw_text, factor, wrap)
            _, _, sd_t, sd = buf.get_tail(span, float(t[-1]))
            graph.update_data(
                t, v,
                stdev_values=sd * k_sd if len(sd) else None,
                stdev_timestamps=(sd_t - half_range) if len(sd) else None,
                min_val=float(np.min(v)),
                max_val=float(np.max(v)),
                max_stdev=(buf.max_stdev or 0.0) * k_sd,
                span_s=span,
            )
            graph.set_tolerance(tol)

        # Time graph
        diff_t, diff_v, _, _ = self._processor.time_diff_buffer.get_tail(span)
        if len(diff_t) > 0:
            end = float(diff_t[-1])
            pc_t, pc_v, _, _ = self._processor.pc_loop_buffer.get_tail(span, end)
            mt_t, mt_v, _, _ = self._processor.mount_loop_buffer.get_tail(span, end)
            ntp_t, ntp_v, _, _ = self._processor.ntp_buffer.get_tail(span, end)
            self._time_graph.update_data(
                diff_t, diff_v,
                pc_loop_t=pc_t, pc_loop_v=pc_v,
                mount_loop_t=mt_t, mount_loop_v=mt_v,
                ntp_t=ntp_t if len(ntp_t) > 0 else None,
                ntp_v=ntp_v if len(ntp_v) > 0 else None,
                span_s=span,
                drift_ms_h=self._clock_drift(),
            )

        # Axial graph: speeds computed from the axis angles over the
        # visible span plus one running range (the regression needs it).
        if self._axial_mode() != "off":
            rng = float(self._settings.get("running_range_seconds") or 60)
            args = {}
            for name, b, dflt in (("ra", self._processor.ra_axis_buffer, RA_DEFAULT_SPEED),
                                  ("dec", self._processor.dec_axis_buffer, 0.0)):
                t, v, _, _ = b.get_tail(span + rng)
                s = axial_speeds(t, v, rng, dflt) if len(t) > 1 else None
                if s is not None:
                    s["t"] = s["t"] + (float(t[0]) - float(t[-1]))
                args[name] = s
            if args["ra"] or args["dec"]:
                mode = self._axial_mode()
                shift = (rng if mode == "displacement" else rng / 2.0) if correct else 0.0
                self._axial_graph.update_data(
                    span_s=span, mode=mode, shift_s=shift,
                    dec_deg=self._processor._declination_deg, **args)

        # Seismic graph
        sei_t, sei_v, sei_sd_t, sei_sd = self._processor.seismic_buffer.get_tail(span)
        if len(sei_t) > 0:
            # The tolerance lines were never set and stayed at +/-100
            # whatever the preferences said.
            self._seismic_graph.set_tolerance(
                float(self._settings.get("tolerance_seismic_percent") or 0.0),
                float(self._settings.get("seismometer_range") or 0.0))
            self._seismic_graph.update_data(
                sei_t, sei_v,
                stdev_values=sei_sd if len(sei_sd) else None,
                stdev_timestamps=sei_sd_t if len(sei_sd) else None,
                span_s=span,
            )

        # Update STDEV in status panel (last value of the night computation)
        full_ra_stdev = self._processor.ra_buffer.get_stdev_array()
        full_dec_stdev = self._processor.dec_buffer.get_stdev_array()
        if len(full_ra_stdev) > 0 and len(full_dec_stdev) > 0:
            self._status_panel.update_stdev(full_ra_stdev[-1], full_dec_stdev[-1])

        # A write error (disk full, network share gone) is said once.
        error = getattr(self._file_logger, "write_error", None)
        if error and not getattr(self, "_write_error_reported", False):
            self._write_error_reported = True
            self._status_panel.add_message(f"\u26a0 {T('write_error')} : {error}",
                                           Colors.STATUS_ERROR)

        # Update title with current frequency
        self._update_title()

        # Photographic log of the night, when requested.
        self._check_graph_full()

    # ── FFT ──────────────────────────────────────────────────────

    def _show_fft(self):
        """Show FFT analysis window."""
        if self._fft_window is None:
            self._fft_window = FFTWindow()
            self._fft_window.span_changed.connect(lambda _m: self._update_fft())
            w = self._settings.get("fft_width")
            h = self._settings.get("fft_height")
            self._fft_window.resize(w, h)
        self._fft_window.show()
        self._fft_window.raise_()
        self._fft_timer.start()

    def _update_fft(self):
        """Every 2 s: spectra computed in a background thread, then shown
        and logged by _on_fft_computed in this one.

        The three spectra of 50,000 samples took 25 ms (desktop CPU) on the
        GUI thread every 2 s, with or without the window; on a NUC, 60-80 ms
        of frozen window each time. Only the copies of the buffers are made
        here. A computation still running is not doubled."""
        fft_visible = bool(self._fft_window and self._fft_window.isVisible())
        if not fft_visible and not self._logging_active:
            return
        job = getattr(self, "_fft_job", None)
        if job is not None and job.is_alive():
            return
        ra_t, ra_data = self._processor.ra_buffer.get_arrays()
        dec_t, dec_data = self._processor.dec_buffer.get_arrays()
        _, sei_data = self._processor.seismic_buffer.get_arrays()
        sei_rate = self._settings.get("seismometer_frequency_hz")
        signal = self.fft_computed
        # The last N minutes only, the same for the three series (chosen in
        # the FFT window): over the whole buffer, the mount spectrum
        # covered hours (50,000 samples at 2 Hz) and the seismometer's 41
        # minutes (at 20 Hz), and the two could no longer be compared.
        try:
            span_s = float(self._settings.get("fft_span_min") or 0) * 60.0
        except (TypeError, ValueError):
            span_s = 1800.0
        if span_s > 0:
            if len(ra_t):
                keep = ra_t >= ra_t[-1] - span_s
                ra_t, ra_data = ra_t[keep], ra_data[keep]
            if len(dec_t):
                keep = dec_t >= dec_t[-1] - span_s
                dec_t, dec_data = dec_t[keep], dec_data[keep]
            if sei_rate and sei_rate > 0:
                sei_data = sei_data[-int(span_s * sei_rate):]

        def work():
            # On the real timestamps: the sampling rate is measured on the
            # data, gaps are skipped, drift and dither steps removed
            # (src/core/spectrum.py).
            from ..core.spectrum import spectrum, regular_spectrum
            try:
                d = np.diff(ra_t) if len(ra_t) > 1 else np.array([])
                d = d[d > 0]
                result = {
                    "ra": spectrum(ra_t, ra_data) if len(ra_data) > 64 else (None, None),
                    "dec": spectrum(dec_t, dec_data) if len(dec_data) > 64 else (None, None),
                    "sei": (regular_spectrum(sei_data, sei_rate)
                            if len(sei_data) > 64 else (None, None)),
                    "freq": 1.0 / float(np.median(d)) if len(d) else 0.0,
                    "sei_rate": sei_rate if len(sei_data) > 0 else None,
                    "durations": {
                        "ra": float(ra_t[-1] - ra_t[0]) if len(ra_t) > 1 else 0.0,
                        "dec": float(dec_t[-1] - dec_t[0]) if len(dec_t) > 1 else 0.0,
                        "sei": (len(sei_data) / float(sei_rate)
                                if sei_rate and len(sei_data) else 0.0),
                    },
                }
            except Exception as e:
                logger.warning(f"FFT not computed: {e}")
                return
            try:
                signal.emit(result)
            except RuntimeError:
                pass                  # window closed meanwhile

        import threading
        self._fft_job = threading.Thread(target=work, daemon=True, name="FFT")
        self._fft_job.start()

    def _on_fft_computed(self, r):
        (ra_freqs, ra_mags), (dec_freqs, dec_mags) = r["ra"], r["dec"]
        sei_freqs, sei_mags = r["sei"]
        freq = r["freq"]
        if self._fft_window and self._fft_window.isVisible():
            self._fft_window.update_fft(
                ra_freqs=ra_freqs, ra_mags=ra_mags,
                dec_freqs=dec_freqs, dec_mags=dec_mags,
                sei_freqs=sei_freqs, sei_mags=sei_mags,
                ra_sample_rate=freq, dec_sample_rate=freq,
                sei_sample_rate=r["sei_rate"],
                durations=r.get("durations"),
            )

        # Log FFT data to .fft file
        if self._writes_samples():
            if ra_freqs is not None and len(ra_freqs) > 0:
                self._file_logger.log_fft_snapshot("RA", freq, ra_freqs, ra_mags)
            if dec_freqs is not None and len(dec_freqs) > 0:
                self._file_logger.log_fft_snapshot("DEC", freq, dec_freqs, dec_mags)
            if sei_freqs is not None and len(sei_freqs) > 0:
                self._file_logger.log_fft_snapshot("SEI", self._settings.get(
                    "seismometer_frequency_hz"), sei_freqs, sei_mags)

    # ── Logging ──────────────────────────────────────────────────

    def _toggle_logging(self):
        if self._logging_active:
            self._stop_logging()
        elif self._logging_armed:
            self._disarm()
        elif self._settings.get("autostart_on_tracking"):
            self._arm()
        else:
            self._start_logging()

    def _arm(self):
        """Wait for the mount to track before writing anything."""
        self._logging_armed = True
        self._daylight_reported = False
        self._update_arm_button()
        self._status_panel.add_message(T("logging_armed"), Colors.STATUS_OK)
        # Already tracking when armed: start at once rather than wait for a
        # transition that has already happened -- unless it is broad daylight.
        if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
            self._start_on_tracking()
        # Armed in daylight while the mount already tracks: no status change
        # will come at sunset, so nothing started. Look again every minute.
        if self._arm_timer is None:
            self._arm_timer = QTimer(self)
            self._arm_timer.timeout.connect(self._check_arming)
        self._arm_timer.start(60_000)

    AUTO_OPTIONS = (("connect_on_launch", "pref_connect_launch", "tt_connect_launch"),
                    ("autostart_on_tracking", "pref_autostart", "tt_arm"),
                    ("pause_when_not_tracking", "pref_pause", "tt_pause"),
                    ("close_at_sunrise", "pref_close_sunrise", "tt_sunrise"))

    def _logging_menu(self, pos):
        menu = QMenu(self)
        for key, caption, tooltip in self.AUTO_OPTIONS:
            a = QAction(T(caption), menu)
            a.setCheckable(True)
            a.setChecked(bool(self._settings.get(key)))
            a.setToolTip(T(tooltip))
            a.toggled.connect(lambda on, c=key: self._auto_option(c, on))
            menu.addAction(a)
        menu.setToolTipsVisible(True)
        menu.addSeparator()
        menu.addAction(T("menu_preferences"), self._show_preferences)
        menu.exec(self._btn_logging.mapToGlobal(pos))

    def _auto_option(self, key: str, active: bool):
        self._settings.set(key, bool(active))
        self._save_settings()
        if self._logging_armed:
            # « Night only » just switched off while the mount tracks in
            # daylight: start now rather than at the next minute's check.
            if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
                self._start_on_tracking()
            self._update_arm_button()

    def _check_arming(self):
        if not self._logging_armed or self._logging_active:
            self._arm_timer.stop()
            return
        if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
            self._start_on_tracking()
        self._update_arm_button()

    def _update_arm_button(self):
        """Armed: the button says what it is waiting for.

        It used to read « ARMED — waiting for tracking » while the status
        line said the mount was tracking: what it was really waiting for was
        the night (no session is opened in daylight, see _fait_jour).
        """
        if not self._logging_armed or self._logging_active:
            self._btn_logging.setToolTip(T("tt_start_logging"))
            return
        tracking_now = getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING
        if tracking_now and self._is_daytime():
            self._btn_logging.setText(T("btn_armed_night"))
        else:
            self._btn_logging.setText(T("btn_armed_log"))
        self._btn_logging.setToolTip(T("tt_armed"))

    def _is_daytime(self) -> bool:
        """Is the Sun up? False if it cannot be known.

        Serves as a safeguard for arming: at sunrise the mount is often
        still tracking, so re-arming restarted a session within the
        second — the program closed the night then immediately reopened a
        file in broad daylight, in a loop.
        """
        if not self._settings.get("close_at_sunrise"):
            return False
        site = self._site()
        if not site:
            return False
        from ..core.ephemerides import sun_altitude, HORIZON
        from datetime import datetime, timezone
        try:
            return sun_altitude(datetime.now(timezone.utc), site[0], site[1]) > HORIZON
        except Exception:
            return False

    def _disarm(self):
        self._logging_armed = False
        self._btn_logging.setText(T("btn_start_log"))
        self._btn_logging.setToolTip(T("tt_start_logging"))
        self._status_panel.add_message(T("logging_disarmed"))

    def _start_on_tracking(self):
        """The mount started tracking while armed."""
        if not self._logging_armed or self._logging_active:
            return
        if self._is_daytime():
            # Stay armed: the night will come. Said once, and the button
            # shows it; otherwise "waiting for tracking" contradicted the
            # state "the mount is tracking".
            self._update_arm_button()
            if not getattr(self, '_daylight_reported', False):
                self._daylight_reported = True
                self._status_panel.add_message(T("logging_armed_day"))
            return
        self._logging_armed = False
        self._start_logging()
        self._status_panel.add_message(T("logging_autostart"), Colors.STATUS_OK)

    def _writes_samples(self) -> bool:
        """Whether samples should go to the file right now."""
        return self._logging_active and not self._logging_paused

    def _cancel_park_stop(self):
        if self._park_timer is not None:
            self._park_timer.stop()
            self._park_timer = None

    def _pause(self):
        """Mount stopped tracking long enough: stop writing, keep the session.

        A grace delay is used because a stop can be transient -- a meridian
        flip, a slew between two targets, an autofocus run. Suspending on the
        first non-tracking sample would punch a hole in every dither.
        """
        self._cancel_park_stop()
        if not self._logging_active or self._logging_paused:
            return
        self._logging_paused = True
        self._file_logger.log_event("Logging suspended: mount not tracking")
        self._status_panel.add_message(T("logging_suspendu"))

    def _resume(self):
        """Tracking resumed: same file, same night."""
        if not self._logging_active or not self._logging_paused:
            return
        self._logging_paused = False
        self._file_logger.log_event("Logging resumed: mount tracking again")
        self._status_panel.add_message(T("logging_repris"), Colors.STATUS_OK)

    def _watch_dawn(self):
        """Close the session once the Sun is up, and only then.

        The night is one unit: a mount that parks at 02:00 and resumes at
        03:00 is still the same night, and must stay in one file with one
        report. Only daylight ends it -- and only after the Sun has actually
        been down during the session, so that a daytime test does not close
        itself the moment it starts.
        """
        if not self._logging_active:
            return
        site = self._site()
        if not site:
            return
        from ..core.ephemerides import sun_altitude, HORIZON
        from datetime import datetime, timezone
        lat, lon, _ = site
        try:
            h = sun_altitude(datetime.now(timezone.utc), lat, lon)
        except Exception as exc:
            logger.error(f"Sun altitude failed: {exc}")
            return
        if h <= HORIZON:
            self._night_seen = True
            return
        if self._night_seen:
            self._status_panel.add_message(T("logging_autostop"), Colors.STATUS_OK)
            self._stop_logging()

            # And show the report. The automatic analysis only triggered on
            # a TRANSITION to PARKED: a mount parked for half an hour when
            # the Sun rises produces none, so the night was closed, the
            # report written, and nothing displayed. Yet that is the only
            # moment one wants to see it.
            self._auto_analyze_on_park()

            # And wait again for the evening. Without this the program
            # stayed connected but inert until a click: someone had to be
            # there every evening. Armed, it chains the nights on its own.
            if (self._connected
                    and self._settings.get("autostart_on_tracking")):
                self._arm()

    def _start_logging(self):
        """Start data logging to files."""
        if self._logging_active:
            return
        session = SessionInfo(
            version=self._version,
            observatory=self._settings.get("observatory_name"),
            mount_name=self._settings.get("mount_name"),
            protocol=ConnectionProtocol(self._settings.get("mount_protocol"))
                if self._sim_mode == "none" else ConnectionProtocol.SIMULATION,
            # Timezone-aware, from whatever the PC is set to. astimezone()
            # with no argument is the one portable way to get the local
            # offset on Windows, macOS and Linux alike, and it follows DST;
            # time.timezone / time.altzone do not, and get it wrong twice a
            # year. The offset travels with the file so that a replay in
            # another timezone still reads the right local hours.
            start_time=datetime.now().astimezone(),
        )
        # Always store the site as decimal degrees, longitude positive EAST.
        # The mount speaks sexagesimal LX200 with longitude positive WEST and
        # the preferences hold plain decimals: writing either verbatim would
        # put two incompatible conventions under the same header key, and the
        # reader would have to guess -- guessing wrong flips the hemisphere.
        _site = self._site()
        if _site:
            session.latitude = f"{_site[0]:.5f}"
            session.longitude = f"{_site[1]:.5f}"
            session.elevation = f"{_site[2]:.0f}"
        self._write_error_reported = False
        if self._file_logger.start_session(session) is False:
            error = getattr(self._file_logger, "write_error", "") or ""
            self._status_panel.add_message(
                f"\u26a0 {T('log_start_failed')} : {error}", Colors.STATUS_ERROR)
            return
        self._logging_active = True
        self._logging_paused = False
        self._night_seen = False
        if self._settings.get("close_at_sunrise"):
            self._dawn_timer = QTimer(self)
            self._dawn_timer.timeout.connect(self._watch_dawn)
            self._dawn_timer.start(60_000)
            self._watch_dawn()
        self._btn_logging.setText(T("btn_stop_log"))
        # Start FFT timer for logging even if FFT window is not open
        if not self._fft_timer.isActive():
            self._fft_timer.start()
        self._status_panel.add_message(T("logging_started"), Colors.STATUS_OK)
        # Also announce the night when the site comes from the preferences:
        # _on_mount_info only fires when the mount answers, which is exactly
        # the case the preferences exist to cover.
        self._announce_night()

    def _stop_logging(self):
        """Stop data logging."""
        self._cancel_park_stop()
        if self._dawn_timer is not None:
            self._dawn_timer.stop()
            self._dawn_timer = None
        self._logging_paused = False
        if not self._logging_active:
            return
        dat_path = getattr(self._file_logger, 'dat_path', None)
        self._last_session = dat_path
        self._file_logger.close()
        self._logging_active = False
        self._btn_logging.setText(T("btn_start_log"))
        self._status_panel.add_message(T("logging_stopped"))

        # The night report is written on its own, next to the .dat. Asking the
        # user to remember to export it is how a night ends up without one.
        if dat_path:
            self._start_end_of_night(dat_path, write=True)

    def _start_end_of_night(self, dat_path, write: bool):
        key = str(dat_path)
        if key in self._night_jobs:
            return
        job = EndOfNightJob(key, get_language(), write, self)
        job.completed.connect(self._end_of_night_ready)
        job.finished.connect(job.deleteLater)
        self._night_jobs[key] = job
        job.start()

    @pyqtSlot(str, object, object)
    def _end_of_night_ready(self, path: str, session, output):
        self._night_jobs.pop(path, None)
        if output:
            self._status_panel.add_message(
                f"{T('report_saved')} : {Path(output).stem[:-3]}*.txt "
                f"({', '.join(LANGUAGES)})", Colors.STATUS_OK
            )
        if session is None:
            return
        if path in self._analysis_requested:
            self._analysis_requested.discard(path)
            self._show_analysis(session)
        else:
            # Kept for the park that usually follows the dawn close.
            self._read_session = (path, session)

    def _new_log_files(self):
        """Close current files and open new ones."""
        if self._logging_active:
            session = SessionInfo(
                version=self._version,
                observatory=self._settings.get("observatory_name"),
                mount_name=self._settings.get("mount_name"),
                protocol=ConnectionProtocol.SIMULATION
                    if self._sim_mode != "none" else ConnectionProtocol(self._settings.get("mount_protocol")),
                # Timezone-aware, from whatever the PC is set to. astimezone()
            # with no argument is the one portable way to get the local
            # offset on Windows, macOS and Linux alike, and it follows DST;
            # time.timezone / time.altzone do not, and get it wrong twice a
            # year. The offset travels with the file so that a replay in
            # another timezone still reads the right local hours.
            start_time=datetime.now().astimezone(),
            )
            self._file_logger.new_files(session)
            self._status_panel.add_message(T("new_log_files"))

    # ── Log replay & analysis ───────────────────────────────────

    def _open_log10m_files(self):
        """Open and analyze 10micron mount .log10m internal log files."""
        dialog = Log10mAnalysisDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def _open_log_file(self):
        """Open a previous log file for replay and analysis."""
        log_dir = str(self._file_logger.log_dir)

        title = T("open_log_title")
        filter_str = T("open_log_filter")

        file_path, _ = QFileDialog.getOpenFileName(
            self, title, log_dir, filter_str
        )
        if not file_path:
            return

        self._status_panel.add_message(
            f"{T('loading_file')} : {Path(file_path).name}..."
        )
        # Parsed in the background: a long night took seconds (a minute on
        # a small PC) with the window frozen, live polling included.
        job = EndOfNightJob(file_path, get_language(), False, self)
        job.completed.connect(self._replay_ready)
        job.finished.connect(job.deleteLater)
        self._replay_job = job
        job.start()

    @pyqtSlot(str, object, object)
    def _replay_ready(self, file_path: str, session, _output):
        self._replay_job = None
        if session is None or session.sample_count == 0:
            self._status_panel.add_message(
                T("replay_no_data"), Colors.STATUS_ERROR
            )
            return

        # Show info
        msg = T("replay_loaded").format(
            samples=f"{session.sample_count:,}",
            duration=session.duration_str,
        )
        self._status_panel.add_message(msg, Colors.STATUS_OK)
        self._status_panel.add_message(
            f"  {T('replay_mode')}", Colors.STATUS_WARNING
        )

        # Drawing the graphs must never cost the night report. Until 1.10.2 a
        # single mismatched array left the graphs black AND stopped the report
        # from opening, with nothing said: the exception went to stderr, which
        # a packaged build does not show.
        try:
            self._replay_session(session)
        except Exception as exc:
            logger.exception("Replay: graph drawing failed")
            self._status_panel.add_message(
                f"{T('replay_graphs_failed')} : {exc}", Colors.STATUS_ERROR
            )

        try:
            self._replay_fft(session)
        except Exception as exc:
            logger.exception("Replay: FFT failed")
            self._status_panel.add_message(
                f"{T('replay_fft_failed')} : {exc}", Colors.STATUS_ERROR
            )

        # The report is the point of the whole operation: it opens even if
        # everything above failed.
        try:
            dialog = AnalysisDialog(session, self)
            dialog.exec()
            dialog.deleteLater()      # parented to the window: freed, not kept
        except Exception as exc:
            logger.exception("Replay: analysis report failed")
            self._status_panel.add_message(
                f"{T('replay_report_failed')} : {exc}", Colors.STATUS_ERROR
            )
            return

        self._status_panel.add_message(
            T("analysis_complete"), Colors.STATUS_OK
        )

    def _replay_session(self, session):
        """Load parsed session data into the graph widgets.

        The abscissa MUST be `deviation_timestamps`, not `timestamps`: the
        latter holds every sample of the file, while the deviations only hold
        the samples kept in the segments (slews and, since 1.10.0, commanded
        excursions are dropped). Plotting 54 047 abscissae against 44 604
        ordinates draws nothing at all — the graphs stayed black while the
        console announced replay mode, which is exactly what was reported.
        """
        t_dev = session.deviation_timestamps
        if len(t_dev) != len(session.ra_deviations):
            t_dev = session.timestamps[:len(session.ra_deviations)]

        # RA graph
        if len(session.ra_deviations) > 0 and len(t_dev) == len(session.ra_deviations):
            sd = session.deviation_ra_stdevs
            sd = sd if len(sd) == len(t_dev) else None
            self._ra_graph.update_data(
                t_dev, session.ra_deviations,
                stdev_values=sd,
                min_val=float(np.min(session.ra_deviations)),
                max_val=float(np.max(session.ra_deviations)),
                max_stdev=float(np.max(sd)) if sd is not None and np.any(sd > 0) else None,
            )

        # DEC graph
        if len(session.dec_deviations) > 0 and len(t_dev) == len(session.dec_deviations):
            sd = session.deviation_dec_stdevs
            sd = sd if len(sd) == len(t_dev) else None
            self._dec_graph.update_data(
                t_dev, session.dec_deviations,
                stdev_values=sd,
                min_val=float(np.min(session.dec_deviations)),
                max_val=float(np.max(session.dec_deviations)),
                max_stdev=float(np.max(sd)) if sd is not None and np.any(sd > 0) else None,
            )

        # Time graph
        if len(session.time_timestamps) > 0:
            self._time_graph.update_data(
                session.time_timestamps, session.time_pc_mount_diff,
                pc_loop_t=session.time_timestamps if len(session.time_pc_loop) > 0 else None,
                pc_loop_v=session.time_pc_loop if len(session.time_pc_loop) > 0 else None,
                mount_loop_t=session.time_timestamps if len(session.time_mount_loop) > 0 else None,
                mount_loop_v=session.time_mount_loop if len(session.time_mount_loop) > 0 else None,
                ntp_t=session.time_timestamps if len(session.time_ntp_diff) > 0 and np.any(session.time_ntp_diff != 0) else None,
                ntp_v=session.time_ntp_diff if len(session.time_ntp_diff) > 0 and np.any(session.time_ntp_diff != 0) else None,
            )

        # Axial graph
        if len(session.ra_axis) > 2 and np.any(session.ra_axis != 0):
            rng = float(self._settings.get("running_range_seconds") or 60)
            t = session.timestamps[:len(session.ra_axis)]
            ra = axial_speeds(t, session.ra_axis, rng, RA_DEFAULT_SPEED)
            dec = (axial_speeds(t, session.dec_axis, rng)
                   if len(session.dec_axis) == len(session.ra_axis) else None)
            if ra is not None:
                dec_deg = (float(np.median(session.dec_degrees))
                           if len(session.dec_degrees) else 0.0)
                self._axial_graph.update_data(
                    ra=ra, dec=dec, dec_deg=dec_deg,
                    mode=self._settings.get("axial_mode") or "velocity")

    def _replay_fft(self, session):
        """Compute and display FFT from replayed data."""
        if session.effective_frequency <= 0:
            return

        freq = session.effective_frequency

        ra_freqs, ra_mags = None, None
        dec_freqs, dec_mags = None, None

        from ..core.spectrum import spectrum, regular_spectrum

        def compute(dev):
            t = getattr(session, "deviation_timestamps", None)
            if t is not None and len(t) == len(dev):
                return spectrum(t, dev)
            return regular_spectrum(dev, freq, remove_steps=True)

        if len(session.ra_deviations) > 64:
            ra_freqs, ra_mags = compute(np.asarray(session.ra_deviations))
        if len(session.dec_deviations) > 64:
            dec_freqs, dec_mags = compute(np.asarray(session.dec_deviations))

        # Show FFT window with replayed data
        if ra_freqs is not None or dec_freqs is not None:
            if self._fft_window is None:
                self._fft_window = FFTWindow()
                self._fft_window.span_changed.connect(lambda _m: self._update_fft())
            self._fft_window.set_span_visible(False)
            self._fft_window.update_fft(
                ra_freqs=ra_freqs, ra_mags=ra_mags,
                dec_freqs=dec_freqs, dec_mags=dec_mags,
                ra_sample_rate=freq, dec_sample_rate=freq,
            )
            self._fft_window.show()
            self._fft_window.raise_()

    def _auto_analyze_on_park(self):
        """Show the report of the night that has just ended.

        Called at the morning close and on a park. A given session is shown
        only once: otherwise a mount parking after sunrise opened a second
        window on the same report.
        """
        try:
            dat_path = self._last_session
            if dat_path is None or not Path(dat_path).exists():
                return
            if str(dat_path) == getattr(self, '_analysed_session', None):
                return
            self._analysed_session = str(dat_path)
            # A session of a handful of bytes has nothing to say.
            if Path(dat_path).stat().st_size < 1024:
                return

            self._status_panel.add_message(
                T("parked_auto_analysis"), Colors.STATUS_OK,
            )
            key = str(dat_path)
            read_back = self._read_session
            if read_back is not None and read_back[0] == key:
                self._read_session = None
                self._show_analysis(read_back[1])
                return
            # Read in the background; the window opens when it is ready.
            self._analysis_requested.add(key)
            self._start_end_of_night(key, write=False)
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    def _show_analysis(self, session):
        try:
            if session.sample_count < 10:
                return
            # Non-modal, and only one at a time. exec() blocked the event
            # loop: on the first morning with nobody in front of the screen,
            # the program froze. The previous one is DESTROYED, not merely
            # hidden: close() kept it in memory with its whole session
            # (+100 MB per night, down to swap on a 4 GB PC).
            previous = getattr(self, '_analysis_window', None)
            if previous is not None:
                try:
                    previous.close()
                    previous.deleteLater()
                except RuntimeError:
                    pass          # already destroyed by Qt
            dialog = AnalysisDialog(session, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            self._analysis_window = dialog
            self._status_panel.add_message(T("analysis_complete"), Colors.STATUS_OK)
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    # ── Zoom and reset ───────────────────────────────────────────

    def _seismometer_config(self):
        g = self._settings.get
        return (g("seismometer_port"), float(g("seismometer_frequency_hz") or 20),
                int(g("seismometer_offset") or 0), int(g("seismometer_range") or 2000),
                int(g("seismometer_baud") or 9600))

    def _axial_mode(self) -> str:
        """The axial mode in force: "off" when the axes cannot be read.

        The axis angles come from 10Micron commands (:GaXa#, :GaXb#). In
        pure ASCOM they are never sent, so the mode chosen before switching
        to ASCOM must not poll nor show an empty graph."""
        mode = self._settings.get("axial_mode") or "off"
        if (self._settings.get("mount_protocol") == "ascom"
                and not self._settings.get("ascom_10micron_commands")
                and self._sim_mode == "none"):
            return "off"
        return mode

    def _save_settings(self):
        """Settings written to disk; a full disk or a read-only folder is
        logged, not raised: in a slot it counted as a crash, and on exit it
        stopped closeEvent before the night's files were closed."""
        try:
            self._settings.save()
        except OSError as e:
            logger.error(f"Settings not saved: {e}")

    def _apply_seismometer(self):
        """Start, restart or stop the seismometer to match the preferences,
        at once, and show or hide its graph.

        It used to start only at connection and its graph to be added only
        when the window was built: ticking « Enable » showed nothing until a
        restart, and a port that would not open (often because JamaSeis held
        it) was reported in the log file alone.
        """
        if self._sim_mode in ("seismometer", "all"):
            return
        wanted = bool(self._settings.get("seismometer_enabled"))
        cfg = self._seismometer_config()
        current_cfg = getattr(self, '_current_sei_config', None)
        if self._seismometer is not None and (not wanted or cfg != current_cfg):
            try:
                self._seismometer.stop()
            except Exception as e:
                logger.warning(f"Seismometer stop: {e}")
            self._seismometer = None
            self._current_sei_config = None
        if wanted and self._graph_splitter.indexOf(self._seismic_graph) < 0:
            self._graph_splitter.addWidget(self._seismic_graph)
        self._seismic_graph.setVisible(wanted)
        self._expand_graphs()
        if not wanted or self._seismometer is not None:
            return
        port, freq, offset, span_range, baud = cfg
        if not port:
            self._status_panel.add_message(T("sei_pas_de_port"), Colors.STATUS_WARNING)
            return
        sei = Seismometer(port=port, frequency_hz=freq, offset=offset,
                          data_range=span_range, baudrate=baud)
        sei.set_callback(self.seismic_received.emit)
        if not sei.start():
            self._status_panel.add_message(
                T("sei_echec").format(port=port, e=sei.error), Colors.STATUS_ERROR)
            return
        self._seismometer = sei
        self._current_sei_config = cfg
        self._status_panel.add_message(
            T("sei_demarre").format(port=port, baud=baud), Colors.STATUS_OK)
        n0 = self._last_seismic()
        QTimer.singleShot(15_000, lambda s=sei, n=n0: self._check_seismometer(s, n))

    def _last_seismic(self) -> float:
        try:
            t, _ = self._processor.seismic_buffer.get_last_n(1)
            return float(t[-1]) if len(t) else 0.0
        except Exception:
            return 0.0

    def _check_seismometer(self, sei, n0):
        if sei is not self._seismometer or not self._processor:
            return
        if self._last_seismic() <= n0:
            self._status_panel.add_message(
                T("sei_muet").format(port=self._settings.get("seismometer_port")),
                Colors.STATUS_WARNING)
        self._sei_lost_shown = False
        QTimer.singleShot(60_000, lambda s=sei: self._watch_seismometer(s))

    def _watch_seismometer(self, sei):
        """Every minute: a port lost in the night (adapter unplugged) is
        said once, and so is its return -- it was only checked 15 s after
        the start."""
        if sei is not self._seismometer:
            return
        lost = bool(getattr(sei, "lost", False))
        if lost != getattr(self, "_sei_lost_shown", False):
            self._sei_lost_shown = lost
            port = self._settings.get("seismometer_port")
            if lost:
                self._status_panel.add_message(
                    T("sei_perdu").format(port=port, e=sei.error), Colors.STATUS_ERROR)
            else:
                self._status_panel.add_message(
                    T("sei_demarre").format(port=port, baud=self._seismometer_config()[4]),
                    Colors.STATUS_OK)
        QTimer.singleShot(60_000, lambda s=sei: self._watch_seismometer(s))

    def _displayed_ra_tolerance(self) -> float:
        """RA tolerance in the displayed unit: the setting is in arcseconds
        of RA; in hours mode it is shown, and compared, in seconds of time."""
        tol = float(self._settings.get("tolerance_ra_arcsec") or 0.0)
        return tol if self._settings.get("ra_in_degrees") else tol / 15.0

    def _span(self) -> float:
        """Seconds shown by the scrolling graphs (View > Time span)."""
        return shown_span(self._settings.get("time_span_s"))

    def _clock_drift(self):
        """Clock drift in ms/h, fitted on the last half hour, recomputed
        at most every 5 s (it is a slope, it does not move faster)."""
        now = time.monotonic()
        cache = getattr(self, '_drift_cache', None)
        if cache is not None and now - cache[0] < 5.0:
            return cache[1]
        try:
            t, v, _, _ = self._processor.time_diff_buffer.get_tail(1800.0)
            d = clock_drift(t, v)
        except Exception as e:
            logger.debug(f"Clock drift: {e}")
            d = None
        self._drift_cache = (now, d)
        return d

    def _set_span(self, seconds: float):
        self._settings.set("time_span_s", float(seconds))
        self._save_settings()
        self._refresh_graphs_now()

    def _fill_span_menu(self, menu):
        group = QActionGroup(menu)
        current_value = self._span()
        for s in SPANS_S:
            a = QAction(span_name(s), menu)
            a.setCheckable(True)
            a.setChecked(abs(s - current_value) < 0.5)
            a.triggered.connect(lambda checked, s=s: self._set_span(s))
            group.addAction(a)
            menu.addAction(a)
        # Rebuilt on opening, so the tick follows a change made elsewhere.
        menu.aboutToShow.connect(lambda m=menu: [
            a.setChecked(abs(s - self._span()) < 0.5)
            for a, s in zip(m.actions(), SPANS_S)])

    def _fill_vertical_menu(self, menu):
        group = QActionGroup(menu)
        modes = [("data", T("zoom_data")), ("tolerance", T("zoom_tolerance")),
                 ("maximum", T("zoom_maximum")), ("minmax", T("zoom_minmax"))]
        for mode, label in modes:
            a = QAction(label, menu)
            a.setCheckable(True)
            a.triggered.connect(lambda checked, m=mode: self._set_vertical_zoom(m))
            group.addAction(a)
            menu.addAction(a)
        menu.aboutToShow.connect(lambda m=menu: [
            a.setChecked(mode == (self._settings.get("vertical_zoom_mode") or "data"))
            for a, (mode, _) in zip(m.actions(), modes)])

    def _wire_graph_menus(self):
        """Right click on a graph: our menu, not pyqtgraph's.

        pyqtgraph's own menu offered « X axis / Y axis » ranges that the
        next refresh, a quarter of a second later, overwrote: the span
        looked settable and never stayed.
        """
        for graph in (self._ra_graph, self._dec_graph, self._time_graph,
                       self._seismic_graph, self._axial_graph):
            plot = graph._plot
            plot.setMenuEnabled(False)
            # No wheel or drag zoom: the next refresh undid it a moment
            # later (a touchpad scroll zoomed the graphs for an instant).
            # The span is set from the menus.
            plot.setMouseEnabled(x=False, y=False)
            plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            plot.customContextMenuRequested.connect(
                lambda pos, g=graph: self._graph_menu(g, pos))

    def _graph_menu(self, graph, pos):
        menu = QMenu(self)
        self._fill_span_menu(menu.addMenu(T("time_span")))
        if graph in (self._ra_graph, self._dec_graph):
            self._fill_vertical_menu(menu.addMenu(T("vertical_zoom")))
        menu.exec(graph._plot.mapToGlobal(pos))

    def _set_horizontal_zoom(self, zoom: int):
        """Apply the horizontal zoom to the graphs, and remember it.

        Until now it was only saved: the menu existed, the setting was
        stored, and the display took no account of it.
        """
        self._settings.set("horizontal_zoom", zoom)
        self._save_settings()
        self._apply_horizontal_zoom(zoom)

    def _apply_horizontal_zoom(self, zoom: int):
        for graph in (self._ra_graph, self._dec_graph,
                       self._time_graph, self._seismic_graph):
            graph._horizontal_zoom = zoom

    def _set_vertical_zoom(self, mode: str, save: bool = True):
        self._ra_graph.set_vertical_zoom(mode)
        self._dec_graph.set_vertical_zoom(mode)
        if save:
            self._settings.set("vertical_zoom_mode", mode)
            self._save_settings()
            self._refresh_graphs_now()

    def _reset_minmax(self):
        self._processor.reset_minmax()
        self._status_panel.add_message(T("reset_minmax"))

    def _reset_buffers(self, minmax: bool = False):
        """Empty the graphs' buffers. While the poller runs, done in its
        thread between two samples: from the GUI thread a reset falling
        between the append and the median of a sample gave a reference of
        0 and a 10^5" spike that pinned min/max for the night."""
        processor = self._processor

        def reset(_connection=None):
            processor.reset_buffers()
            if minmax:
                processor.reset_minmax()

        poller = self._poller
        if poller is not None and poller.isRunning():
            poller.submit(reset)
        else:
            reset()
        self._ra_graph.reset()
        self._dec_graph.reset()
        self._time_graph.reset()
        self._seismic_graph.reset()
        self._axial_graph.reset()
        self._status_panel.add_message(T("reset_buffers"))

    def _reset_both(self):
        self._reset_buffers(minmax=True)
        self._status_panel.add_message(T("reset_both"))

    # ── Preferences ──────────────────────────────────────────────

    def _site(self):
        """Observing site as (lat, lon east, elevation), or None.

        The mount is trusted first and the preferences fill in. Note the
        sign: LX200 reports longitude positive WEST, so a site east of
        Greenwich comes back negative and must be flipped -- getting it
        wrong moves the observatory and shifts every twilight.
        """
        site = self._site_from_mount()
        if site:
            return site
        lat_p = self._settings.get("site_latitude")
        lon_p = self._settings.get("site_longitude")
        if lat_p not in (None, "") and lon_p not in (None, ""):
            try:
                elev = float(self._settings.get("site_elevation_m") or 0.0)
            except (TypeError, ValueError):
                elev = 0.0
            return float(lat_p), float(lon_p), elev
        return None

    def _site_from_mount(self):
        """(lat, lon east, elevation) as reported by the mount, or None."""
        from ..core.ephemerides import parse_latitude_lx200, parse_longitude_lx200
        if not self._mount_site:
            return None
        lat_t, lon_t, elev = self._mount_site
        lat = parse_latitude_lx200(lat_t)
        lon = parse_longitude_lx200(lon_t)
        if lat is None or lon is None:
            return None
        return lat, lon, (elev if elev is not None else 0.0)

    def _remember_site(self):
        """Keep the mount's site in the preferences.

        The fields there are the fallback for a mount or driver that does
        not report its site; filled from the mount they also serve when a
        night is replayed with no mount connected.
        """
        site = self._site_from_mount()
        if not site:
            return
        lat, lon, elev = site
        self._settings.set("site_latitude", f"{lat:.5f}")
        self._settings.set("site_longitude", f"{lon:.5f}")
        self._settings.set("site_elevation_m", f"{elev:.0f}")
        try:
            self._save_settings()
        except OSError as exc:
            logger.warning(f"Could not save the site: {exc}")

    def _announce_night(self):
        """Post tonight's twilights to the status panel."""
        site = self._site()
        if not site:
            return
        from ..core.ephemerides import night_around
        from datetime import datetime, timezone
        lat, lon, _ = site
        try:
            n = night_around(datetime.now(timezone.utc), lat, lon)
        except Exception as exc:
            logger.error(f"Ephemeris failed: {exc}")
            return

        def hl(t):
            return t.astimezone().strftime('%H:%M') if t else '--:--'

        if n.sun_always_up:
            self._status_panel.add_message(T("nuit_jour_permanent"))
            return
        self._status_panel.add_message(
            f"{T('nuit_coucher')} {hl(n.sunset)}  |  "
            f"{T('nuit_nautique')} {hl(n.nautical)}  |  "
            f"{T('nuit_lever')} {hl(n.sunrise)}")
        if n.astro_dark:
            d = n.dark_duration
            hours = int(d.total_seconds() // 3600)
            mins = int((d.total_seconds() % 3600) // 60)
            self._status_panel.add_message(
                f"{T('nuit_noire')} {hl(n.astro_start)} \u2192 {hl(n.astro_end)} "
                f"({hours} h {mins:02d})", Colors.STATUS_OK)
        else:
            self._status_panel.add_message(T("nuit_pas_de_nuit_noire"))

    def _choose_language(self, code: str):
        """Change the interface language.

        Nothing is retranslated in place: the menus, labels and tooltips are
        built once at startup, so changing the language only takes effect on
        the next run. Saying so -- and offering the restart -- is the whole
        point, because silently doing nothing is what made the option look
        like it did not exist.
        """
        if code == self._settings.get("language"):
            return
        self._settings.set("language", code)
        self._save_settings()
        set_language(code)
        self._warn_restart()

    def _warn_restart(self):
        """Tell the user the new language needs a restart, and offer it."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(T("lang_restart_titre"))
        box.setText(T("lang_restart_texte"))
        if self._logging_active:
            # Restarting would end the session and write the night report in
            # the middle of the night. Not offered.
            box.setInformativeText(T("lang_restart_bloque"))
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()
            return
        now = box.addButton(T("lang_restart_now"),
                                     QMessageBox.ButtonRole.AcceptRole)
        box.addButton(T("lang_restart_later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self._restart()

    def _restart(self):
        """Relaunch the application in place."""
        import os
        import subprocess
        try:
            self.close()
            env = dict(os.environ, KIT_RELANCE='1')
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable] + sys.argv[1:], env=env)
            else:
                subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])]
                                 + sys.argv[1:], env=env)
        except Exception as exc:
            logger.error(f"Restart failed: {exc}")
            return
        QApplication.quit()

    def _show_preferences(self):
        """Show preferences dialog."""
        before = self._settings.get("language")
        dialog = PreferencesDialog(
            self._settings, self,
            mount_site=self._site_from_mount() if self._connected else None)
        if dialog.exec():
            self._apply_settings()
            # Check the mount at once with the new expectations, as
            # MountMonitor 3 does, rather than at the next slew or period.
            if self._connected:
                self._run_mount_checks(force=True)
            # The language combo also lives in Preferences. Changing it there
            # must say the same thing as the Language menu, otherwise it is
            # again an option that appears to do nothing.
            if self._settings.get("language") != before:
                self._warn_restart()

    def _apply_settings(self):
        """Apply changed settings to running components."""
        set_language(self._settings.get("language"))
        for graph in (self._ra_graph, self._dec_graph):
            graph.set_smooth(self._settings.get("smooth_curves"))

        if self._processor:
            self._processor.set_tolerances(
                self._settings.get("tolerance_ra_arcsec"),
                self._settings.get("tolerance_dec_arcsec"),
                self._settings.get("tolerance_seismic_percent"),
            )
            self._processor.set_running_range(self._settings.get("running_range_seconds"))
            self._processor.set_reference_mode(self._settings.get("reference_mode"))
        self._target_asked_at = None          # mode may have just changed: read the target now

        if self._poller:
            self._poller.set_frequency(self._settings.get("polling_frequency_hz"))
            self._poller.set_axial_enabled(self._axial_mode() != "off")
            self._poller.set_log_tracking_only(self._settings.get("log_mode") == "tracking_only")
            # Was only read at connection: a delay changed while connected
            # was ignored until the next connection.
            self._poller.set_delay_after_slew(self._settings.get("delay_after_slew_seconds"))
        self._axial_graph.setVisible(self._axial_mode() != "off")
        self._expand_graphs()

        if self._ntp_client and self._settings.get("ntp_enabled"):
            self._ntp_client.set_server(self._settings.get("ntp_server"))
            self._ntp_client.set_interval(self._settings.get("ntp_interval_seconds"))

        self._ra_graph.set_tolerance(self._settings.get("tolerance_ra_arcsec"))
        self._dec_graph.set_tolerance(self._settings.get("tolerance_dec_arcsec"))

        self._status_panel.set_ra_in_degrees(self._settings.get("ra_in_degrees"))
        self._arm_periodic_check()
        self._apply_seismometer()
        self._refresh_graphs_now()

        # Update status panel tolerance display
        self._status_panel.set_tolerances(
            self._settings.get("tolerance_ra_arcsec"),
            self._settings.get("tolerance_dec_arcsec"),
        )

    # ── Graph dump ─────────────────────────────────────────────

    def _check_graph_full(self):
        """Save the graphs when the width has filled with new data.

        This is the Java MountMonitor behaviour: « MountMonitor outputs
        the graphs automatically each time the window width is filled with
        new data ». It leaves a continuous photographic log of the night,
        without having to replay anything the next day.

        The criterion: the displayed window has been entirely renewed since
        the last export, i.e. the last sample has moved forward by one
        window width. Each image thus shows a different piece of the
        night, with no gap or overlap.

        🔴 It used to count the buffer samples. But the buffer is circular
        and capped at 50,000: once full, its size no longer changes, and
        the log stopped in the middle of the night without a word.
        """
        # Every automatic mode dumps on filling, as MountMonitor 3; parking
        # and slewing only add their own dumps on top.
        if self._settings.get("dump_mode") not in ("full", "parking", "slewing"):
            return
        try:
            t, _ = self._processor.ra_buffer.get_arrays()
        except Exception:
            return
        if len(t) == 0:
            return
        end = float(t[-1])
        span = self._span()
        started = getattr(self, '_last_dump_time', None)
        if started is None or end < started:
            self._last_dump_time = end
            return
        if end - started >= span:
            self._last_dump_time = end
            self._dump_graphs()

    def _dump_graphs(self):
        """Export all graph images, in folders next to the log files.

        They went to the current directory: in the installed program that
        is the application folder, wiped by every update, and from the Task
        Scheduler it is System32, where mkdir raised -- inside the parking
        handler, which then never closed the night. Each export is now
        guarded on its own."""
        base = Path(self._file_logger.log_dir)
        jobs = [(self._ra_graph, "RA_graphs"), (self._dec_graph, "DEC_graphs"),
                (self._time_graph, "Time_graphs"), (self._seismic_graph, "Seismic_graphs")]
        if self._axial_mode() != "off":
            jobs.append((self._axial_graph, "Axial_graphs"))
        if self._fft_window and self._fft_window.isVisible():
            jobs.append((self._fft_window, "FFT_graphs"))
        failed = None
        for graph, folder in jobs:
            try:
                graph.export_to_image(str(base / folder))
            except Exception as e:          # disk full, folder not writable
                failed = e
                logger.warning(f"Graph export to {folder} failed: {e}")
        # The next dump on filling comes one full width after this one,
        # whatever triggered it (slew, park, by hand): no near-duplicate.
        try:
            t, _ = self._processor.ra_buffer.get_arrays()
            if len(t):
                self._last_dump_time = float(t[-1])
        except Exception:
            pass
        if failed is not None:
            self._status_panel.add_message(f"\u26a0 {T('graphs_exported')} : {failed}",
                                           Colors.STATUS_WARNING)
        else:
            self._status_panel.add_message(T("graphs_exported"))

    # ── Mount checks ────────────────────────────────────────────

    def _periodic_check(self):
        """Mount settings checked again every few minutes, not only at
        connection and after a slew: a setting changed on the keypad in the
        middle of a target went unnoticed until the next slew."""
        if self._connected and self._connection:
            self._run_mount_checks(force=False)

    def _arm_periodic_check(self):
        minutes = float(self._settings.get("mount_check_interval_min") or 0)
        t = getattr(self, '_checks_timer', None)
        if t is None:
            t = self._checks_timer = QTimer(self)
            t.timeout.connect(self._periodic_check)
        if minutes > 0:
            t.start(int(minutes * 60_000))
        else:
            t.stop()

    def _run_mount_checks(self, force: bool = True):
        """Run mount setting checks based on preferences.

        Checks refraction, tracking rate, GPS sync as configured in
        the Miscellaneous tab. The mount is read in the poller thread (up to
        five commands, each with a 5 s timeout, used to freeze the window);
        the results are judged and shown here.
        """
        if not self._connection or not self._connected:
            return
        cfg = {k: self._settings.get(k) for k in (
            "check_refraction_status",
            "check_refraction_enabled", "check_tracking_rate",
            "check_gps_sync", "check_dual_tracking")}
        # A parked mount still reports its CONFIGURED tracking rate, so the
        # check passed and printed « Tracking rate: Sidereal OK » next to a
        # mount that was not tracking at all. Rate-dependent checks are
        # skipped unless the mount is actually tracking.
        tracking_gui = getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING

        def read(c):
            r = {}
            # The status is read here, with the checks. The window's own copy
            # lags right after connecting (still UNKNOWN), which printed
            # "Mount parked: tracking checks skipped" one second after
            # "Mount is tracking: recording started".
            status = c.get_status() if cfg["check_tracking_rate"] else None
            tracking_now = (status == MountStatus.TRACKING if status not in
                            (None, MountStatus.UNKNOWN) else tracking_gui)
            r["tracking"] = tracking_now
            if cfg["check_refraction_status"]:
                r["refraction"] = c.is_refraction_enabled()
            if cfg["check_refraction_enabled"]:
                r["mode"] = c.get_refraction_mode()
            if tracking_now and cfg["check_tracking_rate"]:
                r["rate"] = c.get_tracking_rate()
                # Follow object, tracking correction and speed from the
                # mount's preference list, as MountMonitor 3 does.
                r["prefs"] = c.check_mount_settings()
                r["prefs_refused"] = bool(getattr(c, "preferences_refused", False))
                r["prefs_pure_ascom"] = bool(getattr(c, "preferences_pure_ascom", False))
            if cfg["check_gps_sync"]:
                r["gps"] = c.is_gps_synced()
            if cfg["check_dual_tracking"]:
                r["dual"] = c.is_dual_tracking_enabled()
            return r

        self._mount_request(read, lambda r: self._judge_checks(
            r or {}, (r or {}).get("tracking", tracking_gui), force))

    def _judge_checks(self, r: dict, tracking_now: bool, force: bool = True):
        warnings = []
        ok_checks = []

        # Refraction correction on/off (:GREF#)
        if self._settings.get("check_refraction_status") and r.get("refraction") is not None:
            expected_val = self._settings.get("check_refraction_status_value") or "enabled"
            actual = "enabled" if r["refraction"] else "disabled"
            if actual == expected_val:
                # "correction" is feminine in French: activée, désactivée
                ok_checks.append(T("chk_refr_status_ok").format(v=T(f"val_{actual}_f")) + " \u2713")
            else:
                warnings.append(T("chk_refr_status_ko").format(
                    a=T(f"val_{actual}_f"), e=T(f"val_{expected_val}_f")))

        # Refraction update mode (:WSG#: not_updating, not_updating_tracking,
        # continuously_updating). Pointless when the correction is off.
        if self._settings.get("check_refraction_enabled") and r.get("refraction") is not False:
            expected = self._settings.get("check_refraction_value")
            mode = r.get("mode")
            if mode is not None:
                # Shown in the user's language, with the words of the
                # preferences (the raw keys "not updating" appeared in
                # English inside French sentences).
                names = {"not_updating": "refraction_not_updating",
                         "not_updating_tracking": "refraction_not_tracking",
                         "continuously_updating": "refraction_continuous"}

                def shown(m):
                    return T(names[m]) if m in names else str(m).replace('_', ' ')
                if mode == expected:
                    ok_checks.append(T("chk_refraction_ok").format(v=shown(mode)) + " \u2713")
                else:
                    warnings.append(
                        T("chk_refraction_ko").format(a=shown(mode), e=shown(expected))
                    )

        # Check GPS sync
        if self._settings.get("check_gps_sync") and r.get("gps") is not None:
            expected_val = self._settings.get("check_gps_sync_value")
            actual = "synchronising" if r["gps"] else "not synchronising"
            gps_names = {"synchronising": T("val_sync"), "not synchronising": T("val_nosync")}
            if actual == expected_val:
                ok_checks.append(T("chk_gps_ok").format(v=gps_names[actual]) + " \u2713")
            else:
                warnings.append(T("chk_gps_ko").format(
                    a=gps_names[actual], e=gps_names.get(expected_val, expected_val)))

        # Check dual tracking
        if self._settings.get("check_dual_tracking") and r.get("dual") is not None:
            expected_val = self._settings.get("check_dual_tracking_value")
            actual = "enabled" if r["dual"] else "disabled"
            if actual == expected_val:
                ok_checks.append(T("chk_dual_ok").format(v=T(f"val_{actual}")) + " \u2713")
            else:
                warnings.append(T("chk_dual_ko").format(
                    a=T(f"val_{actual}"), e=T(f"val_{expected_val}")))

        # Follow object on, and allowed (expected rate not sidereal): the
        # mount then tracks at the object's own rate, shown as speed
        # "Custom" in its preference list and as a non-standard :GT# rate.
        # Neither is then a wrong setting.
        prefs = r.get("prefs") if tracking_now else None
        expected = (self._settings.get("check_tracking_rate_value") or "sidereal").lower()
        following = bool(prefs and prefs.get("follow_object") and expected != "sidereal")

        # Check tracking rate
        if not tracking_now:
            ok_checks.append(T("chk_parked"))
        if tracking_now and self._settings.get("check_tracking_rate"):
            expected_val = self._settings.get("check_tracking_rate_value")
            rate = r.get("rate")
            if rate is not None:
                from ..core.mount_connection import classify_tracking_rate
                name = classify_tracking_rate(rate)
                read_value = T(f"val_{name}") if name else f"{rate}"
                if name == (expected_val or "").lower():
                    ok_checks.append(T("chk_rate_ok").format(v=read_value) + " \u2713")
                elif following and name != "sidereal":
                    pass                # the object's rate, reported below
                else:
                    warnings.append(T("chk_rate_ko").format(a=read_value, e=T(f"val_{expected_val}")))

        # Mount preference list (:PRlist#): follow object off, tracking
        # correction 0.000 %, tracking speed Sidereal.
        if not prefs and r.get("prefs_refused") and tracking_now:
            # Said once per check, as information: not a wrong setting.
            ok_checks.append(T("chk_prefs_refused"))
        elif not prefs and r.get("prefs_pure_ascom") and tracking_now:
            ok_checks.append(T("chk_prefs_pure_ascom"))
        if prefs and self._settings.get("check_tracking_rate"):
            if "follow_object" in prefs:
                if not prefs["follow_object"]:
                    ok_checks.append(T("chk_follow_ok") + " \u2713")
                elif expected != "sidereal":
                    # First departure from MountMonitor 3: Follow object is
                    # how the mount tracks the Sun or a planet. Expected only
                    # with a sidereal rate; with solar or lunar it is allowed.
                    ok_checks.append(T("chk_follow_allowed").format(e=T(f"val_{expected}"))
                                     + " \u2713")
                else:
                    warnings.append(T("chk_follow_ko"))
            corr = prefs.get("tracking_correction")
            if corr is not None:
                try:
                    zero = abs(float(corr)) < 1e-9
                except ValueError:
                    zero = False
                if zero:
                    ok_checks.append(T("chk_corr_ok").format(v=corr) + " \u2713")
                else:
                    warnings.append(T("chk_corr_ko").format(v=corr))
            speed = prefs.get("tracking_speed")
            if following and speed is not None and speed.lower() == "custom":
                ok_checks.append(T("chk_speed_follow").format(
                    ra=prefs.get("custom_rate_ra", "?"),
                    dec=prefs.get("custom_rate_dec", "?")) + " \u2713")
            elif speed is not None and speed.lower() != expected \
                    and not any(T(f"val_{speed.lower()}") in w for w in warnings):
                warnings.append(T("chk_speed_ko").format(a=speed, e=T(f"val_{expected}")))

        # Display results. The periodic check (every few minutes) writes to
        # the history only when the outcome changes, not every time.
        summary = (tuple(ok_checks), tuple(warnings))
        changed = summary != getattr(self, '_last_checks_summary', None)
        self._last_checks_summary = summary
        if (changed or force) and (ok_checks or warnings):
            for msg in ok_checks:
                self._status_panel.add_message(msg, Colors.STATUS_OK)
                if self._logging_active:
                    self._file_logger.log_event(f"Check OK: {msg}")
            for msg in warnings:
                self._status_panel.add_message(f"\u26a0 {msg}", Colors.STATUS_WARNING)
                if self._logging_active:
                    self._file_logger.log_event(f"Check WARNING: {msg}")
            # Marker written last: the history shows the newest line on top,
            # so it heads the block of results (suggestion of N. de Hilster).
            self._status_panel.add_message(T("chk_header"), Colors.TEXT_SECONDARY)
        if warnings:
            self._mount_alert(warnings)
        else:
            box = getattr(self, "_alert_box", None)
            if box is not None and box.isVisible():
                box.hide()          # put right: the alert goes by itself

    def _mount_alert(self, warnings: list):
        """ONE non-modal box, updated in place.

        A modal box per end of slew piled up all night in front of an empty
        chair, each one a nested event loop."""
        if not self._settings.get("mount_alert_popup"):
            return
        text = (T("mount_alert_text") + "\n\n" + "\n".join(f"\u26a0 {w}" for w in warnings)
                 + "\n\n" + T("mount_alert_disable"))
        box = getattr(self, "_alert_box", None)
        if box is None:
            # Top-level, without owner: Windows only moves an owner-less
            # window to another virtual desktop (see bring_alert_to_user).
            box = QMessageBox(None)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(T("mount_alert_title"))
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setModal(False)
            # On top of the other windows, even when MountMonitor is behind
            # NINA: a wrong mount setting spoils the night, it must be seen.
            box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._alert_box = box
        box.setText(text)
        box.show()
        box.raise_()
        box.activateWindow()
        # Taskbar / dock flashes until the window is looked at.
        QApplication.alert(self, 0)
        QApplication.alert(box, 0)
        # MountMonitor on another virtual desktop (Windows): the alert comes
        # to the desktop the user is on, or Windows switches to ours.
        from ..utils.win_desktop import bring_alert_to_user
        where = bring_alert_to_user(int(box.winId()))
        if where:
            logger.info(f"Mount alert brought to the user ({where})")

    # ── Help ─────────────────────────────────────────────────────

    def _open_manual(self):
        """Open the PDF manual for the current language.

        It ships in app/docs next to the program; without a menu entry
        nobody would ever find it there.
        """
        import subprocess
        import webbrowser
        lang = get_language()
        base = Path(__file__).resolve().parent.parent.parent / "docs"
        path = base / f"manual_{lang}.pdf"
        if not path.exists():
            path = base / "manual_en.pdf"
        if not path.exists():
            QMessageBox.information(self, T("menu_manual"), T("manual_absent"))
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            # xdg-open may simply be absent on a bare Linux install.
            webbrowser.open(path.as_uri())

    def _show_help(self):
        """Show the help document, in the user's language.

        The text lived here as two hard-coded strings, English and French,
        still describing version 1.6. It now sits in help_texts, in three
        languages, and is scrollable: a QMessageBox silently truncates a
        document this long.
        """
        from .help_texts import help_html, TITLE
        lang = get_language()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{TITLE.get(lang, TITLE['en'])} — MountMonitor")
        dlg.resize(760, 620)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser(dlg)
        view.setOpenExternalLinks(False)
        view.setHtml(help_html(lang, self._version))
        lay.addWidget(view)
        buttons_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
        buttons_box.rejected.connect(dlg.reject)
        buttons_box.accepted.connect(dlg.accept)
        lay.addWidget(buttons_box)
        dlg.exec()

    def _show_about(self):
        """Show about dialog, in the interface language, with the logo
        (same source as the icon: logo.svg)."""
        box = QMessageBox(self)
        box.setWindowTitle(T("menu_about"))
        try:
            from kit_aide import logo_a_propos
            logo_a_propos(box, Path(__file__).resolve().parent.parent.parent / "logo_128.png")
        except Exception:
            pass
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(T("about_texte").format(v=self._version))
        box.exec()

    def _show_online_help(self):
        """Open online help / documentation in browser."""
        import webbrowser
        webbrowser.open("https://github.com/ARP273-ROSE/MountMonitor")

    def _report_bug(self):
        """Open bug report dialog with pre-filled template and system info."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        import webbrowser
        from urllib.parse import quote

        lang = get_language()

        dlg = QDialog(self)
        dlg.setWindowTitle(T("bug_report_title"))
        dlg.setMinimumSize(500, 350)
        layout = QVBoxLayout(dlg)

        # Info label
        info = QLabel(T("bug_report_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        # Description label
        desc_label = QLabel(T("bug_report_description"))
        layout.addWidget(desc_label)

        # Description text edit
        desc_edit = QTextEdit()
        desc_edit.setPlaceholderText(T("tt_bug_desc"))
        layout.addWidget(desc_edit)

        # Buttons
        buttons = QDialogButtonBox()
        send_btn = buttons.addButton(
            T("bug_report_send"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        send_btn.setToolTip(T("tt_bug_prefilled"))
        cancel_btn = buttons.addButton(
            T("bug_report_cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        cancel_btn.setToolTip(T("tt_bug_cancel"))
        layout.addWidget(buttons)

        def on_accept():
            dlg.accept()
            crash_reporter = CrashReporter()
            body = crash_reporter.format_bug_report(desc_edit.toPlainText().strip())
            # URL-encode and open in browser
            encoded_body = quote(body, safe='')
            title = quote("Bug Report", safe='')
            url = (
                f"https://github.com/{GITHUB_REPO}/issues/new"
                f"?title={title}&body={encoded_body}"
            )
            webbrowser.open(url)

        buttons.accepted.connect(on_accept)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    # ── Auto-update ──────────────────────────────────────────────

    def _check_updates_silent(self):
        """Discreet check at startup: nothing is shown if all is well."""
        self._start_update_check(manual=False)

    def _check_updates_manual(self):
        """Check requested from the Help menu: always answered."""
        self.statusBar().showMessage(T("update_checking"), 5000)
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool):
        """Query GitHub in a background thread."""
        if getattr(self, '_check_in_progress', False):
            return
        self._check_in_progress = True

        def _query():
            found = None
            try:
                if updater.is_packaged():
                    found = updater.check(self._version)
                elif manual:
                    found = 'sources'
            except Exception:
                logger.debug("Update check failed",
                             exc_info=True)
            self.update_found.emit((found, manual))

        threading.Thread(target=_query, daemon=True,
                         name='verif-maj').start()

    def _on_update_found(self, result):
        """Result of the check, on the GUI thread."""
        found, manual = result
        self._check_in_progress = False

        if found == 'sources':
            QMessageBox.information(
                self, T("menu_check_updates"),
                T("tt_upd_source"))
            return

        if not found:
            if manual:
                QMessageBox.information(
                    self, T("menu_check_updates"),
                    T("update_up_to_date").format(version=self._version))
            return

        self._show_update_dialog(found)

    def _show_update_dialog(self, release_info: dict):
        """Show update available dialog with changelog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

        tag = release_info.get("version", "?")
        body = release_info.get("notes", "") or ""
        size = release_info.get("size", 0)

        # Neither modal nor owned by the window. At the observatory the check
        # runs at logon, unattended (--connect): a modal dialog owned by the
        # main window, left behind it, minimised with it or on another
        # virtual desktop, disabled the window without anything to show for
        # it -- the taskbar button then opened nothing and MountMonitor had
        # to be killed (24/11/2026). Owner-less, the dialog has its own
        # taskbar button and the window stays usable while it waits.
        old = getattr(self, "_update_offer", None)
        if old is not None:
            old.close()
        dlg = QDialog(None)
        dlg.setWindowTitle(T("update_available"))
        dlg.setMinimumSize(500, 400)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._update_offer = dlg
        layout = QVBoxLayout(dlg)

        # Version info
        info_text = (
            f"<h3>{T('update_available')}</h3>"
            f"<p><b>{T('update_current')}:</b> {self._version}<br>"
            f"<b>{T('update_new')}:</b> {tag}"
            + (f" ({size / 1e6:.1f} Mo)" if size else "")
            + "</p>"
        )
        info_label = QLabel(info_text)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        # Changelog
        if body:
            changelog_label = QLabel(f"<b>{T('update_changelog')}:</b>")
            layout.addWidget(changelog_label)
            changelog = QTextEdit()
            changelog.setReadOnly(True)
            changelog.setPlainText(
                updater.notes_dans_la_langue(body, get_language()))
            layout.addWidget(changelog)

        # Buttons
        buttons = QDialogButtonBox()
        download_btn = buttons.addButton(
            T("update_download"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        download_btn.setToolTip(T("tt_upd_install"))
        skip_btn = buttons.addButton(
            T("update_skip"), QDialogButtonBox.ButtonRole.RejectRole
        )
        skip_btn.setToolTip(T("tt_upd_skip"))
        layout.addWidget(buttons)

        def on_download():
            dlg.accept()
            self._apply_update(release_info)

        def forget(*_):
            if getattr(self, "_update_offer", None) is dlg:
                self._update_offer = None

        buttons.accepted.connect(on_download)
        buttons.rejected.connect(dlg.reject)
        dlg.finished.connect(forget)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.alert(dlg, 0)
        try:
            from ..utils.win_desktop import bring_alert_to_user
            bring_alert_to_user(int(dlg.winId()))
        except Exception:
            logger.debug("Update dialog not brought to the user", exc_info=True)

    def _apply_update(self, info: dict):
        """Download the application archive and install it, then restart.

        Nothing executable is downloaded: the module fetches a ZIP archive
        and replaces the files itself, which avoids the SmartScreen
        warning — a downloaded .exe carries the "mark of the web", a file
        written by a program does not.
        """
        from PyQt6.QtWidgets import QProgressDialog

        # The download runs in a thread: done on the GUI thread with
        # processEvents, it froze the window on a slow line and let events
        # re-enter half-way through the replacement of the files.
        dlg = QProgressDialog(T("update_downloading"), None, 0, 100, self)
        dlg.setWindowTitle(T("update_available"))
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._update_dlg = dlg

        def progress(done, total):
            if total:
                self.update_progress.emit(int(done * 100 / total))

        def download():
            try:
                self.update_installed.emit(bool(updater.download_and_apply(info, progress=progress)), "")
            except Exception as e:
                self.update_installed.emit(False, str(e) or e.__class__.__name__)

        threading.Thread(target=download, daemon=True, name="maj-telechargement").start()

    @pyqtSlot(int)
    def _on_update_progress(self, pct: int):
        dlg = getattr(self, "_update_dlg", None)
        if dlg is not None:
            dlg.setValue(pct)

    @pyqtSlot(bool, str)
    def _on_update_installed(self, installed: bool, error: str):
        dlg, self._update_dlg = getattr(self, "_update_dlg", None), None
        if dlg is not None:
            dlg.close()
        if error:
            QMessageBox.warning(
                self, T("update_available"),
                T("tt_upd_failed").format(err=error))
            return
        if not installed:
            QMessageBox.warning(self, T("update_available"), T("update_failed"))
            return

        QMessageBox.information(self, T("update_available"), T("update_success"))

        # The window is closed rather than the application quit: closeEvent
        # stops the poller, writes the session summary and closes the six
        # files of the night. Quitting without going through it would
        # leave a truncated .dat.
        # Closed FIRST, then relaunched: the new instance used to start while
        # this one was still in closeEvent, found the lock taken and stopped
        # on « already open » -- an unattended PC was left without
        # MountMonitor. The new one also waits for the lock (KIT_RELANCE).
        self.close()
        if self.isVisible():                 # closing was refused
            return
        updater.restart()
        QApplication.quit()

    def _create_desktop_shortcut(self):
        """Create a desktop shortcut for MountMonitor."""
        try:
            from shortcut_helper import create_shortcut_force
            create_shortcut_force("MountMonitor", "main.py", "logo.ico")
        except Exception as e:
            QMessageBox.warning(self,
                T("menu_create_shortcut"),
                T("erreur_prefixe") + str(e))

    # ── Window lifecycle ─────────────────────────────────────────

    def _restore_panels(self):
        """Put the splitters back where the user last left them."""
        from PyQt6.QtCore import QByteArray
        for key, sp in (("splitter_graphs", getattr(self, '_graph_splitter', None)),
                        ("splitter_main", getattr(self, '_h_splitter', None))):
            state = self._settings.get(key)
            if sp is not None and state:
                try:
                    sp.restoreState(QByteArray.fromBase64(state.encode('ascii')))
                except Exception as exc:
                    logger.debug(f"Splitter {key} not restored: {exc}")
        self._expand_graphs()

    def _expand_graphs(self):
        """No shown graph squeezed to nothing.

        The layout saved by a session with three graphs gave the fourth
        (seismometer, axial) a height of zero once restored: enabled, fed,
        and invisible -- « nothing happens ». Any shown graph lower than
        60 px gets an equal share again.
        """
        sp = getattr(self, '_graph_splitter', None)
        if sp is None or sp.count() == 0:
            return
        sp.setChildrenCollapsible(False)
        sizes = sp.sizes()
        shown_idx = [i for i in range(sp.count()) if not sp.widget(i).isHidden()]
        if not shown_idx or all(sizes[i] >= 60 for i in shown_idx):
            return
        total = sum(sizes[i] for i in shown_idx) or 400 * len(shown_idx)
        part = total // len(shown_idx)
        sp.setSizes([part if i in shown_idx else 0 for i in range(sp.count())])

    def _save_panels(self):
        for key, sp in (("splitter_graphs", getattr(self, '_graph_splitter', None)),
                        ("splitter_main", getattr(self, '_h_splitter', None))):
            if sp is not None:
                self._settings.set(key, bytes(sp.saveState().toBase64()).decode('ascii'))

    def closeEvent(self, event):
        """Handle window close: save settings, stop everything."""
        self._closing = True        # pollers are waited for, not released
        # The alert box has no owner: closed by hand, or it would keep the
        # application alive after the main window.
        for box in (getattr(self, "_alert_box", None),
                    getattr(self, "_update_offer", None)):
            if box is not None:
                box.close()
        # Save window geometry
        self._settings.set("window_width", self.width())
        self._settings.set("window_height", self.height())
        self._settings.set("window_x", self.x())
        self._settings.set("window_y", self.y())
        if self._fft_window:
            self._settings.set("fft_width", self._fft_window.width())
            self._settings.set("fft_height", self._fft_window.height())
        self._save_panels()
        # Disk full: the settings are lost, the night must not be --
        # stopping the poller and closing the files comes next.
        self._save_settings()

        # Stop everything
        self._disconnect()
        if self._connecting and self._poller is not None:
            poller, self._poller = self._poller, None
            self._release_poller(poller)

        # The night report is written in a background thread: let it finish
        # (the files are on disk already, this is only the report), and never
        # let a running QThread be destroyed -- that aborts the process.
        for job in list(self._night_jobs.values()) + [getattr(self, "_replay_job", None)]:
            if job is not None:
                try:
                    job.wait(120_000)
                except RuntimeError:
                    pass
        for poller in list(self._finishing_pollers):
            poller.wait(5000)

        if self._fft_window:
            self._fft_window.close()

        event.accept()
