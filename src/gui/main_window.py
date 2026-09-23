"""Main window for MountMonitor.

Assembles all components: graphs, status panel, menus, toolbar.
Manages the connection lifecycle and data flow.
"""

import os
import sys
import logging
import threading
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
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QFont, QIcon, QKeySequence

from .graph_widgets import TrackingGraph, TimeGraph, SeismicGraph, AxialGraph
from .fft_window import FFTWindow
from .analysis_dialog import AnalysisDialog, sauver_rapport
from .log10m_dialog import Log10mAnalysisDialog
from .status_panel import StatusPanel
from .preferences_dialog import PreferencesDialog
from .theme import Colors
from ..config.settings import Settings
from ..core.mount_connection import MountConnection
from ..core.lx200_protocol import LX200Connection
from ..core.lx200_serial import LX200SerialConnection
from ..core.ascom_connection import ASCOMConnection
from ..core.data_processor import DataProcessor
from ..core.poller import MountPoller
from ..core.ntp_client import NTPClient
from ..core.seismometer import Seismometer
from ..simulation.sim_mount import SimulatedMount
from ..simulation.sim_seismometer import SimulatedSeismometer
from ..logging_module.file_logger import FileLogger
from ..logging_module.log_parser import parse_session, list_log_sessions
from ..logging_module.crash_reporter import CrashReporter, anonymize_path, GITHUB_REPO
from ..models.mount_data import MountSample, MountStatus, SessionInfo, ConnectionProtocol
from ..utils.i18n import T, set_language, get_language, LANGUES
from ..utils.coordinates import format_ra, format_dec
# La mise a jour passe par le module commun du kit, a la racine : il va
# chercher l'archive applicative publiee dans le depot public de
# distribution. L'ancien mecanisme telechargeait la zipball du depot de
# code, reste prive : l'API repondait 404 et la mise a jour ne s'est
# jamais declenchee chez personne.
import updater

logger = logging.getLogger(__name__)


def _read_version() -> str:
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "1.0.0"


