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

from .graph_widgets import (TrackingGraph, TimeGraph, SeismicGraph, AxialGraph,
                            couper_au_present, largeur_fenetre,
                            largeur_affichee, nom_largeur, derive_horloge,
                            LARGEURS_S)
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
from ..core.data_processor import DataProcessor, ecarts_a_la_mediane
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



class TravailFinDeNuit(QThread):
    """Reads a finished session ONCE and writes its three reports, off the GUI.

    At dawn and at every park the window used to parse the .dat twice and
    write the reports on the GUI thread: about 7 s frozen for a 10 Hz night
    here, 25 s or more on a small mini-PC (a minute and a half for a long
    night), with the freeze watchdog firing. One thread is enough on two
    cores; the session comes back by a signal and the window is built then.
    """
    fini = pyqtSignal(str, object, object)     # dat path, session or None, main report path

    def __init__(self, chemin_dat, langue: str, ecrire: bool, parent=None):
        super().__init__(parent)
        self._chemin = str(chemin_dat)
        self._langue = langue
        self._ecrire = ecrire

    def run(self):
        session, sortie = None, None
        try:
            session = parse_session(Path(self._chemin))
            if self._ecrire:
                sortie = sauver_rapport(self._chemin, self._langue, session=session)
        except Exception as e:
            logger.error(f"End-of-night processing failed: {e}")
        self.fini.emit(self._chemin, session, sortie)

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
    # The seismometer reads in its own thread; its data crosses over by this
    # queued signal. It used to call _on_seismic_data directly from that
    # thread, writing the .sei/.dat files the GUI thread was writing too.
    sismique_recue = pyqtSignal(float, object)
    maj_progression = pyqtSignal(int)
    maj_posee = pyqtSignal(bool, str)

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
        self._connexion_en_cours = False
        # Pollers whose thread has not ended yet (stuck in a driver): kept
        # referenced, a QThread destroyed while running aborts the process.
        self._pollers_finissants: list = []
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
        # Chemin du .dat que CE lancement a ferme. Tant qu'il est None, il n'y
        # a rien a analyser automatiquement.
        self._derniere_session = None
        self._fen_analyse = None
        self._session_analysee = None
        self._aube_timer = None
        self._timer_armement = None
        self._travaux_nuit: dict = {}
        self._analyse_demandee: set = set()
        self._session_lue = None
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
        # 4 fps, 2 fps from the start on a small PC; adapted while running.
        self._cadence_min = 1 if (os.cpu_count() or 2) <= 4 else 0
        self._refresh_timer.setInterval(self.CADENCES_MS[self._cadence_min])

        # FFT timer (slower)
        self._fft_timer = QTimer()
        self._fft_timer.timeout.connect(self._update_fft)
        self._fft_timer.setInterval(2000)  # Every 2 seconds

        # Verification des mises a jour, en fond, au demarrage.
        self.maj_trouvee.connect(self._maj_reperee)
        self.sismique_recue.connect(self._on_seismic_data)
        self.maj_progression.connect(self._maj_progression)
        self.maj_posee.connect(self._maj_terminee)
        QTimer.singleShot(3000, self._check_updates_silent)

        # Auto-connect in simulation mode
        self._essais_connexion = 0
        self._connexion_auto_active = False
        if sim_mode != "none":
            QTimer.singleShot(500, self._connect)
        elif auto_connect or self._settings.get("connect_on_launch"):
            # Unattended start of the observatory PC: the window comes up
            # before the control box has finished booting, so the first
            # attempt often fails. Keep trying until it answers.
            self._connexion_auto_active = True
            QTimer.singleShot(1500, self._connexion_automatique)

        self._appliquer_zoom_horizontal(1)
        self._set_vertical_zoom(self._settings.get("vertical_zoom_mode") or "data",
                                enregistrer=False)
        self._brancher_menus_graphes()

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

        # Time span and vertical scale: same submenus as the right click on
        # a graph (_menu_graphe), checked on the current choice.
        self._remplir_menu_largeur(view_menu.addMenu(T("time_span")))
        self._remplir_menu_vertical(view_menu.addMenu(T("vertical_zoom")))

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

        # Kit commun : signalement vers le point de collecte et case
        # d'accord des rapports automatiques (le manuel et les mises a jour
        # ont deja leurs entrees ci-dessus et ci-dessous ; l'accord est
        # demande par main.py au premier lancement).
        try:
            from kit_aide import AideKit
            from src.config.paths import dossier_journaux
            self._aide_kit = AideKit(
                self, self._version, get_language, [], nom_fil="mountmonitor",
                etat=lambda: {"langue": get_language(), "simulation": self._sim_mode},
                journal=dossier_journaux() / "mountmonitor_app.log")
            self._aide_kit.remplir_menu(help_menu, avec_manuel=False, avec_maj=False)
        except Exception:
            logger.debug("Menu du kit indisponible", exc_info=True)

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
        # Right click: the automatic options, where they are needed. In the
        # Preferences alone they went unnoticed (a user observing the Sun by
        # day did not know recording could be allowed in daylight).
        self._btn_logging.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_logging.customContextMenuRequested.connect(self._menu_enregistrement)
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
        # A click by the user ends the automatic attempts, whatever its effect.
        self._connexion_auto_active = False
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connexion_automatique(self):
        """Connect at launch; on failure, try again every connect_retry_s s.

        Stops at the first success, or as soon as the user takes over (click on
        Connect/Disconnect). Never opens a dialog: on an unattended start nobody
        is there to answer it."""
        if not self._connexion_auto_active or self._connected:
            self._connexion_auto_active = False
            return
        protocol = self._settings.get("mount_protocol")
        if protocol == "ascom" and not self._settings.get("ascom_driver"):
            # _connect would open the ASCOM Chooser and wait for a click.
            self._status_panel.add_message(T("no_ascom_driver"), Colors.STATUS_ERROR)
            self._connexion_auto_active = False
            return
        if protocol == "lx200_serial" and not self._settings.get("serial_port"):
            self._status_panel.add_message(T("no_serial_port"), Colors.STATUS_ERROR)
            self._connexion_auto_active = False
            return
        self._essais_connexion += 1
        self._connect()      # the answer comes back in _on_connect_result

    def _replanifier_connexion_auto(self):
        if not self._connexion_auto_active or self._connected:
            self._connexion_auto_active = False
            return
        brut = self._settings.get("connect_retry_s")
        delai = max(5, int(30 if brut is None else brut))
        self._status_panel.add_message(
            T("auto_connect_retry").format(n=self._essais_connexion, s=delai),
            Colors.STATUS_WARNING)
        QTimer.singleShot(delai * 1000, self._connexion_automatique)

    def _connect(self):
        """Connect to the mount.

        The connection is opened in the poller thread: an unreachable mount
        (5 s timeout) or a slow ASCOM driver used to freeze the window, every
        30 s while --connect waited for the mount. The rest of the start-up
        happens in _on_connect_result."""
        if self._connected or self._connexion_en_cours:
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

        self._status_panel.add_message(T("connecting"))
        self._poller = MountPoller(
            self._connection, self._processor,
            frequency_hz=self._settings.get("polling_frequency_hz"),
        )
        self._poller.set_axial_enabled(self._settings.get("axial_mode") != "off")
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
        self._poller.mount_info_ready.connect(self._on_mount_info)
        self._poller.environment_ready.connect(self._on_environment)
        self._poller.connect_in_thread()
        self._connexion_en_cours = True
        self._poller.start()

    @pyqtSlot(object, object)
    def _on_request_done(self, callback, result):
        try:
            callback(result)
        except Exception as e:
            logger.warning(f"Mount request callback failed: {e}")

    def _demande_monture(self, fn, callback=None):
        """Ask the poller thread to run fn(connection); never blocks the GUI."""
        if self._poller is not None and self._connected:
            self._poller.submit(fn, callback)

    def _liberer_poller(self, poller):
        if poller is None:
            return
        if not poller.stop():
            logger.warning("Poller thread still busy in the driver; kept until it ends")
            self._pollers_finissants.append(poller)
            poller.finished.connect(lambda p=poller: self._pollers_finissants.remove(p)
                                    if p in self._pollers_finissants else None)

    @pyqtSlot(bool)
    def _on_connect_result(self, ok: bool):
        self._connexion_en_cours = False
        if not ok:
            self._status_panel.add_message(T("connection_failed"), Colors.STATUS_ERROR)
            poller, self._poller = self._poller, None
            self._liberer_poller(poller)
            self._connection = None
            if self._connexion_auto_active:
                self._replanifier_connexion_auto()
            return
        self._connexion_auto_active = False

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
            sim_sei.set_callback(self.sismique_recue.emit)
            sim_sei.start()
            self._seismometer = sim_sei
            self._status_panel.add_message(T("sim_seismometer"), Colors.STATUS_WARNING)
        else:
            self._appliquer_sismometre()

        # Logging starts on connection -- but ARMED if that is what the user
        # asked for. This call used to go straight to _start_logging, which
        # bypassed the arming entirely: connecting to a parked mount at 08:38
        # began recording at once, which is precisely what arming exists to
        # avoid.
        if (self._settings.get("autostart_on_tracking")
                and self._prev_mount_status != MountStatus.TRACKING):
            self._armer()
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
        self._liberer_poller(poller)

        if self._ntp_client:
            self._ntp_client.stop()
            self._ntp_client = None

        if self._seismometer:
            if hasattr(self._seismometer, 'stop'):
                self._seismometer.stop()
            self._seismometer = None
            self._config_sei_actuelle = None

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
        elif self._logging_armed:
            self._maj_bouton_armement()
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

            # Auto-analysis on park: only for a session THIS run recorded.
            # It used to fire on any PARKED status and analyse the newest
            # .dat lying on disk, so connecting to an already-parked mount
            # opened a report on a night that had nothing to do with it.
            if getattr(self, '_derniere_session', None) is not None:
                self._auto_analyze_on_park()

        # After slew ends and tracking resumes → run checks + get target coords
        if was_slewing and now_tracking:
            QTimer.singleShot(1000, self._run_mount_checks)
            # Retrieve target coordinates for reference mode
            if self._settings.get("reference_mode") == "target":
                self._demande_monture(
                    lambda c: (c.get_target_ra(), c.get_target_dec()),
                    self._recevoir_cible)

    def _recevoir_cible(self, cible):
        target_ra, target_dec = cible or (None, None)
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
            f"{T('pan_mount')} : {product}", Colors.STATUS_OK
        )
        self._status_panel.add_message(
            f"{T('pan_firmware')} : {firmware}"
        )
        if mount_id:
            self._status_panel.add_message(f"{T('pan_id')} : {mount_id}")
        if pier_side and hasattr(pier_side, 'value'):
            self._status_panel.add_message(f"{T('pan_pier')} : {pier_side.value}")
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

    @pyqtSlot(float, object)
    def _on_seismic_data(self, timestamp: float, values: list[float]):
        """Handle seismometer data (GUI thread, via sismique_recue)."""
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
            for t, v in zip(self._processor.seismic_times(timestamp, len(values)), values):
                self._file_logger.log_seismic_data(t, v + offset, v, stdev)

    # ── Graph refresh ────────────────────────────────────────────

    # Graph cadence: 4 per second where the machine allows it. On a small PC
    # (2-4 cores) it starts at 2 per second, and on any machine it slows down
    # (to 1 per second) when drawing takes too long, then speeds up again.
    CADENCES_MS = (250, 500, 1000)

    def _refresh_graphs(self):
        """Timer slot: skip when nobody can see the window, adapt the cadence."""
        if self.isMinimized() or not self.isVisible():
            return
        t0 = time.perf_counter()
        try:
            self._refresh_graphs_now()
        finally:
            # Drawing happens after this slot, in the event loop; it costs
            # about as much as the update itself: count it twice.
            cout = 2.0 * (time.perf_counter() - t0) * 1000.0
            self._adapter_cadence(cout)

    def _adapter_cadence(self, cout_ms: float):
        actuel = self._refresh_timer.interval()
        cadences = self.CADENCES_MS
        i = cadences.index(actuel) if actuel in cadences else 0
        moyenne = 0.8 * getattr(self, "_cout_rafraichissement", cout_ms) + 0.2 * cout_ms
        self._cout_rafraichissement = moyenne
        if moyenne > 0.4 * actuel and i + 1 < len(cadences):
            self._refresh_timer.setInterval(cadences[i + 1])
        elif i > self._cadence_min and moyenne < 0.1 * cadences[i - 1]:
            self._refresh_timer.setInterval(cadences[i - 1])

    def _refresh_graphs_now(self):
        """Refresh all graphs with current buffer data.

        Les graphes defilent au present : chacun ne recoit que les
        `largeur_fenetre(zoom)` dernieres secondes, a pleine resolution
        (deux minutes, c'est quelques centaines d'echantillons). Les
        statistiques de la nuit (min/max/ecart-type maximal) restent
        calculees sur tout le tampon, par DataBuffer.
        """
        largeur = self._largeur()

        # Graph correction: shift STDEV timestamps back by half running range
        correct = self._settings.get("correct_graphs_for_range")
        half_range = self._settings.get("running_range_seconds") / 2.0 if correct else 0.0

        # Only the visible tail is copied out of each buffer (get_tail): the
        # previous version rebuilt seven 50,000-element arrays four times a
        # second to keep about a thousand points of each.
        # RA / DEC
        # Positions are drawn from the RAW coordinates, around the median of
        # what is visible (ecarts_a_la_mediane), in the RA unit chosen in the
        # preferences: seconds of time (hours mode) or arcseconds of RA
        # (degrees mode, 15 times more), like MountMonitor 3. The running
        # sigma is computed on sky (x cos dec) and converted the same way.
        p = self._processor
        en_degres = bool(self._settings.get("ra_in_degrees"))
        cos_d = max(abs(np.cos(np.radians(p.declination_deg))), 1e-3)
        k_ra = (1.0 if en_degres else 1.0 / 15.0) / cos_d     # sky " -> unit
        self._ra_graph.set_unite('"' if en_degres else 's')
        for raw, buf, graphe, facteur, tour, k_sd, tol in (
                (p.ra_raw_buffer, p.ra_buffer, self._ra_graph,
                 54000.0 if en_degres else 3600.0, 24.0, k_ra,
                 self._tolerance_ra_affichee()),
                (p.dec_raw_buffer, p.dec_buffer, self._dec_graph,
                 3600.0, None, 1.0, self._settings.get("tolerance_dec_arcsec"))):
            t, brut, _, _ = raw.get_tail(largeur)
            if len(t) == 0:
                continue
            v = ecarts_a_la_mediane(brut, facteur, tour)
            _, _, sd_t, sd = buf.get_tail(largeur, float(t[-1]))
            graphe.update_data(
                t, v,
                stdev_values=sd * k_sd if len(sd) else None,
                stdev_timestamps=(sd_t - half_range) if len(sd) else None,
                min_val=float(np.min(v)),
                max_val=float(np.max(v)),
                max_stdev=(buf.max_stdev or 0.0) * k_sd,
                largeur_s=largeur,
            )
            graphe.set_tolerance(tol)

        # Time graph
        diff_t, diff_v, _, _ = self._processor.time_diff_buffer.get_tail(largeur)
        if len(diff_t) > 0:
            fin = float(diff_t[-1])
            pc_t, pc_v, _, _ = self._processor.pc_loop_buffer.get_tail(largeur, fin)
            mt_t, mt_v, _, _ = self._processor.mount_loop_buffer.get_tail(largeur, fin)
            ntp_t, ntp_v, _, _ = self._processor.ntp_buffer.get_tail(largeur, fin)
            self._time_graph.update_data(
                diff_t, diff_v,
                pc_loop_t=pc_t, pc_loop_v=pc_v,
                mount_loop_t=mt_t, mount_loop_v=mt_v,
                ntp_t=ntp_t if len(ntp_t) > 0 else None,
                ntp_v=ntp_v if len(ntp_v) > 0 else None,
                largeur_s=largeur,
                derive_ms_h=self._derive_horloge(),
            )

        # Axial graph
        if self._settings.get("axial_mode") != "off":
            bufs = (self._processor.ra_speed_raw_buffer,
                    self._processor.dec_speed_raw_buffer,
                    self._processor.ra_speed_avg_buffer,
                    self._processor.dec_speed_avg_buffer)
            fins = [t[-1] for t in (b.get_last_n(1)[0] for b in bufs) if len(t)]
            if fins:
                fin = float(max(fins))
                args = {}
                for nom, b in zip(("ra_raw", "dec_raw", "ra_avg", "dec_avg"), bufs):
                    t, v, _, _ = b.get_tail(largeur, fin)
                    args[nom + "_t"] = t if len(t) > 0 else None
                    args[nom + "_v"] = v if len(t) > 0 else None
                self._axial_graph.update_data(largeur_s=largeur, **args)

        # Seismic graph
        sei_t, sei_v, sei_sd_t, sei_sd = self._processor.seismic_buffer.get_tail(largeur)
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
                largeur_s=largeur,
            )

        # Update STDEV in status panel (last value of the night computation)
        full_ra_stdev = self._processor.ra_buffer.get_stdev_array()
        full_dec_stdev = self._processor.dec_buffer.get_stdev_array()
        if len(full_ra_stdev) > 0 and len(full_dec_stdev) > 0:
            self._status_panel.update_stdev(full_ra_stdev[-1], full_dec_stdev[-1])

        # A write error (disk full, network share gone) is said once.
        erreur = getattr(self._file_logger, "erreur_ecriture", None)
        if erreur and not getattr(self, "_erreur_ecriture_dite", False):
            self._erreur_ecriture_dite = True
            self._status_panel.add_message(f"\u26a0 {T('write_error')} : {erreur}",
                                           Colors.STATUS_ERROR)

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

        # On the real timestamps: the sampling rate is measured on the data
        # (max(1, actual_frequency) forced 1 Hz on a 0.5 Hz poll), gaps are
        # skipped, drift and dither steps removed (src/core/spectre.py).
        from ..core.spectre import spectre, spectre_regulier

        def frequence(t):
            if len(t) < 2:
                return 0.0
            d = np.diff(t)
            d = d[d > 0]
            return 1.0 / float(np.median(d)) if len(d) else 0.0

        ra_t, ra_data = self._processor.ra_buffer.get_arrays()
        ra_freqs, ra_mags = spectre(ra_t, ra_data) if len(ra_data) > 64 else (None, None)
        dec_t, dec_data = self._processor.dec_buffer.get_arrays()
        dec_freqs, dec_mags = spectre(dec_t, dec_data) if len(dec_data) > 64 else (None, None)
        freq = frequence(ra_t)

        _, sei_data = self._processor.seismic_buffer.get_arrays()
        sei_rate = self._settings.get("seismometer_frequency_hz")
        sei_freqs, sei_mags = (spectre_regulier(sei_data, sei_rate)
                               if len(sei_data) > 64 else (None, None))

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
        self._jour_signale = False
        self._maj_bouton_armement()
        self._status_panel.add_message(T("logging_armed"), Colors.STATUS_OK)
        # Already tracking when armed: start at once rather than wait for a
        # transition that has already happened -- unless it is broad daylight.
        if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
            self._demarrer_sur_suivi()
        # Armed in daylight while the mount already tracks: no status change
        # will come at sunset, so nothing started. Look again every minute.
        if self._timer_armement is None:
            self._timer_armement = QTimer(self)
            self._timer_armement.timeout.connect(self._verifier_armement)
        self._timer_armement.start(60_000)

    OPTIONS_AUTO = (("connect_on_launch", "pref_connect_launch", "tt_connect_launch"),
                    ("autostart_on_tracking", "pref_autostart", "tt_arm"),
                    ("pause_when_not_tracking", "pref_pause", "tt_pause"),
                    ("close_at_sunrise", "pref_close_sunrise", "tt_sunrise"))

    def _menu_enregistrement(self, pos):
        menu = QMenu(self)
        for cle, libelle, aide in self.OPTIONS_AUTO:
            a = QAction(T(libelle), menu)
            a.setCheckable(True)
            a.setChecked(bool(self._settings.get(cle)))
            a.setToolTip(T(aide))
            a.toggled.connect(lambda on, c=cle: self._option_auto(c, on))
            menu.addAction(a)
        menu.setToolTipsVisible(True)
        menu.addSeparator()
        menu.addAction(T("menu_preferences"), self._show_preferences)
        menu.exec(self._btn_logging.mapToGlobal(pos))

    def _option_auto(self, cle: str, active: bool):
        self._settings.set(cle, bool(active))
        self._settings.save()
        if self._logging_armed:
            # « Night only » just switched off while the mount tracks in
            # daylight: start now rather than at the next minute's check.
            if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
                self._demarrer_sur_suivi()
            self._maj_bouton_armement()

    def _verifier_armement(self):
        if not self._logging_armed or self._logging_active:
            self._timer_armement.stop()
            return
        if getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING:
            self._demarrer_sur_suivi()
        self._maj_bouton_armement()

    def _maj_bouton_armement(self):
        """Armed: the button says what it is waiting for.

        It used to read « ARMED — waiting for tracking » while the status
        line said the mount was tracking: what it was really waiting for was
        the night (no session is opened in daylight, see _fait_jour).
        """
        if not self._logging_armed or self._logging_active:
            self._btn_logging.setToolTip(T("tt_start_logging"))
            return
        suit = getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING
        if suit and self._fait_jour():
            self._btn_logging.setText(T("btn_armed_night"))
        else:
            self._btn_logging.setText(T("btn_armed_log"))
        self._btn_logging.setToolTip(T("tt_armed"))

    def _fait_jour(self) -> bool:
        """Le Soleil est-il leve ? False si on ne peut pas savoir.

        Sert de garde-fou a l'armement : au lever, la monture suit souvent
        encore, si bien qu'un rearmement redemarrait une session dans la
        seconde — le programme cloturait la nuit puis rouvrait aussitot un
        fichier en plein jour, en boucle.
        """
        if not self._settings.get("close_at_sunrise"):
            return False
        site = self._site()
        if not site:
            return False
        from ..core.ephemerides import hauteur_soleil, HORIZON
        from datetime import datetime, timezone
        try:
            return hauteur_soleil(datetime.now(timezone.utc), site[0], site[1]) > HORIZON
        except Exception:
            return False

    def _desarmer(self):
        self._logging_armed = False
        self._btn_logging.setText(T("btn_start_log"))
        self._btn_logging.setToolTip(T("tt_start_logging"))
        self._status_panel.add_message(T("logging_disarmed"))

    def _demarrer_sur_suivi(self):
        """The mount started tracking while armed."""
        if not self._logging_armed or self._logging_active:
            return
        if self._fait_jour():
            # On reste arme : la nuit viendra. Dit une fois, et le bouton
            # l'affiche, sans quoi « en attente du suivi » contredisait
            # l'etat « la monture suit ».
            self._maj_bouton_armement()
            if not getattr(self, '_jour_signale', False):
                self._jour_signale = True
                self._status_panel.add_message(T("logging_armed_day"))
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

            # Et on montre le rapport. L'analyse automatique ne se declenchait
            # que sur une TRANSITION vers PARKED : une monture parquee depuis
            # une demi-heure quand le Soleil se leve n'en produit aucune, si
            # bien que la nuit se cloturait, le rapport s'ecrivait, et rien ne
            # s'affichait. C'est pourtant le seul moment ou l'on veut le voir.
            self._auto_analyze_on_park()

            # Et on se remet en attente pour le soir. Sans cela le programme
            # restait connecte mais inerte jusqu'a un clic : il fallait etre
            # la chaque soir. Arme, il enchaine les nuits tout seul.
            if (self._connected
                    and self._settings.get("autostart_on_tracking")):
                self._armer()

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
        self._derniere_session = chemin_dat
        self._file_logger.close()
        self._logging_active = False
        self._btn_logging.setText(T("btn_start_log"))
        self._status_panel.add_message(T("logging_stopped"))

        # The night report is written on its own, next to the .dat. Asking the
        # user to remember to export it is how a night ends up without one.
        if chemin_dat:
            self._lancer_fin_de_nuit(chemin_dat, ecrire=True)

    def _lancer_fin_de_nuit(self, chemin_dat, ecrire: bool):
        cle = str(chemin_dat)
        if cle in self._travaux_nuit:
            return
        travail = TravailFinDeNuit(cle, get_language(), ecrire, self)
        travail.fini.connect(self._fin_de_nuit_prete)
        travail.finished.connect(travail.deleteLater)
        self._travaux_nuit[cle] = travail
        travail.start()

    @pyqtSlot(str, object, object)
    def _fin_de_nuit_prete(self, chemin: str, session, sortie):
        self._travaux_nuit.pop(chemin, None)
        if sortie:
            self._status_panel.add_message(
                f"{T('report_saved')} : {Path(sortie).stem[:-3]}*.txt "
                f"({', '.join(LANGUES)})", Colors.STATUS_OK
            )
        if session is None:
            return
        if chemin in self._analyse_demandee:
            self._analyse_demandee.discard(chemin)
            self._montrer_analyse(session)
        else:
            # Kept for the park that usually follows the dawn close.
            self._session_lue = (chemin, session)

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
        # Parsed in the background: a long night took seconds (a minute on
        # a small PC) with the window frozen, live polling included.
        travail = TravailFinDeNuit(file_path, get_language(), False, self)
        travail.fini.connect(self._relecture_prete)
        travail.finished.connect(travail.deleteLater)
        self._travail_relecture = travail
        travail.start()

    @pyqtSlot(str, object, object)
    def _relecture_prete(self, file_path: str, session, _sortie):
        self._travail_relecture = None
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
            # Compute speeds from axis positions
            # Degrees -> arcsec/s. Samples with the same time stamp (ASCOM
            # times to the second in older files) are dropped: dividing by
            # 1e-6 drew huge spikes.
            t = session.timestamps[:len(session.ra_axis)]
            dt = np.diff(t)
            bon = dt > 0

            def vitesse(pos):
                d = (np.diff(pos) + 180.0) % 360.0 - 180.0
                return (d[bon] * 3600.0) / dt[bon]
            ra_speed = vitesse(session.ra_axis)
            dec_speed = (vitesse(session.dec_axis)
                         if len(session.dec_axis) == len(session.ra_axis) else None)
            t = np.concatenate((t[:1], t[1:][bon]))

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

        from ..core.spectre import spectre, spectre_regulier

        def calcul(dev):
            t = getattr(session, "deviation_timestamps", None)
            if t is not None and len(t) == len(dev):
                return spectre(t, dev)
            return spectre_regulier(dev, freq, enlever_sauts=True)

        if len(session.ra_deviations) > 64:
            ra_freqs, ra_mags = calcul(np.asarray(session.ra_deviations))
        if len(session.dec_deviations) > 64:
            dec_freqs, dec_mags = calcul(np.asarray(session.dec_deviations))

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
        """Montre le rapport de la nuit qui vient de se terminer.

        Appelee a la cloture du matin et sur un park. Une meme session n'est
        montree qu'une fois : sans cela, une monture qui se parque apres le
        lever ouvrait une seconde fenetre sur le meme rapport.
        """
        try:
            dat_path = self._derniere_session
            if dat_path is None or not Path(dat_path).exists():
                return
            if str(dat_path) == getattr(self, '_session_analysee', None):
                return
            self._session_analysee = str(dat_path)
            # Une session d'une poignee d'octets n'a rien a dire.
            if Path(dat_path).stat().st_size < 1024:
                return

            self._status_panel.add_message(
                T("parked_auto_analysis"), Colors.STATUS_OK,
            )
            cle = str(dat_path)
            lue = self._session_lue
            if lue is not None and lue[0] == cle:
                self._session_lue = None
                self._montrer_analyse(lue[1])
                return
            # Read in the background; the window opens when it is ready.
            self._analyse_demandee.add(cle)
            self._lancer_fin_de_nuit(cle, ecrire=False)
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    def _montrer_analyse(self, session):
        try:
            if session.sample_count < 10:
                return
            # Non modale, et une seule a la fois. exec() bloquait la boucle
            # d'evenements : au premier matin sans personne devant l'ecran,
            # le programme se figeait. La precedente est DETRUITE, pas
            # seulement cachee : close() la gardait en memoire avec toute sa
            # session (+100 Mo par nuit, jusqu'au swap sur un PC de 4 Go).
            precedente = getattr(self, '_fen_analyse', None)
            if precedente is not None:
                try:
                    precedente.close()
                    precedente.deleteLater()
                except RuntimeError:
                    pass          # deja detruite par Qt
            dialog = AnalysisDialog(session, self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            self._fen_analyse = dialog
            self._status_panel.add_message(T("analysis_complete"), Colors.STATUS_OK)
        except Exception as e:
            logger.error(f"Auto-analysis failed: {e}")

    # ── Zoom and reset ───────────────────────────────────────────

    def _config_sismometre(self):
        g = self._settings.get
        return (g("seismometer_port"), float(g("seismometer_frequency_hz") or 20),
                int(g("seismometer_offset") or 0), int(g("seismometer_range") or 2000),
                int(g("seismometer_baud") or 9600))

    def _appliquer_sismometre(self):
        """Start, restart or stop the seismometer to match the preferences,
        at once, and show or hide its graph.

        It used to start only at connection and its graph to be added only
        when the window was built: ticking « Enable » showed nothing until a
        restart, and a port that would not open (often because JamaSeis held
        it) was reported in the log file alone.
        """
        if self._sim_mode in ("seismometer", "all"):
            return
        voulu = bool(self._settings.get("seismometer_enabled"))
        cfg = self._config_sismometre()
        actuel = getattr(self, '_config_sei_actuelle', None)
        if self._seismometer is not None and (not voulu or cfg != actuel):
            try:
                self._seismometer.stop()
            except Exception as e:
                logger.warning(f"Seismometer stop: {e}")
            self._seismometer = None
            self._config_sei_actuelle = None
        if voulu and self._graph_splitter.indexOf(self._seismic_graph) < 0:
            self._graph_splitter.addWidget(self._seismic_graph)
        self._seismic_graph.setVisible(voulu)
        self._deplier_graphes()
        if not voulu or self._seismometer is not None:
            return
        port, freq, offset, plage, baud = cfg
        if not port:
            self._status_panel.add_message(T("sei_pas_de_port"), Colors.STATUS_WARNING)
            return
        sei = Seismometer(port=port, frequency_hz=freq, offset=offset,
                          data_range=plage, baudrate=baud)
        sei.set_callback(self.sismique_recue.emit)
        if not sei.start():
            self._status_panel.add_message(
                T("sei_echec").format(port=port, e=sei.erreur), Colors.STATUS_ERROR)
            return
        self._seismometer = sei
        self._config_sei_actuelle = cfg
        self._status_panel.add_message(
            T("sei_demarre").format(port=port, baud=baud), Colors.STATUS_OK)
        n0 = self._dernier_sismique()
        QTimer.singleShot(15_000, lambda s=sei, n=n0: self._verifier_sismometre(s, n))

    def _dernier_sismique(self) -> float:
        try:
            t, _ = self._processor.seismic_buffer.get_last_n(1)
            return float(t[-1]) if len(t) else 0.0
        except Exception:
            return 0.0

    def _verifier_sismometre(self, sei, n0):
        if sei is not self._seismometer or not self._processor:
            return
        if self._dernier_sismique() <= n0:
            self._status_panel.add_message(
                T("sei_muet").format(port=self._settings.get("seismometer_port")),
                Colors.STATUS_WARNING)

    def _tolerance_ra_affichee(self) -> float:
        """RA tolerance in the displayed unit: the setting is in arcseconds
        of RA; in hours mode it is shown, and compared, in seconds of time."""
        tol = float(self._settings.get("tolerance_ra_arcsec") or 0.0)
        return tol if self._settings.get("ra_in_degrees") else tol / 15.0

    def _largeur(self) -> float:
        """Seconds shown by the scrolling graphs (View > Time span)."""
        return largeur_affichee(self._settings.get("time_span_s"))

    def _derive_horloge(self):
        """Clock drift in ms/h, fitted on the last half hour, recomputed
        at most every 5 s (it is a slope, it does not move faster)."""
        maintenant = time.monotonic()
        cache = getattr(self, '_derive_cache', None)
        if cache is not None and maintenant - cache[0] < 5.0:
            return cache[1]
        try:
            t, v, _, _ = self._processor.time_diff_buffer.get_tail(1800.0)
            d = derive_horloge(t, v)
        except Exception as e:
            logger.debug(f"Clock drift: {e}")
            d = None
        self._derive_cache = (maintenant, d)
        return d

    def _set_largeur(self, secondes: float):
        self._settings.set("time_span_s", float(secondes))
        self._settings.save()
        self._refresh_graphs_now()

    def _remplir_menu_largeur(self, menu):
        groupe = QActionGroup(menu)
        actuelle = self._largeur()
        for s in LARGEURS_S:
            a = QAction(nom_largeur(s), menu)
            a.setCheckable(True)
            a.setChecked(abs(s - actuelle) < 0.5)
            a.triggered.connect(lambda checked, s=s: self._set_largeur(s))
            groupe.addAction(a)
            menu.addAction(a)
        # Rebuilt on opening, so the tick follows a change made elsewhere.
        menu.aboutToShow.connect(lambda m=menu: [
            a.setChecked(abs(s - self._largeur()) < 0.5)
            for a, s in zip(m.actions(), LARGEURS_S)])

    def _remplir_menu_vertical(self, menu):
        groupe = QActionGroup(menu)
        modes = [("data", T("zoom_data")), ("tolerance", T("zoom_tolerance")),
                 ("maximum", T("zoom_maximum")), ("minmax", T("zoom_minmax"))]
        for mode, label in modes:
            a = QAction(label, menu)
            a.setCheckable(True)
            a.triggered.connect(lambda checked, m=mode: self._set_vertical_zoom(m))
            groupe.addAction(a)
            menu.addAction(a)
        menu.aboutToShow.connect(lambda m=menu: [
            a.setChecked(mode == (self._settings.get("vertical_zoom_mode") or "data"))
            for a, (mode, _) in zip(m.actions(), modes)])

    def _brancher_menus_graphes(self):
        """Right click on a graph: our menu, not pyqtgraph's.

        pyqtgraph's own menu offered « X axis / Y axis » ranges that the
        next refresh, a quarter of a second later, overwrote: the span
        looked settable and never stayed.
        """
        for graphe in (self._ra_graph, self._dec_graph, self._time_graph,
                       self._seismic_graph, self._axial_graph):
            plot = graphe._plot
            plot.setMenuEnabled(False)
            plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            plot.customContextMenuRequested.connect(
                lambda pos, g=graphe: self._menu_graphe(g, pos))

    def _menu_graphe(self, graphe, pos):
        menu = QMenu(self)
        self._remplir_menu_largeur(menu.addMenu(T("time_span")))
        if graphe in (self._ra_graph, self._dec_graph):
            self._remplir_menu_vertical(menu.addMenu(T("vertical_zoom")))
        menu.exec(graphe._plot.mapToGlobal(pos))

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

    def _set_vertical_zoom(self, mode: str, enregistrer: bool = True):
        self._ra_graph.set_vertical_zoom(mode)
        self._dec_graph.set_vertical_zoom(mode)
        if enregistrer:
            self._settings.set("vertical_zoom_mode", mode)
            self._settings.save()
            self._refresh_graphs_now()

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

        self._status_panel.set_ra_en_degres(self._settings.get("ra_in_degrees"))
        self._appliquer_sismometre()
        self._refresh_graphs_now()

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

        Le critere : la fenetre affichee s'est entierement renouvelee depuis
        le dernier export, c'est-a-dire que le dernier echantillon a avance
        d'une largeur de fenetre. Chaque image montre ainsi un morceau de
        nuit different, sans trou ni recouvrement.

        🔴 Il comptait auparavant les echantillons du tampon. Or celui-ci est
        circulaire et plafonne a 50 000 : une fois plein, sa taille ne bouge
        plus, et le carnet s'arretait en pleine nuit sans rien dire.
        """
        if self._settings.get("dump_mode") != "full":
            return
        try:
            t, _ = self._processor.ra_buffer.get_arrays()
        except Exception:
            return
        if len(t) == 0:
            return
        fin = float(t[-1])
        largeur = self._largeur()
        depart = getattr(self, '_instant_dernier_dump', None)
        if depart is None or fin < depart:
            self._instant_dernier_dump = fin
            return
        if fin - depart >= largeur:
            self._instant_dernier_dump = fin
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
        suit = getattr(self, '_prev_mount_status', None) == MountStatus.TRACKING

        def lire(c):
            r = {}
            if cfg["check_refraction_status"]:
                r["refraction"] = c.is_refraction_enabled()
            if cfg["check_refraction_enabled"]:
                r["mode"] = c.get_refraction_mode()
            if suit and cfg["check_tracking_rate"]:
                r["rate"] = c.get_tracking_rate()
            if cfg["check_gps_sync"]:
                r["gps"] = c.is_gps_synced()
            if cfg["check_dual_tracking"]:
                r["dual"] = c.is_dual_tracking_enabled()
            return r

        self._demande_monture(lire, lambda r: self._juger_controles(r or {}, suit))

    def _juger_controles(self, r: dict, suit: bool):
        warnings = []
        ok_checks = []

        # Refraction correction on/off (:GREF#)
        if self._settings.get("check_refraction_status") and r.get("refraction") is not None:
            expected_val = self._settings.get("check_refraction_status_value") or "enabled"
            actual = "enabled" if r["refraction"] else "disabled"
            if actual == expected_val:
                ok_checks.append(T("chk_refr_status_ok").format(v=T(f"val_{actual}")) + " \u2713")
            else:
                warnings.append(T("chk_refr_status_ko").format(
                    a=T(f"val_{actual}"), e=T(f"val_{expected_val}")))

        # Refraction update mode (:WSG#: not_updating, not_updating_tracking,
        # continuously_updating). Pointless when the correction is off.
        if self._settings.get("check_refraction_enabled") and r.get("refraction") is not False:
            expected = self._settings.get("check_refraction_value")
            mode = r.get("mode")
            if mode is not None:
                mode_display = mode.replace('_', ' ')
                if mode == expected:
                    ok_checks.append(T("chk_refraction_ok").format(v=mode_display) + " \u2713")
                else:
                    expected_display = expected.replace('_', ' ')
                    warnings.append(
                        T("chk_refraction_ko").format(a=mode_display, e=expected_display)
                    )

        # Check GPS sync
        if self._settings.get("check_gps_sync") and r.get("gps") is not None:
            expected_val = self._settings.get("check_gps_sync_value")
            actual = "synchronising" if r["gps"] else "not synchronising"
            if actual == expected_val:
                ok_checks.append(T("chk_gps_ok").format(v=actual) + " \u2713")
            else:
                warnings.append(T("chk_gps_ko").format(a=actual, e=expected_val))

        # Check dual tracking
        if self._settings.get("check_dual_tracking") and r.get("dual") is not None:
            expected_val = self._settings.get("check_dual_tracking_value")
            actual = "enabled" if r["dual"] else "disabled"
            if actual == expected_val:
                ok_checks.append(T("chk_dual_ok").format(v=actual) + " \u2713")
            else:
                warnings.append(T("chk_dual_ko").format(a=actual, e=expected_val))

        # Check tracking rate
        if not suit:
            ok_checks.append(T("chk_parked"))
        if suit and self._settings.get("check_tracking_rate"):
            expected_val = self._settings.get("check_tracking_rate_value")
            rate = r.get("rate")
            if rate is not None:
                rate_lower = str(rate).lower().strip()
                if expected_val.lower() in rate_lower or rate_lower.startswith("60"):
                    ok_checks.append(T("chk_rate_ok").format(v=rate) + " \u2713")
                else:
                    warnings.append(T("chk_rate_ko").format(a=rate, e=expected_val))

        # Display results
        for msg in ok_checks:
            self._status_panel.add_message(msg, Colors.STATUS_OK)
            if self._logging_active:
                self._file_logger.log_event(f"Check OK: {msg}")

        if warnings:
            for msg in warnings:
                self._status_panel.add_message(f"\u26a0 {msg}", Colors.STATUS_WARNING)
                if self._logging_active:
                    self._file_logger.log_event(f"Check WARNING: {msg}")
            self._alerte_monture(warnings)

    def _alerte_monture(self, warnings: list):
        """ONE non-modal box, updated in place.

        A modal box per end of slew piled up all night in front of an empty
        chair, each one a nested event loop."""
        texte = T("mount_alert_text") + "\n\n" + "\n".join(f"\u26a0 {w}" for w in warnings)
        boite = getattr(self, "_boite_alerte", None)
        if boite is None:
            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Warning)
            boite.setWindowTitle(T("mount_alert_title"))
            boite.setStandardButtons(QMessageBox.StandardButton.Ok)
            boite.setModal(False)
            self._boite_alerte = boite
        boite.setText(texte)
        boite.show()
        boite.raise_()

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

        # The download runs in a thread: done on the GUI thread with
        # processEvents, it froze the window on a slow line and let events
        # re-enter half-way through the replacement of the files.
        dlg = QProgressDialog(T("update_downloading"), None, 0, 100, self)
        dlg.setWindowTitle(T("update_available"))
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._dlg_maj = dlg

        def progression(fait, total):
            if total:
                self.maj_progression.emit(int(fait * 100 / total))

        def telecharger():
            try:
                self.maj_posee.emit(bool(updater.download_and_apply(info, progress=progression)), "")
            except Exception as e:
                self.maj_posee.emit(False, str(e) or e.__class__.__name__)

        threading.Thread(target=telecharger, daemon=True, name="maj-telechargement").start()

    @pyqtSlot(int)
    def _maj_progression(self, pct: int):
        dlg = getattr(self, "_dlg_maj", None)
        if dlg is not None:
            dlg.setValue(pct)

    @pyqtSlot(bool, str)
    def _maj_terminee(self, pose: bool, erreur: str):
        dlg, self._dlg_maj = getattr(self, "_dlg_maj", None), None
        if dlg is not None:
            dlg.close()
        if erreur:
            QMessageBox.warning(
                self, T("update_available"),
                T("tt_upd_failed").format(err=erreur))
            return
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
                T("erreur_prefixe") + str(e))

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
        self._deplier_graphes()

    def _deplier_graphes(self):
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
        tailles = sp.sizes()
        montres = [i for i in range(sp.count()) if not sp.widget(i).isHidden()]
        if not montres or all(tailles[i] >= 60 for i in montres):
            return
        total = sum(tailles[i] for i in montres) or 400 * len(montres)
        part = total // len(montres)
        sp.setSizes([part if i in montres else 0 for i in range(sp.count())])

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
        if self._connexion_en_cours and self._poller is not None:
            poller, self._poller = self._poller, None
            self._liberer_poller(poller)

        # The night report is written in a background thread: let it finish
        # (the files are on disk already, this is only the report), and never
        # let a running QThread be destroyed -- that aborts the process.
        for travail in list(self._travaux_nuit.values()) + [getattr(self, "_travail_relecture", None)]:
            if travail is not None:
                try:
                    travail.wait(120_000)
                except RuntimeError:
                    pass
        for poller in list(self._pollers_finissants):
            poller.wait(5000)

        if self._fft_window:
            self._fft_window.close()

        event.accept()
