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
    QApplication, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence

from .graph_widgets import TrackingGraph, TimeGraph, SeismicGraph
from .fft_window import FFTWindow
from .status_panel import StatusPanel
from .preferences_dialog import PreferencesDialog
from .theme import Colors
from ..config.settings import Settings
from ..core.mount_connection import MountConnection
from ..core.lx200_protocol import LX200Connection
from ..core.data_processor import DataProcessor
from ..core.poller import MountPoller
from ..core.ntp_client import NTPClient
from ..core.seismometer import Seismometer
from ..simulation.sim_mount import SimulatedMount
from ..simulation.sim_seismometer import SimulatedSeismometer
from ..logging_module.file_logger import FileLogger
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

        # Apply language setting
        lang = self._settings.get("language")
        set_language(lang)

        # Setup UI
        self._setup_window()
        self._create_menus()
        self._create_toolbar()
        self._create_central_widget()
        self._create_statusbar()

        # Refresh timer for graph updates
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_graphs)
        self._refresh_timer.setInterval(100)  # 10 fps graph update

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

        about_action = QAction(T("menu_about"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        bug_action = QAction(T("menu_report_bug"), self)
        bug_action.triggered.connect(self._report_bug)
        help_menu.addAction(bug_action)

    def _create_toolbar(self):
        """Create toolbar with main action buttons."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())
        self.addToolBar(toolbar)

        self._btn_connect = QPushButton("Connect / Connecter")
        self._btn_connect.setToolTip("EN: Connect to mount\nFR: Se connecter à la monture")
        self._btn_connect.clicked.connect(self._toggle_connection)
        toolbar.addWidget(self._btn_connect)

        self._btn_logging = QPushButton("Start Log / Démarrer log")
        self._btn_logging.setToolTip("EN: Start/stop data logging\nFR: Démarrer/arrêter l'enregistrement")
        self._btn_logging.setEnabled(False)
        self._btn_logging.clicked.connect(self._toggle_logging)
        toolbar.addWidget(self._btn_logging)

        toolbar.addSeparator()

        btn_fft = QPushButton("FFT")
        btn_fft.setToolTip("EN: Open FFT analysis\nFR: Ouvrir l'analyse FFT")
        btn_fft.clicked.connect(self._show_fft)
        toolbar.addWidget(btn_fft)

        btn_prefs = QPushButton(T("menu_preferences"))
        btn_prefs.setToolTip("EN: Open preferences\nFR: Ouvrir les préférences")
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

        graph_splitter.addWidget(self._ra_graph)
        graph_splitter.addWidget(self._dec_graph)
        graph_splitter.addWidget(self._time_graph)

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
        """Update window title with connection info."""
        title = f"MountMonitor v{self._version}"
        if self._connected and self._processor:
            freq = self._processor.actual_frequency
            if self._sim_mode != "none":
                title += f" | {freq:.1f}Hz simulation mode"
            else:
                protocol = self._settings.get("mount_protocol")
                if protocol == "lx200":
                    ip = self._settings.get("mount_ip")
                    port = self._settings.get("mount_port")
                    title += f" | {freq:.1f}Hz on TCP/IP {ip}:{port}"
                elif protocol == "ascom":
                    title += f" | {freq:.1f}Hz via ASCOM"
                else:
                    title += f" | {freq:.1f}Hz {protocol}"
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
        else:
            self._status_panel.add_message(
                f"Protocol {protocol} not yet implemented", Colors.STATUS_ERROR
            )
            return

        # Connect
        self._status_panel.add_message(T("connecting"))
        if not self._connection.connect():
            self._status_panel.add_message(T("connection_failed"), Colors.STATUS_ERROR)
            return

        self._connected = True
        self._status_panel.set_connected(True)
        self._btn_connect.setText("Disconnect / Déconnecter")
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
        self._btn_connect.setText("Connect / Connecter")
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
        """Handle mount status changes."""
        self._status_panel.update_status(status)
        if self._logging_active:
            self._file_logger.log_event(f"Mount status: {status.name}")

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
        """Handle initial mount info."""
        logger.info(f"Mount info: {info}")

    def _on_seismic_data(self, timestamp: float, values: list[float]):
        """Handle seismometer data callback."""
        self._processor.process_seismic_data(timestamp, values)

    # ── Graph refresh ────────────────────────────────────────────

    def _refresh_graphs(self):
        """Refresh all graphs with current buffer data. Called by timer."""
        # RA graph
        ra_t, ra_v = self._processor.ra_buffer.get_arrays()
        ra_stdev = self._processor.ra_buffer.get_stdev_array()
        if len(ra_t) > 0:
            self._ra_graph.update_data(
                ra_t, ra_v,
                stdev_values=ra_stdev if len(ra_stdev) == len(ra_t) else None,
                min_val=self._processor.ra_buffer.min_value,
                max_val=self._processor.ra_buffer.max_value,
                max_stdev=self._processor.ra_buffer.max_stdev,
            )
            self._ra_graph.set_tolerance(self._settings.get("tolerance_ra_arcsec"))

        # DEC graph
        dec_t, dec_v = self._processor.dec_buffer.get_arrays()
        dec_stdev = self._processor.dec_buffer.get_stdev_array()
        if len(dec_t) > 0:
            self._dec_graph.update_data(
                dec_t, dec_v,
                stdev_values=dec_stdev if len(dec_stdev) == len(dec_t) else None,
                min_val=self._processor.dec_buffer.min_value,
                max_val=self._processor.dec_buffer.max_value,
                max_stdev=self._processor.dec_buffer.max_stdev,
            )
            self._dec_graph.set_tolerance(self._settings.get("tolerance_dec_arcsec"))

        # Time graph
        diff_t, diff_v = self._processor.time_diff_buffer.get_arrays()
        pc_t, pc_v = self._processor.pc_loop_buffer.get_arrays()
        mt_t, mt_v = self._processor.mount_loop_buffer.get_arrays()
        ntp_t, ntp_v = self._processor.ntp_buffer.get_arrays()
        if len(diff_t) > 0:
            self._time_graph.update_data(
                diff_t, diff_v,
                pc_loop_t=pc_t, pc_loop_v=pc_v,
                mount_loop_t=mt_t, mount_loop_v=mt_v,
                ntp_t=ntp_t if len(ntp_t) > 0 else None,
                ntp_v=ntp_v if len(ntp_v) > 0 else None,
            )

        # Seismic graph
        sei_t, sei_v = self._processor.seismic_buffer.get_arrays()
        if len(sei_t) > 0:
            sei_stdev = self._processor.seismic_buffer.get_stdev_array()
            self._seismic_graph.update_data(
                sei_t, sei_v,
                stdev_values=sei_stdev if len(sei_stdev) == len(sei_t) else None,
            )

        # Update STDEV in status panel
        if len(ra_stdev) > 0 and len(dec_stdev) > 0:
            self._status_panel.update_stdev(ra_stdev[-1], dec_stdev[-1])

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
        """Update FFT window with current data."""
        if not self._fft_window or not self._fft_window.isVisible():
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

        self._fft_window.update_fft(
            ra_freqs=ra_freqs, ra_mags=ra_mags,
            dec_freqs=dec_freqs, dec_mags=dec_mags,
            sei_freqs=sei_freqs, sei_mags=sei_mags,
            ra_sample_rate=freq, dec_sample_rate=freq,
            sei_sample_rate=sei_rate if len(sei_data) > 0 else None,
        )

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
        self._btn_logging.setText("Stop Log / Arrêter log")
        self._status_panel.add_message(T("logging_started"), Colors.STATUS_OK)

    def _stop_logging(self):
        """Stop data logging."""
        if not self._logging_active:
            return
        self._file_logger.close()
        self._logging_active = False
        self._btn_logging.setText("Start Log / Démarrer log")
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

        <h3>Keyboard Shortcuts</h3>
        <ul>
        <li><b>Ctrl+K</b>: Connect</li>
        <li><b>Ctrl+D</b>: Disconnect</li>
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
        <p>Stored in <code>Logs/</code> folder. Four file types:
        .log (events), .dat (mount data), .dti (time data), .sei (seismic).</p>
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

        <h3>Raccourcis clavier</h3>
        <ul>
        <li><b>Ctrl+K</b> : Connecter</li>
        <li><b>Ctrl+D</b> : Déconnecter</li>
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
        <p>Stockés dans le dossier <code>Logs/</code>. Quatre types :
        .log (événements), .dat (données monture), .dti (données temps), .sei (sismique).</p>
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

    def _report_bug(self):
        """Open bug report dialog."""
        import webbrowser
        webbrowser.open("https://github.com/ARP273-ROSE/MountMonitor/issues/new")

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