class MainWindow(QMainWindow):
    """Main application window."""

    # Retour du fil qui interroge GitHub vers le fil graphique.
    #
    # `object` et non `dict` : declare en `dict`, PyQt recopierait la charge
    # champ par champ. Surtout, le retour passe par un signal et jamais par
    # QTimer.singleShot — un minuteur cree dans un fil sans boucle
    # d'evenements ne se declenche jamais, et la reponse serait perdue sans le
    # moindre message.
    maj_trouvee = pyqtSignal(object)

    def __init__(self, sim_mode: str = "none"):
        """Initialize main window.

        Args:
            sim_mode: "none", "mount", "seismometer", or "all"
        """
        super().__init__()
        self._version = _read_version()
        self._sim_mode = sim_mode
        self._settings = Settings()
        self._processor = DataProcessor()
        self._connection: Optional[MountConnection] = None
        self._poller: Optional[MountPoller] = None
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
        self._logging_suspendu = False
        self._nuit_vue = False          # the Sun went below the horizon while recording
        self._aube_timer = None
        # Site as the mount reports it, when it does. Plenty of setups never
        # push their site to the mount -- hence the preference fallback.
        self._site_monture = None
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
        self._refresh_timer.setInterval(250)  # 4 fps graph update (was 100ms/10fps)

        # FFT timer (slower)
        self._fft_timer = QTimer()
        self._fft_timer.timeout.connect(self._update_fft)
        self._fft_timer.setInterval(2000)  # Every 2 seconds

        # Verification des mises a jour, en fond, au demarrage.
        self.maj_trouvee.connect(self._maj_reperee)
        QTimer.singleShot(3000, self._check_updates_silent)

        # Auto-connect in simulation mode
        if sim_mode != "none":
            QTimer.singleShot(500, self._connect)

        self._appliquer_zoom_horizontal(
            self._settings.get("horizontal_zoom") or 1)

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
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu(T("menu_file"))

        connect_action = QAction(T("connecting").rstrip("..."), self)
        connect_action.setShortcut(QKeySequence("Ctrl+K"))
        connect_action.setToolTip(T("tt_connect"))
        connect_action.triggered.connect(self._connect)
        file_menu.addAction(connect_action)
        self._connect_action = connect_action

        disconnect_action = QAction(T("disconnected"), self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+D"))
        disconnect_action.setToolTip(T("tt_disconnect"))
        disconnect_action.triggered.connect(self._disconnect)
        disconnect_action.setEnabled(False)
        file_menu.addAction(disconnect_action)
        self._disconnect_action = disconnect_action

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

        quit_action = QAction(T("menu_quit"), self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu(T("menu_view"))

        # Horizontal zoom submenu
        hz_menu = view_menu.addMenu(T("horizontal_zoom"))
        for zoom in [1, 2, 3, 5, 10]:
            action = QAction(f"{zoom}x", self)
            action.setToolTip(T("tt_zoom_h").format(zoom=zoom))
            action.triggered.connect(lambda checked, z=zoom: self._set_horizontal_zoom(z))
            hz_menu.addAction(action)

        # Vertical zoom submenu
        vz_menu = view_menu.addMenu(T("vertical_zoom"))
        for mode, label in [
            ("data", T("zoom_data")),
            ("tolerance", T("zoom_tolerance")),
            ("maximum", T("zoom_maximum")),
            ("minmax", T("zoom_minmax")),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked, m=mode: self._set_vertical_zoom(m))
            vz_menu.addAction(action)

        view_menu.addSeparator()

        fft_action = QAction(T("fft_title"), self)
        fft_action.setShortcut(QKeySequence("Ctrl+F"))
        fft_action.setToolTip(T("tt_fft_win"))
        fft_action.triggered.connect(self._show_fft)
        view_menu.addAction(fft_action)

        # Reset menu
        reset_menu = menubar.addMenu(T("menu_reset"))

        for label, slot in [
            (T("reset_minmax"), self._reset_minmax),
            (T("reset_buffers"), self._reset_buffers),
            (T("reset_both"), self._reset_both),
            (T("reset_new_files"), self._new_log_files),
            (T("dump_graphs_action"), self._dump_graphs),
        ]:
            action = QAction(label, self)
            action.triggered.connect(slot)
            reset_menu.addAction(action)

        # Edit menu
        edit_menu = menubar.addMenu(T("menu_edit"))
        pref_action = QAction(T("menu_preferences"), self)
        pref_action.setShortcut(QKeySequence("Ctrl+,"))
        pref_action.setToolTip(T("tt_prefs"))
        pref_action.triggered.connect(self._show_preferences)
        edit_menu.addAction(pref_action)

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
        courant = self._settings.get("language") or "auto"
        for code, libelle in [("auto", T("lang_auto"))] + list(LANGUES.items()):
            act = QAction(libelle, self)
            act.setCheckable(True)
            act.setChecked(code == courant)
            act.setData(code)
            act.triggered.connect(lambda _checked, c=code: self._choisir_langue(c))
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
        manual_action.triggered.connect(self._ouvrir_manuel)
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

        update_action = QAction(T("menu_check_updates"), self)
        update_action.setToolTip(T("tt_check_upd"))
        update_action.triggered.connect(self._check_updates_manual)
        help_menu.addAction(update_action)

        help_menu.addSeparator()

        shortcut_action = QAction(T("menu_create_shortcut"), self)
        shortcut_action.triggered.connect(self._create_desktop_shortcut)
        help_menu.addAction(shortcut_action)

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
        toolbar.addWidget(self._btn_logging)

        toolbar.addSeparator()

        btn_fft = QPushButton("FFT")
        btn_fft.setToolTip(T("tt_fft"))
        btn_fft.clicked.connect(self._show_fft)
        toolbar.addWidget(btn_fft)

        btn_prefs = QPushButton(T("menu_preferences"))
        btn_prefs.setToolTip(T("tt_preferences"))
        btn_prefs.clicked.connect(self._show_preferences)
        toolbar.addWidget(btn_prefs)

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
        self._time_graph = TimeGraph()
        self._seismic_graph = SeismicGraph()
        self._axial_graph = AxialGraph()

        graph_splitter.addWidget(self._ra_graph)
        graph_splitter.addWidget(self._dec_graph)
        graph_splitter.addWidget(self._time_graph)

        # Show axial graph if enabled
        if self._settings.get("axial_mode") != "off":
            graph_splitter.addWidget(self._axial_graph)

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
        self._restaurer_panneaux()

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
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        """Connect to the mount."""
        if self._connected:
            return

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
                self._settings.save()
            self._connection = ASCOMConnection(driver_id=driver_id)
        else:
            self._status_panel.add_message(
                f"{T('protocol_not_impl')}: {protocol}", Colors.STATUS_ERROR
            )
            return

        # Connect
        self._status_panel.add_message(T("connecting"))
        if not self._connection.connect():
            self._status_panel.add_message(T("connection_failed"), Colors.STATUS_ERROR)
            return

        self._connected = True
        self._status_panel.set_connected(True)
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
            as_ha_seconds=self._settings.get("tolerance_as_ha_seconds"),
        )

        # Start poller
        self._poller = MountPoller(
            self._connection, self._processor,
            frequency_hz=self._settings.get("polling_frequency_hz"),
        )
        self._poller.set_axial_enabled(self._settings.get("axial_mode") != "off")
        self._poller.set_log_tracking_only(self._settings.get("log_mode") == "tracking_only")
        self._poller.set_delay_after_slew(self._settings.get("delay_after_slew_seconds"))

        # Connect signals
        self._poller.sample_ready.connect(self._on_sample)
        self._poller.time_sample_ready.connect(self._on_time_sample)
        self._poller.status_changed.connect(self._on_status_changed)
        self._poller.connection_lost.connect(self._on_connection_lost)
        self._poller.connection_restored.connect(self._on_connection_restored)
        self._poller.log_message.connect(self._on_log_message)
        self._poller.mount_info_ready.connect(self._on_mount_info)
        self._poller.environment_ready.connect(self._on_environment)

        self._poller.start()
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
            sim_sei.set_callback(self._on_seismic_data)
            sim_sei.start()
            self._seismometer = sim_sei
            self._status_panel.add_message(T("sim_seismometer"), Colors.STATUS_WARNING)
        elif self._settings.get("seismometer_enabled"):
            sei = Seismometer(
                port=self._settings.get("seismometer_port"),
                frequency_hz=self._settings.get("seismometer_frequency_hz"),
                offset=self._settings.get("seismometer_offset"),
                data_range=self._settings.get("seismometer_range"),
            )
            sei.set_callback(self._on_seismic_data)
            if sei.start():
                self._seismometer = sei

        # Auto-start logging
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

        if self._poller:
            self._poller.stop()
            self._poller = None

        if self._ntp_client:
            self._ntp_client.stop()
            self._ntp_client = None

        if self._seismometer:
            if hasattr(self._seismometer, 'stop'):
                self._seismometer.stop()
            self._seismometer = None

        if self._connection:
            self._connection.disconnect()
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

        # Log to file
        if self._ecrit_echantillons():
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
        if self._ecrit_echantillons():
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
        if self._logging_active:
            self._file_logger.log_event(f"Mount status: {status.name}")

        # ── Armed logger: start on tracking, suspend when tracking stops ──
        if status == MountStatus.TRACKING:
            self._annuler_arret_park()
            if self._logging_armed:
                self._demarrer_sur_suivi()
            else:
                self._reprendre()
        elif self._logging_active and self._settings.get("pause_when_not_tracking"):
            # Any status other than TRACKING -- parked, idle, slewing --
            # starts the grace delay. Slews and autofocus finish well inside
            # it; only a real stop outlasts it.
            if self._park_timer is None and not self._logging_suspendu:
                delai = int(self._settings.get("pause_delay_s") or 120)
                self._park_timer = QTimer(self)
                self._park_timer.setSingleShot(True)
                self._park_timer.timeout.connect(self._suspendre)
                self._park_timer.start(delai * 1000)

        # Detect transition from slewing to tracking
        was_slewing = prev_status == MountStatus.SLEWING
        now_tracking = status == MountStatus.TRACKING

        # Auto-reset on slewing
        if status == MountStatus.SLEWING:
            if self._settings.get("reset_mode") == "slewing":
                self._reset_both()

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

            # Auto-analysis on park: analyze the night session
            self._auto_analyze_on_park()

        # After slew ends and tracking resumes → run checks + get target coords
        if was_slewing and now_tracking:
            QTimer.singleShot(1000, self._run_mount_checks)
            # Retrieve target coordinates for reference mode
            if self._settings.get("reference_mode") == "target" and self._connection:
                target_ra = self._connection.get_target_ra()
                target_dec = self._connection.get_target_dec()
                if target_ra and target_dec:
                    from ..utils.coordinates import parse_ra, parse_dec
                    ra_h = parse_ra(target_ra)
                    dec_d = parse_dec(target_dec)
                    if ra_h is not None and dec_d is not None:
                        self._processor.set_target_coordinates(ra_h, dec_d)

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
            f"Mount: {product}", Colors.STATUS_OK
        )
        self._status_panel.add_message(
            f"Firmware: {firmware}"
        )
        if mount_id:
            self._status_panel.add_message(f"ID: {mount_id}")
        if pier_side and hasattr(pier_side, 'value'):
            self._status_panel.add_message(f"Pier: {pier_side.value}")
        if azimuth is not None and altitude is not None:
            self._status_panel.add_message(
                f"Az: {azimuth:.1f}\u00b0  Alt: {altitude:.1f}\u00b0"
            )
        if latitude and longitude:
            elev_str = f"  Elev: {elevation:.0f}m" if elevation is not None else ""
            self._status_panel.add_message(
                f"Site: {latitude} {longitude}{elev_str}"
            )
            self._site_monture = (latitude, longitude, elevation)
            self._annoncer_nuit()

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
        if self._ecrit_echantillons():
            self._file_logger.log_environment(sample)

        # Log significant changes to status panel
        parts = []
        if sample.temperature_ext is not None:
            parts.append(f"Temp: {sample.temperature_ext:.1f}\u00b0C")
        if sample.pressure is not None:
            parts.append(f"Press: {sample.pressure:.0f}mbar")
        if sample.temperature_int is not None:
            parts.append(f"Int: {sample.temperature_int:.1f}\u00b0C")
        if sample.meridian_flip_minutes is not None:
            parts.append(f"Flip: {sample.meridian_flip_minutes:.0f}min")
        if parts:
            self._status_panel.add_message("  ".join(parts))

        # Log alignment data (less frequently visible)
        if sample.alignment_stars is not None and sample.alignment_rms is not None:
            logger.debug(
                f"Alignment: {sample.alignment_stars} stars, "
                f"RMS {sample.alignment_rms:.1f}\", "
                f"polar error {sample.polar_error_deg:.4f}\u00b0"
            )

        # Log to event file
        if self._ecrit_echantillons():
            if sample.temperature_ext is not None:
                # Chaque champ peut être None indépendamment (la monture ne
                # renvoie pas toujours pression/température interne) — et un
                # format spec conditionnel dans une f-string est un ValueError.
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

    def _on_seismic_data(self, timestamp: float, values: list[float]):
        """Handle seismometer data callback."""
        self._processor.process_seismic_data(timestamp, values)
        # Parité avec le MountMonitor Java : chaque échantillon est journalisé
        # dans le .sei (temps, brut, valeur recentrée par l'offset, stdev
        # glissant courant). Sans cet appel le fichier restait vide.
        if self._logging_active and values:
            # Le module sismomètre livre des valeurs déjà recentrées
            # (raw - offset) : on reconstruit le brut pour la 1re colonne.
            offset = float(self._settings.get("seismometer_offset") or 0.0)
            stdev_arr = self._processor.seismic_buffer.get_stdev_array()
            stdev = float(stdev_arr[-1]) if len(stdev_arr) else 0.0
            for v in values:
                self._file_logger.log_seismic_data(
                    timestamp, v + offset, v, stdev
                )

    # ── Graph refresh ────────────────────────────────────────────

    def _refresh_graphs(self):
        """Refresh all graphs with current buffer data. Called by timer.

        Performance: uses downsampled arrays (max 5000 points) for graph display
        to avoid plotting 50K+ points. Full-resolution arrays are used only for
        statistics (min/max/stdev) which are pre-computed in DataBuffer.
        """
        # Graph correction: shift STDEV timestamps back by half running range
        correct = self._settings.get("correct_graphs_for_range")
        half_range = self._settings.get("running_range_seconds") / 2.0 if correct else 0.0

        # RA graph — downsampled for display
        ra_t, ra_v = self._processor.ra_buffer.get_downsampled_arrays(5000)
        ra_stdev = self._processor.ra_buffer.get_stdev_array()
        if len(ra_t) > 0:
            # Downsample stdev to match display points
            if len(ra_stdev) > 0:
                full_t, _ = self._processor.ra_buffer.get_arrays()
                if len(ra_stdev) == len(full_t) and len(full_t) > 5000:
                    step = len(full_t) // 5000
                    indices = np.arange(0, len(full_t), step)
                    if indices[-1] != len(full_t) - 1:
                        indices = np.append(indices, len(full_t) - 1)
                    stdev_for_graph = ra_stdev[indices]
                else:
                    stdev_for_graph = ra_stdev if len(ra_stdev) == len(ra_t) else None
            else:
                stdev_for_graph = None
            stdev_t = ra_t - half_range if (stdev_for_graph is not None and half_range > 0) else None
            self._ra_graph.update_data(
                ra_t, ra_v,
                stdev_values=stdev_for_graph,
                stdev_timestamps=stdev_t,
                min_val=self._processor.ra_buffer.min_value,
                max_val=self._processor.ra_buffer.max_value,
                max_stdev=self._processor.ra_buffer.max_stdev,
            )
            self._ra_graph.set_tolerance(self._settings.get("tolerance_ra_arcsec"))

        # DEC graph — downsampled for display
        dec_t, dec_v = self._processor.dec_buffer.get_downsampled_arrays(5000)
        dec_stdev = self._processor.dec_buffer.get_stdev_array()
        if len(dec_t) > 0:
            if len(dec_stdev) > 0:
                full_t, _ = self._processor.dec_buffer.get_arrays()
                if len(dec_stdev) == len(full_t) and len(full_t) > 5000:
                    step = len(full_t) // 5000
                    indices = np.arange(0, len(full_t), step)
                    if indices[-1] != len(full_t) - 1:
                        indices = np.append(indices, len(full_t) - 1)
                    stdev_for_graph = dec_stdev[indices]
                else:
                    stdev_for_graph = dec_stdev if len(dec_stdev) == len(dec_t) else None
            else:
                stdev_for_graph = None
            stdev_t = dec_t - half_range if (stdev_for_graph is not None and half_range > 0) else None
            self._dec_graph.update_data(
                dec_t, dec_v,
                stdev_values=stdev_for_graph,
                stdev_timestamps=stdev_t,
                min_val=self._processor.dec_buffer.min_value,
                max_val=self._processor.dec_buffer.max_value,
                max_stdev=self._processor.dec_buffer.max_stdev,
            )
            self._dec_graph.set_tolerance(self._settings.get("tolerance_dec_arcsec"))

        # Time graph — downsampled
        diff_t, diff_v = self._processor.time_diff_buffer.get_downsampled_arrays(5000)
        pc_t, pc_v = self._processor.pc_loop_buffer.get_downsampled_arrays(5000)
        mt_t, mt_v = self._processor.mount_loop_buffer.get_downsampled_arrays(5000)
        ntp_t, ntp_v = self._processor.ntp_buffer.get_downsampled_arrays(5000)
        if len(diff_t) > 0:
            self._time_graph.update_data(
                diff_t, diff_v,
                pc_loop_t=pc_t, pc_loop_v=pc_v,
                mount_loop_t=mt_t, mount_loop_v=mt_v,
                ntp_t=ntp_t if len(ntp_t) > 0 else None,
                ntp_v=ntp_v if len(ntp_v) > 0 else None,
            )

        # Axial graph — downsampled
        if self._settings.get("axial_mode") != "off":
            ra_raw_t, ra_raw_v = self._processor.ra_speed_raw_buffer.get_downsampled_arrays(5000)
            dec_raw_t, dec_raw_v = self._processor.dec_speed_raw_buffer.get_downsampled_arrays(5000)
            ra_avg_t, ra_avg_v = self._processor.ra_speed_avg_buffer.get_downsampled_arrays(5000)
            dec_avg_t, dec_avg_v = self._processor.dec_speed_avg_buffer.get_downsampled_arrays(5000)
            if len(ra_raw_t) > 0 or len(dec_raw_t) > 0:
                self._axial_graph.update_data(
                    ra_raw_t=ra_raw_t if len(ra_raw_t) > 0 else None,
                    ra_raw_v=ra_raw_v if len(ra_raw_v) > 0 else None,
                    dec_raw_t=dec_raw_t if len(dec_raw_t) > 0 else None,
                    dec_raw_v=dec_raw_v if len(dec_raw_v) > 0 else None,
                    ra_avg_t=ra_avg_t if len(ra_avg_t) > 0 else None,
                    ra_avg_v=ra_avg_v if len(ra_avg_v) > 0 else None,
                    dec_avg_t=dec_avg_t if len(dec_avg_t) > 0 else None,
                    dec_avg_v=dec_avg_v if len(dec_avg_v) > 0 else None,
                )

        # Seismic graph — downsampled
        sei_t, sei_v = self._processor.seismic_buffer.get_downsampled_arrays(5000)
        if len(sei_t) > 0:
            sei_stdev = self._processor.seismic_buffer.get_stdev_array()
            sei_stdev_ds = sei_stdev if len(sei_stdev) == len(sei_t) else None
            self._seismic_graph.update_data(
                sei_t, sei_v,
                stdev_values=sei_stdev_ds,
            )

        # Update STDEV in status panel (use full-res last values)
        full_ra_stdev = self._processor.ra_buffer.get_stdev_array()
        full_dec_stdev = self._processor.dec_buffer.get_stdev_array()
        if len(full_ra_stdev) > 0 and len(full_dec_stdev) > 0:
            self._status_panel.update_stdev(full_ra_stdev[-1], full_dec_stdev[-1])

        # Update title with current frequency
        self._update_title()

        # Carnet photographique de la nuit, quand il est demande.
        self._verifier_graphe_plein()

    # ── FFT ──────────────────────────────────────────────────────

    def _show_fft(self):
        """Show FFT analysis window."""
        if self._fft_window is None:
            self._fft_window = FFTWindow()
            w = self._settings.get("fft_width")
            h = self._settings.get("fft_height")
            self._fft_window.resize(w, h)
        self._fft_window.show()
        self._fft_window.raise_()
        self._fft_timer.start()

    def _update_fft(self):
        """Update FFT window with current data. Also logs FFT to file."""
        fft_visible = self._fft_window and self._fft_window.isVisible()
        if not fft_visible and not self._logging_active:
            return

        freq = max(1.0, self._processor.actual_frequency)

        # RA FFT
        _, ra_data = self._processor.ra_buffer.get_arrays()
        ra_freqs, ra_mags = None, None
        if len(ra_data) > 64:
            ra_freqs, ra_mags = self._processor.compute_fft(ra_data, freq)

        # DEC FFT
        _, dec_data = self._processor.dec_buffer.get_arrays()
        dec_freqs, dec_mags = None, None
        if len(dec_data) > 64:
            dec_freqs, dec_mags = self._processor.compute_fft(dec_data, freq)

        # Seismic FFT
        _, sei_data = self._processor.seismic_buffer.get_arrays()
        sei_freqs, sei_mags = None, None
        sei_rate = self._settings.get("seismometer_frequency_hz")
        if len(sei_data) > 64:
            sei_freqs, sei_mags = self._processor.compute_fft(sei_data, sei_rate)

        if fft_visible:
            self._fft_window.update_fft(
                ra_freqs=ra_freqs, ra_mags=ra_mags,
                dec_freqs=dec_freqs, dec_mags=dec_mags,
                sei_freqs=sei_freqs, sei_mags=sei_mags,
                ra_sample_rate=freq, dec_sample_rate=freq,
                sei_sample_rate=sei_rate if len(sei_data) > 0 else None,
            )

        # Log FFT data to .fft file
        if self._ecrit_echantillons():
            if ra_freqs is not None and len(ra_freqs) > 0:
                self._file_logger.log_fft_snapshot("RA", freq, ra_freqs, ra_mags)
            if dec_freqs is not None and len(dec_freqs) > 0:
                self._file_logger.log_fft_snapshot("DEC", freq, dec_freqs, dec_mags)
            if sei_freqs is not None and len(sei_freqs) > 0:
                self._file_logger.log_fft_snapshot("SEI", sei_rate, sei_freqs, sei_mags)

    # ── Logging ──────────────────────────────────────────────────

    def _toggle_logging(self):
        if self._logging_active:
            self._stop_logging()
        elif self._logging_armed:
            self._desarmer()
        elif self._settings.get("autostart_on_tracking"):
            self._armer()
        else:
            self._start_logging()

    def _armer(self):
        """Wait for the mount to track before writing anything."""
        self._logging_armed = True
        self._btn_logging.setText(T("btn_armed_log"))
        self._status_panel.add_message(T("logging_armed"), Colors.STATUS_OK)
        # Already tracking when armed: start at once rather than wait for a
        # transition that has already happened.
        if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
            self._demarrer_sur_suivi()

    def _desarmer(self):
        self._logging_armed = False
        self._btn_logging.setText(T("btn_start_log"))
        self._status_panel.add_message(T("logging_disarmed"))

    def _demarrer_sur_suivi(self):
        """The mount started tracking while armed."""
        if not self._logging_armed or self._logging_active:
            return
        self._logging_armed = False
        self._start_logging()
        self._status_panel.add_message(T("logging_autostart"), Colors.STATUS_OK)

    def _ecrit_echantillons(self) -> bool:
        """Whether samples should go to the file right now."""
        return self._logging_active and not self._logging_suspendu

    def _annuler_arret_park(self):
        if self._park_timer is not None:
            self._park_timer.stop()
            self._park_timer = None

    def _suspendre(self):
        """Mount stopped tracking long enough: stop writing, keep the session.

        A grace delay is used because a stop can be transient -- a meridian
        flip, a slew between two targets, an autofocus run. Suspending on the
        first non-tracking sample would punch a hole in every dither.
        """
        self._annuler_arret_park()
        if not self._logging_active or self._logging_suspendu:
            return
        self._logging_suspendu = True
        self._file_logger.log_event("Logging suspended: mount not tracking")
        self._status_panel.add_message(T("logging_suspendu"))

    def _reprendre(self):
        """Tracking resumed: same file, same night."""
        if not self._logging_active or not self._logging_suspendu:
            return
        self._logging_suspendu = False
        self._file_logger.log_event("Logging resumed: mount tracking again")
        self._status_panel.add_message(T("logging_repris"), Colors.STATUS_OK)

    def _surveiller_aube(self):
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
        from ..core.ephemerides import hauteur_soleil, HORIZON
        from datetime import datetime, timezone
        lat, lon, _ = site
        try:
            h = hauteur_soleil(datetime.now(timezone.utc), lat, lon)
        except Exception as exc:
            logger.error(f"Sun altitude failed: {exc}")
            return
        if h <= HORIZON:
            self._nuit_vue = True
            return
        if self._nuit_vue:
            self._status_panel.add_message(T("logging_autostop"), Colors.STATUS_OK)
            self._stop_logging()

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
        self._file_logger.start_session(session)
        self._logging_active = True
        self._logging_suspendu = False
        self._nuit_vue = False
        if self._settings.get("close_at_sunrise"):
            self._aube_timer = QTimer(self)
            self._aube_timer.timeout.connect(self._surveiller_aube)
            self._aube_timer.start(60_000)
            self._surveiller_aube()
        self._btn_logging.setText(T("btn_stop_log"))
        # Start FFT timer for logging even if FFT window is not open
        if not self._fft_timer.isActive():
            self._fft_timer.start()
        self._status_panel.add_message(T("logging_started"), Colors.STATUS_OK)
        # Also announce the night when the site comes from the preferences:
        # _on_mount_info only fires when the mount answers, which is exactly
        # the case the preferences exist to cover.
        self._annoncer_nuit()

    def _stop_logging(self):
        """Stop data logging."""
        self._annuler_arret_park()
        if self._aube_timer is not None:
            self._aube_timer.stop()
            self._aube_timer = None
        self._logging_suspendu = False
        if not self._logging_active:
            return
        chemin_dat = getattr(self._file_logger, 'dat_path', None)
        self._file_logger.close()
        self._logging_active = False
        self._btn_logging.setText(T("btn_start_log"))
        self._status_panel.add_message(T("logging_stopped"))

        # The night report is written on its own, next to the .dat. Asking the
        # user to remember to export it is how a night ends up without one.
        if chemin_dat:
            QApplication.processEvents()
            sortie = sauver_rapport(chemin_dat, get_language())
            if sortie:
                self._status_panel.add_message(
                    f"{T('report_saved')} : {Path(sortie).stem[:-3]}*.txt "
                    f"({', '.join(LANGUES)})", Colors.STATUS_OK
                )

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

    def _open_log_file(self):
        """Open a previous log file for replay and analysis."""
        log_dir = str(self._file_logger.log_dir)

        lang = get_language()
        if lang == 'fr':
            title = "Ouvrir un fichier log"
            filter_str = "Fichiers données (*.dat);;Tous les fichiers (*)"
        else:
            title = "Open Log File"
            filter_str = "Data files (*.dat);;All files (*)"

        file_path, _ = QFileDialog.getOpenFileName(
            self, title, log_dir, filter_str
        )
        if not file_path:
            return

        self._status_panel.add_message(
            f"{T('loading_file')} : {Path(file_path).name}..."
        )
        QApplication.processEvents()

        # Parse the session
        session = parse_session(Path(file_path))

        if session.sample_count == 0:
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
        QApplication.processEvents()
        try:
            dialog = AnalysisDialog(session, self)
            dialog.exec()
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
            # Compute speeds from axis positions
            t = session.timestamps[:len(session.ra_axis)]
            dt = np.diff(t)
            dt[dt == 0] = 1e-6
            ra_speed = np.diff(session.ra_axis) / dt
            dec_speed = np.diff(session.dec_axis) / dt if len(session.dec_axis) == len(session.ra_axis) else None

            if len(ra_speed) > 0:
                self._axial_graph.update_data(
                    ra_raw_t=t[1:], ra_raw_v=ra_speed,
                    dec_raw_t=t[1:] if dec_speed is not None else None,
                    dec_raw_v=dec_speed,
                )

    def _replay_fft(self, session):
        """Compute and display FFT from replayed data."""
        if session.effective_frequency <= 0:
            return

        freq = session.effective_frequency

        ra_freqs, ra_mags = None, None
        dec_freqs, dec_mags = None, None

        if len(session.ra_deviations) > 64:
            ra_data = session.ra_deviations - np.mean(session.ra_deviations)
            window = np.hanning(len(ra_data))
            windowed = ra_data * window
            n = len(windowed)
            fft_result = np.fft.rfft(windowed)
            ra_mags = 2.0 / n * np.abs(fft_result)
            ra_freqs = np.fft.rfftfreq(n, d=1.0 / freq)
            ra_freqs = ra_freqs[1:]
            ra_mags = ra_mags[1:]

        if len(session.dec_deviations) > 64:
            dec_data = session.dec_deviations - np.mean(session.dec_deviations)
            window = np.hanning(len(dec_data))
            windowed = dec_data * window
            n = len(windowed)
            fft_result = np.fft.rfft(windowed)
            dec_mags = 2.0 / n * np.abs(fft_result)
            dec_freqs = np.fft.rfftfreq(n, d=1.0 / freq)
            dec_freqs = dec_freqs[1:]
            dec_mags = dec_mags[1:]

        # Show FFT window with replayed data
        if ra_freqs is not None or dec_freqs is not None:
            if self._fft_window is None:
                self._fft_window = FFTWindow()
            self._fft_window.update_fft(
                ra_freqs=ra_freqs, ra_mags=ra_mags,
                dec_freqs=dec_freqs, dec_mags=dec_mags,
                ra_sample_rate=freq, dec_sample_rate=freq,
            )
            self._fft_window.show()
            self._fft_window.raise_()

    def _auto_analyze_on_park(self):
        """Automatically analyze the night session when mount is parked.

        Finds the most recent .dat log file and runs the full analysis.
        """
        try:
            log_dir = self._file_logger.log_dir
            sessions = list_log_sessions(log_dir)
            if not sessions:
                return

            # Use the most recent log file
            latest = sessions[0]
            dat_path = latest['path']

            # Only analyze if file has meaningful data (> 1 KB)
            if latest['size_kb'] < 1.0:
                return

            self._status_panel.add_message(
                T("parked_auto_analysis"), Colors.STATUS_OK,
            )
            QApplication.processEvents()

            session = parse_session(dat_path)
            if session.sample_count < 10:
                return

            # Show analysis dialog
            dialog = AnalysisDialog(session, self)
            dialog.exec()

            self._status_panel.add_message(
                T("analysis_complete"), Colors.STATUS_OK
            )
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    # ── Zoom and reset ───────────────────────────────────────────

    def _set_horizontal_zoom(self, zoom: int):
        """Applique le zoom horizontal aux graphes, et le retient.

        Il n'etait jusqu'ici qu'enregistre : le menu existait, le reglage
        etait sauvegarde, et l'affichage n'en tenait aucun compte.
        """
        self._settings.set("horizontal_zoom", zoom)
        self._settings.save()
        self._appliquer_zoom_horizontal(zoom)

    def _appliquer_zoom_horizontal(self, zoom: int):
        for graphe in (self._ra_graph, self._dec_graph,
                       self._time_graph, self._seismic_graph):
            graphe._zoom_horizontal = zoom

    def _set_vertical_zoom(self, mode: str):
        self._ra_graph.set_vertical_zoom(mode)
        self._dec_graph.set_vertical_zoom(mode)
        self._settings.set("vertical_zoom_mode", mode)
        self._settings.save()

    def _reset_minmax(self):
        self._processor.reset_minmax()
        self._status_panel.add_message(T("reset_minmax"))

    def _reset_buffers(self):
        self._processor.reset_buffers()
        self._ra_graph.reset()
        self._dec_graph.reset()
        self._time_graph.reset()
        self._seismic_graph.reset()
        self._axial_graph.reset()
        self._status_panel.add_message(T("reset_buffers"))

    def _reset_both(self):
        self._reset_buffers()
        self._processor.reset_minmax()
        self._status_panel.add_message(T("reset_both"))

    # ── Preferences ──────────────────────────────────────────────

    def _site(self):
        """Observing site as (lat, lon east, elevation), or None.

        The mount is trusted first and the preferences fill in. Note the
        sign: LX200 reports longitude positive WEST, so a site east of
        Greenwich comes back negative and must be flipped -- getting it
        wrong moves the observatory and shifts every twilight.
        """
        from ..core.ephemerides import parse_latitude_lx200, parse_longitude_lx200
        if self._site_monture:
            lat_t, lon_t, elev = self._site_monture
            lat = parse_latitude_lx200(lat_t)
            lon = parse_longitude_lx200(lon_t)
            if lat is not None and lon is not None:
                return lat, lon, (elev if elev is not None else 0.0)
        lat_p = self._settings.get("site_latitude")
        lon_p = self._settings.get("site_longitude")
        if lat_p not in (None, "") and lon_p not in (None, ""):
            try:
                elev = float(self._settings.get("site_elevation_m") or 0.0)
            except (TypeError, ValueError):
                elev = 0.0
            return float(lat_p), float(lon_p), elev
        return None

    def _annoncer_nuit(self):
        """Post tonight's twilights to the status panel."""
        site = self._site()
        if not site:
            return
        from ..core.ephemerides import nuit_autour
        from datetime import datetime, timezone
        lat, lon, _ = site
        try:
            n = nuit_autour(datetime.now(timezone.utc), lat, lon)
        except Exception as exc:
            logger.error(f"Ephemeris failed: {exc}")
            return

        def hl(t):
            return t.astimezone().strftime('%H:%M') if t else '--:--'

        if n.soleil_toujours_haut:
            self._status_panel.add_message(T("nuit_jour_permanent"))
            return
        self._status_panel.add_message(
            f"{T('nuit_coucher')} {hl(n.coucher)}  |  "
            f"{T('nuit_nautique')} {hl(n.nautique)}  |  "
            f"{T('nuit_lever')} {hl(n.lever)}")
        if n.nuit_noire:
            d = n.duree_noire
            heures = int(d.total_seconds() // 3600)
            mins = int((d.total_seconds() % 3600) // 60)
            self._status_panel.add_message(
                f"{T('nuit_noire')} {hl(n.astro_debut)} \u2192 {hl(n.astro_fin)} "
                f"({heures} h {mins:02d})", Colors.STATUS_OK)
        else:
            self._status_panel.add_message(T("nuit_pas_de_nuit_noire"))

    def _choisir_langue(self, code: str):
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
        self._settings.save()
        set_language(code)
        self._prevenir_redemarrage()

    def _prevenir_redemarrage(self):
        """Tell the user the new language needs a restart, and offer it."""
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Icon.Information)
        boite.setWindowTitle(T("lang_restart_titre"))
        boite.setText(T("lang_restart_texte"))
        if self._logging_active:
            # Restarting would end the session and write the night report in
            # the middle of the night. Not offered.
            boite.setInformativeText(T("lang_restart_bloque"))
            boite.setStandardButtons(QMessageBox.StandardButton.Ok)
            boite.exec()
            return
        maintenant = boite.addButton(T("lang_restart_now"),
                                     QMessageBox.ButtonRole.AcceptRole)
        boite.addButton(T("lang_restart_later"), QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        if boite.clickedButton() is maintenant:
            self._redemarrer()

    def _redemarrer(self):
        """Relaunch the application in place."""
        import os
        import subprocess
        try:
            self.close()
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])]
                                 + sys.argv[1:])
        except Exception as exc:
            logger.error(f"Restart failed: {exc}")
            return
        QApplication.quit()

    def _show_preferences(self):
        """Show preferences dialog."""
        avant = self._settings.get("language")
        dialog = PreferencesDialog(self._settings, self)
        if dialog.exec():
            self._apply_settings()
            # The language combo also lives in Preferences. Changing it there
            # must say the same thing as the Language menu, otherwise it is
            # again an option that appears to do nothing.
            if self._settings.get("language") != avant:
                self._prevenir_redemarrage()

    def _apply_settings(self):
        """Apply changed settings to running components."""
        set_language(self._settings.get("language"))

        if self._processor:
            self._processor.set_tolerances(
                self._settings.get("tolerance_ra_arcsec"),
                self._settings.get("tolerance_dec_arcsec"),
                self._settings.get("tolerance_seismic_percent"),
            )
            self._processor.set_running_range(self._settings.get("running_range_seconds"))
            self._processor.set_reference_mode(self._settings.get("reference_mode"))

        if self._poller:
            self._poller.set_frequency(self._settings.get("polling_frequency_hz"))
            self._poller.set_axial_enabled(self._settings.get("axial_mode") != "off")
            self._poller.set_log_tracking_only(self._settings.get("log_mode") == "tracking_only")

        if self._ntp_client and self._settings.get("ntp_enabled"):
            self._ntp_client.set_server(self._settings.get("ntp_server"))
            self._ntp_client.set_interval(self._settings.get("ntp_interval_seconds"))

        self._ra_graph.set_tolerance(self._settings.get("tolerance_ra_arcsec"))
        self._dec_graph.set_tolerance(self._settings.get("tolerance_dec_arcsec"))

        # Update status panel tolerance display
        self._status_panel.set_tolerances(
            self._settings.get("tolerance_ra_arcsec"),
            self._settings.get("tolerance_dec_arcsec"),
            as_ha_seconds=self._settings.get("tolerance_as_ha_seconds"),
        )

    # ── Graph dump ─────────────────────────────────────────────

    def _verifier_graphe_plein(self):
        """Enregistre les graphes quand la largeur s'est remplie de neuf.

        C'est le comportement du MountMonitor Java : « MountMonitor outputs
        the graphs automatically each time the window width is filled with
        new data ». Il laisse un carnet photographique continu de la nuit,
        sans avoir a rejouer quoi que ce soit le lendemain.

        Le critere est celui de l'original : autant d'echantillons neufs que
        le graphe a de pixels de large — au-dela, un point de plus n'ajoute
        rien a l'image.
        """
        if self._settings.get("dump_mode") != "full":
            return
        try:
            largeur = max(200, self._ra_graph.width())
            total = self._processor.ra_buffer.size
        except Exception:
            return
        depart = getattr(self, '_rang_dernier_dump', None)
        if depart is None or total < depart:
            self._rang_dernier_dump = total
            return
        if total - depart >= largeur:
            self._rang_dernier_dump = total
            self._dump_graphs()

    def _dump_graphs(self):
        """Export all graph images to their respective directories."""
        self._ra_graph.export_to_image("RA_graphs")
        self._dec_graph.export_to_image("DEC_graphs")
        self._time_graph.export_to_image("Time_graphs")
        self._seismic_graph.export_to_image("Seismic_graphs")
        if self._settings.get("axial_mode") != "off":
            self._axial_graph.export_to_image("Axial_graphs")
        if self._fft_window and self._fft_window.isVisible():
            self._fft_window.export_to_image("FFT_graphs")
        self._status_panel.add_message(T("graphs_exported"))

    # ── Mount checks ────────────────────────────────────────────

    def _run_mount_checks(self):
        """Run mount setting checks based on preferences.

        Checks refraction, tracking rate, GPS sync as configured in
        the Miscellaneous tab. Shows warnings and logs results.
        """
        if not self._connection or not self._connected:
            return

        warnings = []
        ok_checks = []

        # Check refraction mode (3-way: not_updating, not_updating_tracking, continuously_updating)
        if self._settings.get("check_refraction_enabled"):
            expected = self._settings.get("check_refraction_value")
            mode = self._connection.get_refraction_mode()
            if mode is not None:
                if mode == expected:
                    mode_display = mode.replace('_', ' ')
                    ok_checks.append(f"Refraction: {mode_display} \u2713")
                else:
                    mode_display = mode.replace('_', ' ')
                    expected_display = expected.replace('_', ' ')
                    warnings.append(
                        f"Refraction is '{mode_display}', expected '{expected_display}'"
                    )
            else:
                # Fallback to simple enabled/disabled check
                refraction = self._connection.is_refraction_enabled()
                if refraction is not None:
                    actual = "enabled" if refraction else "disabled"
                    ok_checks.append(f"Refraction: {actual} (simple check)")

        # Check tracking rate
        if self._settings.get("check_tracking_rate"):
            expected_val = self._settings.get("check_tracking_rate_value")
            rate = self._connection.get_tracking_rate()
            if rate is not None:
                rate_lower = str(rate).lower().strip()
                if expected_val.lower() in rate_lower or rate_lower.startswith("60"):
                    ok_checks.append(f"Tracking rate: {rate} \u2713")
                else:
                    warnings.append(
                        f"Tracking rate is {rate}, expected {expected_val}"
                    )

        # Check GPS sync
        if self._settings.get("check_gps_sync"):
            expected_val = self._settings.get("check_gps_sync_value")
            gps = self._connection.is_gps_synced()
            if gps is not None:
                actual = "synchronising" if gps else "not synchronising"
                if actual == expected_val:
                    ok_checks.append(f"GPS: {actual} \u2713")
                else:
                    warnings.append(
                        f"GPS is {actual}, expected {expected_val}"
                    )

        # Check dual tracking
        if self._settings.get("check_dual_tracking"):
            expected_val = self._settings.get("check_dual_tracking_value")
            dual = self._connection.is_dual_tracking_enabled()
            if dual is not None:
                actual = "enabled" if dual else "disabled"
                if actual == expected_val:
                    ok_checks.append(f"Dual tracking: {actual} \u2713")
                else:
                    warnings.append(
                        f"Dual tracking is {actual}, expected {expected_val}"
                    )

        # Display results
        for msg in ok_checks:
            self._status_panel.add_message(msg, Colors.STATUS_OK)
            if self._logging_active:
                self._file_logger.log_event(f"Check OK: {msg}")

        if warnings:
            for msg in warnings:
                self._status_panel.add_message(
                    f"\u26a0 {msg}", Colors.STATUS_WARNING
                )
                if self._logging_active:
                    self._file_logger.log_event(f"Check WARNING: {msg}")

            # Show popup alert
            lang = get_language()
            if lang == "fr":
                title = "Alerte monture"
                text = "Vérification de la monture :\n\n" + "\n".join(
                    f"\u26a0 {w}" for w in warnings
                )
            else:
                title = "Mount Alert"
                text = "Mount settings check:\n\n" + "\n".join(
                    f"\u26a0 {w}" for w in warnings
                )
            QMessageBox.warning(self, title, text)

    # ── Help ─────────────────────────────────────────────────────

    def _ouvrir_manuel(self):
        """Open the PDF manual for the current language.

        It ships in app/docs next to the program; without a menu entry
        nobody would ever find it there.
        """
        import subprocess
        import webbrowser
        lang = get_language()
        base = Path(__file__).resolve().parent.parent.parent / "docs"
        chemin = base / f"manual_{lang}.pdf"
        if not chemin.exists():
            chemin = base / "manual_en.pdf"
        if not chemin.exists():
            QMessageBox.information(self, T("menu_manual"), T("manual_absent"))
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(chemin))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(chemin)])
            else:
                subprocess.Popen(["xdg-open", str(chemin)])
        except Exception:
            # xdg-open may simply be absent on a bare Linux install.
            webbrowser.open(chemin.as_uri())

    def _show_help(self):
        """Show the help document, in the user's language.

        The text lived here as two hard-coded strings, English and French,
        still describing version 1.6. It now sits in aide_textes, in three
        languages, and is scrollable: a QMessageBox silently truncates a
        document this long.
        """
        from .aide_textes import aide_html, TITRE
        lang = get_language()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{TITRE.get(lang, TITRE['en'])} — MountMonitor")
        dlg.resize(760, 620)
        lay = QVBoxLayout(dlg)
        vue = QTextBrowser(dlg)
        vue.setOpenExternalLinks(False)
        vue.setHtml(aide_html(lang, self._version))
        lay.addWidget(vue)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
        boutons.rejected.connect(dlg.reject)
        boutons.accepted.connect(dlg.accept)
        lay.addWidget(boutons)
        dlg.exec()

    def _show_about(self):
        """Show about dialog."""
        lang = get_language()
        if lang == "fr":
            text = (
                f"<h2>MountMonitor v{self._version}</h2>"
                f"<p>Surveillance de monture télescope en temps réel.</p>"
                f"<p>Réécriture modernisée du programme original Java v3.37<br>"
                f"par Nicolàs de Hilster (2018-2021).</p>"
                f"<p>Python/PyQt6/pyqtgraph</p>"
            )
        else:
            text = (
                f"<h2>MountMonitor v{self._version}</h2>"
                f"<p>Real-time telescope mount monitoring.</p>"
                f"<p>Modernized rewrite of the original Java v3.37<br>"
                f"by Nicolàs de Hilster (2018-2021).</p>"
                f"<p>Python/PyQt6/pyqtgraph</p>"
            )
        QMessageBox.about(self, T("menu_about"), text)

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
        """Verification discrete au demarrage : rien ne s'affiche si tout va bien."""
        self._lancer_verification(manuelle=False)

    def _check_updates_manual(self):
        """Verification demandee par le menu Aide : on repond dans tous les cas."""
        self.statusBar().showMessage(T("update_checking"), 5000)
        self._lancer_verification(manuelle=True)

    def _lancer_verification(self, manuelle: bool):
        """Interroge GitHub dans un fil de fond."""
        if getattr(self, '_verification_en_cours', False):
            return
        self._verification_en_cours = True

        def _interroger():
            trouve = None
            try:
                if updater.is_packaged():
                    trouve = updater.check(self._version)
                elif manuelle:
                    trouve = 'sources'
            except Exception:
                logger.debug("Verification des mises a jour impossible",
                             exc_info=True)
            self.maj_trouvee.emit((trouve, manuelle))

        threading.Thread(target=_interroger, daemon=True,
                         name='verif-maj').start()

    def _maj_reperee(self, resultat):
        """Retour de la verification, sur le fil graphique."""
        trouve, manuelle = resultat
        self._verification_en_cours = False

        if trouve == 'sources':
            QMessageBox.information(
                self, T("menu_check_updates"),
                T("tt_upd_source"))
            return

        if not trouve:
            if manuelle:
                QMessageBox.information(
                    self, T("menu_check_updates"),
                    T("update_up_to_date").format(version=self._version))
            return

        self._show_update_dialog(trouve)

    def _show_update_dialog(self, release_info: dict):
        """Show update available dialog with changelog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

        tag = release_info.get("version", "?")
        body = release_info.get("notes", "") or ""
        taille = release_info.get("size", 0)

        dlg = QDialog(self)
        dlg.setWindowTitle(T("update_available"))
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)

        # Version info
        info_text = (
            f"<h3>{T('update_available')}</h3>"
            f"<p><b>{T('update_current')}:</b> {self._version}<br>"
            f"<b>{T('update_new')}:</b> {tag}"
            + (f" ({taille / 1e6:.1f} Mo)" if taille else "")
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
            changelog.setPlainText(body)
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

        buttons.accepted.connect(on_download)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _apply_update(self, info: dict):
        """Telecharge l'archive applicative et la pose, puis redemarre.

        Rien d'executable n'est telecharge : le module recupere une archive
        ZIP et remplace les fichiers lui-meme, ce qui evite l'avertissement
        SmartScreen — un .exe telecharge porte la « marque du web », pas un
        fichier ecrit par un programme.
        """
        from PyQt6.QtWidgets import QProgressDialog

        dlg = QProgressDialog(T("update_downloading"), None, 0, 100, self)
        dlg.setWindowTitle(T("update_available"))
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def progression(fait, total):
            if total:
                dlg.setValue(int(fait * 100 / total))
            QApplication.processEvents()

        try:
            pose = updater.download_and_apply(info, progress=progression)
        except Exception as e:
            dlg.close()
            QMessageBox.warning(
                self, T("update_available"),
                T("tt_upd_failed").format(err=e))
            return
        dlg.close()

        if not pose:
            QMessageBox.warning(self, T("update_available"), T("update_failed"))
            return

        QMessageBox.information(self, T("update_available"), T("update_success"))

        # On ferme la fenetre plutot que de quitter l'application : c'est
        # closeEvent qui arrete le poller, ecrit le resume de session et
        # ferme les six fichiers de la nuit. Quitter sans passer par la
        # laisserait un .dat tronque.
        if updater.restart():
            self.close()
            QApplication.quit()

    def _create_desktop_shortcut(self):
        """Create a desktop shortcut for MountMonitor."""
        try:
            from shortcut_helper import create_shortcut_force
            create_shortcut_force("MountMonitor", "main.py", "logo.ico")
        except Exception as e:
            QMessageBox.warning(self,
                T("menu_create_shortcut"),
                f"Error: {e}")

    # ── Window lifecycle ─────────────────────────────────────────

    def _restaurer_panneaux(self):
        """Put the splitters back where the user last left them."""
        from PyQt6.QtCore import QByteArray
        for cle, sp in (("splitter_graphs", getattr(self, '_graph_splitter', None)),
                        ("splitter_main", getattr(self, '_h_splitter', None))):
            etat = self._settings.get(cle)
            if sp is not None and etat:
                try:
                    sp.restoreState(QByteArray.fromBase64(etat.encode('ascii')))
                except Exception as exc:
                    logger.debug(f"Splitter {cle} not restored: {exc}")

    def _enregistrer_panneaux(self):
        for cle, sp in (("splitter_graphs", getattr(self, '_graph_splitter', None)),
                        ("splitter_main", getattr(self, '_h_splitter', None))):
            if sp is not None:
                self._settings.set(cle, bytes(sp.saveState().toBase64()).decode('ascii'))

    def closeEvent(self, event):
        """Handle window close: save settings, stop everything."""
        # Save window geometry
        self._settings.set("window_width", self.width())
        self._settings.set("window_height", self.height())
        self._settings.set("window_x", self.x())
        self._settings.set("window_y", self.y())
        if self._fft_window:
            self._settings.set("fft_width", self._fft_window.width())
            self._settings.set("fft_height", self._fft_window.height())
        self._enregistrer_panneaux()
        self._settings.save()

        # Stop everything
        self._disconnect()

        if self._fft_window:
            self._fft_window.close()

        event.accept()
