"""Main window for MountMonitor.

Assembles all components: graphs, status panel, menus, toolbar.
Manages the connection lifecycle and data flow.
"""

import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QPushButton, QLabel, QMessageBox,
    QApplication, QStatusBar, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence

from .graph_widgets import TrackingGraph, TimeGraph, SeismicGraph, AxialGraph
from .fft_window import FFTWindow
from .analysis_dialog import AnalysisDialog
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
from ..logging_module.crash_reporter import CrashReporter
from ..models.mount_data import MountSample, MountStatus, SessionInfo, ConnectionProtocol
from ..utils.i18n import T, set_language, get_language
from ..utils.coordinates import format_ra, format_dec

logger = logging.getLogger(__name__)


def _read_version() -> str:
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "1.0.0"


class MainWindow(QMainWindow):
    """Main application window."""

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

        # Auto-connect in simulation mode
        if sim_mode != "none":
            QTimer.singleShot(500, self._connect)

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
        connect_action.setToolTip("EN: Connect to mount\nFR: Se connecter à la monture")
        connect_action.triggered.connect(self._connect)
        file_menu.addAction(connect_action)
        self._connect_action = connect_action

        disconnect_action = QAction(T("disconnected"), self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+D"))
        disconnect_action.setToolTip("EN: Disconnect from mount\nFR: Se déconnecter de la monture")
        disconnect_action.triggered.connect(self._disconnect)
        disconnect_action.setEnabled(False)
        file_menu.addAction(disconnect_action)
        self._disconnect_action = disconnect_action

        file_menu.addSeparator()

        open_log_action = QAction(T("menu_open_log"), self)
        open_log_action.setShortcut(QKeySequence("Ctrl+O"))
        open_log_action.setToolTip(
            "EN: Open and analyze a previous log file\n"
            "FR: Ouvrir et analyser un fichier log précédent"
        )
        open_log_action.triggered.connect(self._open_log_file)
        file_menu.addAction(open_log_action)

        open_log10m_action = QAction(T("menu_open_log10m"), self)
        open_log10m_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_log10m_action.setToolTip(
            "EN: Analyze 10micron mount internal log files (.log10m)\n"
            "FR: Analyser les fichiers log internes de la monture 10micron (.log10m)"
        )
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
            action.setToolTip(f"EN: Set horizontal zoom to {zoom}x\nFR: Zoom horizontal {zoom}x")
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
        fft_action.setToolTip("EN: Open FFT analysis window\nFR: Ouvrir la fenêtre d'analyse FFT")
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
        pref_action.setToolTip("EN: Open preferences\nFR: Ouvrir les préférences")
        pref_action.triggered.connect(self._show_preferences)
        edit_menu.addAction(pref_action)

        # Help menu
        help_menu = menubar.addMenu(T("menu_help"))

        help_action = QAction(T("menu_help_contents"), self)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self._show_help)
        help_menu.addAction(help_action)

        online_help_action = QAction(T("menu_online_help"), self)
        online_help_action.setToolTip(
            "EN: Open online documentation\nFR: Ouvrir la documentation en ligne"
        )
        online_help_action.triggered.connect(self._show_online_help)
        help_menu.addAction(online_help_action)

        help_menu.addSeparator()

        about_action = QAction(T("menu_about"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        bug_action = QAction(T("menu_report_bug"), self)
        bug_action.triggered.connect(self._report_bug)
        help_menu.addAction(bug_action)

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
        h_splitter.addWidget(graph_splitter)
        h_splitter.addWidget(self._status_panel)

        # Set proportions (graphs take ~75%, status ~25%)
        ratio = self._settings.get("graph_textbox_ratio")
        h_splitter.setSizes([ratio * 200, 200])

        main_layout.addWidget(h_splitter)

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
            self._connection = LX200SerialConnection(port=serial_port)
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
        if self._logging_active:
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
        if self._logging_active:
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
        if self._logging_active:
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
        if self._logging_active:
            if sample.temperature_ext is not None:
                self._file_logger.log_event(
                    f"ENV\tTemp={sample.temperature_ext:.1f}°C "
                    f"Press={sample.pressure:.1f}mbar "
                    f"IntTemp={sample.temperature_int:.1f if sample.temperature_int is not None else '?'}°C"
                )

    def _on_seismic_data(self, timestamp: float, values: list[float]):
        """Handle seismometer data callback."""
        self._processor.process_seismic_data(timestamp, values)

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
        if self._logging_active:
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
        else:
            self._start_logging()

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
            start_time=datetime.now(),
        )
        self._file_logger.start_session(session)
        self._logging_active = True
        self._btn_logging.setText(T("btn_stop_log"))
        # Start FFT timer for logging even if FFT window is not open
        if not self._fft_timer.isActive():
            self._fft_timer.start()
        self._status_panel.add_message(T("logging_started"), Colors.STATUS_OK)

    def _stop_logging(self):
        """Stop data logging."""
        if not self._logging_active:
            return
        self._file_logger.close()
        self._logging_active = False
        self._btn_logging.setText(T("btn_start_log"))
        self._status_panel.add_message(T("logging_stopped"))

    def _new_log_files(self):
        """Close current files and open new ones."""
        if self._logging_active:
            session = SessionInfo(
                version=self._version,
                observatory=self._settings.get("observatory_name"),
                mount_name=self._settings.get("mount_name"),
                protocol=ConnectionProtocol.SIMULATION
                    if self._sim_mode != "none" else ConnectionProtocol(self._settings.get("mount_protocol")),
                start_time=datetime.now(),
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

        # Load data into graphs
        self._replay_session(session)

        # Show FFT from replayed data
        self._replay_fft(session)

        # Open analysis dialog
        QApplication.processEvents()
        dialog = AnalysisDialog(session, self)
        dialog.exec()

        self._status_panel.add_message(
            T("analysis_complete"), Colors.STATUS_OK
        )

    def _replay_session(self, session):
        """Load parsed session data into the graph widgets."""
        # RA graph
        if len(session.ra_deviations) > 0:
            self._ra_graph.update_data(
                session.timestamps, session.ra_deviations,
                stdev_values=session.ra_stdevs if len(session.ra_stdevs) == len(session.timestamps) else None,
                min_val=float(np.min(session.ra_deviations)),
                max_val=float(np.max(session.ra_deviations)),
                max_stdev=float(np.max(session.ra_stdevs)) if len(session.ra_stdevs) > 0 and np.any(session.ra_stdevs > 0) else None,
            )

        # DEC graph
        if len(session.dec_deviations) > 0:
            self._dec_graph.update_data(
                session.timestamps, session.dec_deviations,
                stdev_values=session.dec_stdevs if len(session.dec_stdevs) == len(session.timestamps) else None,
                min_val=float(np.min(session.dec_deviations)),
                max_val=float(np.max(session.dec_deviations)),
                max_stdev=float(np.max(session.dec_stdevs)) if len(session.dec_stdevs) > 0 and np.any(session.dec_stdevs > 0) else None,
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
        self._settings.set("horizontal_zoom", zoom)

    def _set_vertical_zoom(self, mode: str):
        self._ra_graph.set_vertical_zoom(mode)
        self._dec_graph.set_vertical_zoom(mode)
        self._settings.set("vertical_zoom_mode", mode)

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

    def _show_preferences(self):
        """Show preferences dialog."""
        dialog = PreferencesDialog(self._settings, self)
        if dialog.exec():
            self._apply_settings()

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

    def _show_help(self):
        """Show help dialog with detailed bilingual help."""
        lang = get_language()
        if lang == "fr":
            title = "Aide - MountMonitor"
            text = self._get_help_text_fr()
        else:
            title = "Help - MountMonitor"
            text = self._get_help_text_en()

        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _get_help_text_en(self) -> str:
        return """
        <h2>MountMonitor v{version}</h2>
        <p><b>Real-time telescope mount monitoring for astrophotography.</b></p>

        <h3>Quick Start</h3>
        <ol>
        <li>Set your mount connection in <b>Preferences</b> (IP, port, protocol)</li>
        <li>Click <b>Connect</b> to start monitoring</li>
        <li>Data logging starts automatically</li>
        </ol>

        <h3>Graphs</h3>
        <ul>
        <li><b>RA graph (magenta)</b>: Right Ascension deviation from reference</li>
        <li><b>DEC graph (red)</b>: Declination deviation from reference</li>
        <li><b>Time graph</b>: PC-Mount time difference, loop times, NTP offset</li>
        <li><b>Seismic graph</b>: Seismometer data (if connected)</li>
        </ul>
        <p>Blue line = running standard deviation. Green lines = tolerance limits.</p>

        <h3>FFT Analysis</h3>
        <p>View > FFT or Ctrl+F. Shows frequency and period domain of RA/DEC/seismic data.
        Useful for identifying vibration sources.</p>

        <h3>Night Report &amp; Adaptive Scoring (v1.6.0)</h3>
        <p>The night analysis report now <b>automatically detects unguided precision mounts</b>
        (10Micron, Planewave, ASA DDM) and adapts scoring thresholds accordingly:</p>
        <ul>
        <li><b>Guided mounts</b>: Excellent &lt;0.5" | Good &lt;1.5" | Fair &lt;3.0"</li>
        <li><b>Unguided precision</b>: Excellent &lt;2.0" | Good &lt;4.0" | Fair &lt;8.0"</li>
        </ul>
        <p>Detection uses mount name, ASCOM driver, and firmware fields.</p>

        <h3>Performance (v1.6.0)</h3>
        <ul>
        <li>Numpy array caching with dirty flags (no redundant copies)</li>
        <li>Graph downsampling: max 5,000 points displayed from 50K+ buffer</li>
        <li>250ms refresh timer (4 fps) — smooth and CPU-efficient</li>
        <li>Lightweight QPlainTextEdit status panel</li>
        <li>Stylesheet caching, STDEV computed outside lock, cached pen/font objects</li>
        </ul>
        <p>Stable for 8h+ sessions without any degradation.</p>

        <h3>Security (v1.6.0)</h3>
        <ul>
        <li>LX200 response buffer limited to 4,096 bytes (anti-DoS)</li>
        <li>Log header sanitization (anti-injection)</li>
        <li>Periodic flush every 20 writes (NAS-optimized)</li>
        </ul>

        <h3>Keyboard Shortcuts</h3>
        <ul>
        <li><b>Ctrl+K</b>: Connect</li>
        <li><b>Ctrl+D</b>: Disconnect</li>
        <li><b>Ctrl+O</b>: Open log (replay + analysis)</li>
        <li><b>Ctrl+F</b>: FFT window</li>
        <li><b>Ctrl+,</b>: Preferences</li>
        <li><b>F1</b>: This help</li>
        </ul>

        <h3>Protocols</h3>
        <ul>
        <li><b>LX200</b>: TCP/IP for 10Micron and compatible mounts</li>
        <li><b>ASCOM</b>: Windows ASCOM drivers (requires comtypes)</li>
        <li><b>Simulation</b>: Test mode with simulated data</li>
        </ul>

        <h3>Log Files</h3>
        <p>Stored in <code>Logs/</code> folder. Six file types:
        .log (events), .dat (mount data), .dti (time data), .sei (seismic),
        .fft (FFT snapshots), .env (environment/diagnostics).</p>
        <p>Logging starts automatically on connection.</p>

        <h3>Log Replay &amp; Analysis</h3>
        <p><b>File → Open Log</b> or <b>Ctrl+O</b>: Load a previous .dat file to replay in graphs
        and get a comprehensive analysis report (quality rating, FFT, drift, tolerance stats).</p>
        <p><b>Auto-analysis on park</b>: When the mount parks, an automatic analysis of the
        night session is generated.</p>
        """.format(version=self._version)

    def _get_help_text_fr(self) -> str:
        return """
        <h2>MountMonitor v{version}</h2>
        <p><b>Surveillance en temps réel de monture télescope pour l'astrophotographie.</b></p>

        <h3>Démarrage rapide</h3>
        <ol>
        <li>Configurez la connexion dans les <b>Préférences</b> (IP, port, protocole)</li>
        <li>Cliquez sur <b>Connecter</b> pour démarrer la surveillance</li>
        <li>L'enregistrement démarre automatiquement</li>
        </ol>

        <h3>Graphiques</h3>
        <ul>
        <li><b>Graphe AD (magenta)</b> : Déviation en Ascension Droite par rapport à la référence</li>
        <li><b>Graphe DÉC (rouge)</b> : Déviation en Déclinaison par rapport à la référence</li>
        <li><b>Graphe temps</b> : Différence PC-Monture, temps de boucle, décalage NTP</li>
        <li><b>Graphe sismique</b> : Données sismomètre (si connecté)</li>
        </ul>
        <p>Ligne bleue = écart-type glissant. Lignes vertes = limites de tolérance.</p>

        <h3>Analyse FFT</h3>
        <p>Affichage > FFT ou Ctrl+F. Montre le domaine fréquentiel et temporel des données AD/DÉC/sismiques.
        Utile pour identifier les sources de vibration.</p>

        <h3>Rapport de nuit et scoring adaptatif (v1.6.0)</h3>
        <p>Le rapport d'analyse détecte automatiquement les <b>montures de précision non-guidées</b>
        (10Micron, Planewave, ASA DDM) et adapte les seuils de notation :</p>
        <ul>
        <li><b>Monture guidée</b> : Excellent &lt;0.5" | Bon &lt;1.5" | Correct &lt;3.0"</li>
        <li><b>Précision non-guidée</b> : Excellent &lt;2.0" | Bon &lt;4.0" | Correct &lt;8.0"</li>
        </ul>
        <p>Détection via nom de monture, driver ASCOM et firmware.</p>

        <h3>Performance (v1.6.0)</h3>
        <ul>
        <li>Cache numpy avec dirty flags (pas de copies redondantes)</li>
        <li>Downsampling graphiques : max 5 000 points affichés sur 50K+ en buffer</li>
        <li>Timer de rafraîchissement 250ms (4 fps) — fluide et économe en CPU</li>
        <li>Panneau de statut QPlainTextEdit léger</li>
        <li>Cache CSS, STDEV calculé hors verrou, pen/font cachés</li>
        </ul>
        <p>Stable pour des sessions de 8h+ sans dégradation.</p>

        <h3>Sécurité (v1.6.0)</h3>
        <ul>
        <li>Buffer réponse LX200 limité à 4 096 octets (anti-DoS)</li>
        <li>Sanitisation des en-têtes log (anti-injection)</li>
        <li>Flush périodique toutes les 20 écritures (optimisé NAS)</li>
        </ul>

        <h3>Raccourcis clavier</h3>
        <ul>
        <li><b>Ctrl+K</b> : Connecter</li>
        <li><b>Ctrl+D</b> : Déconnecter</li>
        <li><b>Ctrl+O</b> : Ouvrir un log (relecture + analyse)</li>
        <li><b>Ctrl+F</b> : Fenêtre FFT</li>
        <li><b>Ctrl+,</b> : Préférences</li>
        <li><b>F1</b> : Cette aide</li>
        </ul>

        <h3>Protocoles</h3>
        <ul>
        <li><b>LX200</b> : TCP/IP pour montures 10Micron et compatibles</li>
        <li><b>ASCOM</b> : Drivers ASCOM Windows (nécessite comtypes)</li>
        <li><b>Simulation</b> : Mode test avec données simulées</li>
        </ul>

        <h3>Fichiers log</h3>
        <p>Stockés dans le dossier <code>Logs/</code>. Six types :
        .log (événements), .dat (données monture), .dti (temps), .sei (sismique),
        .fft (FFT), .env (environnement/diagnostic).</p>
        <p>L'enregistrement démarre automatiquement à la connexion.</p>

        <h3>Relecture et analyse des logs</h3>
        <p><b>Fichier → Ouvrir un log</b> ou <b>Ctrl+O</b> : charger un fichier .dat pour
        revisualiser les graphiques et obtenir un rapport d'analyse complet
        (qualité, FFT, dérive, tolérance).</p>
        <p><b>Analyse auto au parcage</b> : quand la monture se parque, l'analyse
        de la nuit se lance automatiquement.</p>
        """.format(version=self._version)

    def _show_about(self):
        """Show about dialog."""
        lang = get_language()
        if lang == "fr":
            text = (
                f"<h2>MountMonitor v{self._version}</h2>"
                f"<p>Surveillance de monture télescope en temps réel.</p>"
                f"<p>Réécriture modernisée du programme original Java v3.37<br>"
                f"par Nicolas de Hilster (2018-2021).</p>"
                f"<p>Python/PyQt6/pyqtgraph</p>"
            )
        else:
            text = (
                f"<h2>MountMonitor v{self._version}</h2>"
                f"<p>Real-time telescope mount monitoring.</p>"
                f"<p>Modernized rewrite of the original Java v3.37<br>"
                f"by Nicolas de Hilster (2018-2021).</p>"
                f"<p>Python/PyQt6/pyqtgraph</p>"
            )
        QMessageBox.about(self, T("menu_about"), text)

    def _show_online_help(self):
        """Open online help / documentation in browser."""
        import webbrowser
        webbrowser.open("https://github.com/ARP273-ROSE/MountMonitor")

    def _report_bug(self):
        """Open bug report dialog."""
        import webbrowser
        webbrowser.open("https://github.com/ARP273-ROSE/MountMonitor/issues/new")

    def _create_desktop_shortcut(self):
        """Create a desktop shortcut for MountMonitor."""
        try:
            from shortcut_helper import create_shortcut_force
            create_shortcut_force("MountMonitor", "mountmonitor.py", "logo.ico")
        except Exception as e:
            QMessageBox.warning(self,
                T("menu_create_shortcut"),
                f"Error: {e}")

    # ── Window lifecycle ─────────────────────────────────────────

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
        self._settings.save()

        # Stop everything
        self._disconnect()

        if self._fft_window:
            self._fft_window.close()

        event.accept()
