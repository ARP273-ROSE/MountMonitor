"""Preferences dialog for MountMonitor.

Four tabs matching the original: General, Processing, Auxiliary, Miscellaneous.
All settings are bilingual (FR/EN).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QPushButton, QGroupBox, QLabel, QGridLayout,
    QDialogButtonBox, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..config.settings import Settings
from ..utils.i18n import T, langues_disponibles
from ..core.seismometer import Seismometer

import logging
import sys

logger = logging.getLogger(__name__)


def _ascom_choose(current_driver: str = "") -> str:
    """Open the ASCOM Chooser dialog and return the selected driver ProgID.

    Returns empty string if user cancels or ASCOM is not available.
    """
    if sys.platform != "win32":
        return ""
    try:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        chooser = comtypes.client.CreateObject("ASCOM.Utilities.Chooser")
        chooser.DeviceType = "Telescope"
        result = chooser.Choose(current_driver)
        return str(result) if result else ""
    except Exception as e:
        logger.warning(f"ASCOM Chooser failed: {e}")
        return ""


class PreferencesDialog(QDialog):
    """Preferences dialog with 4 tabs."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle(T("menu_preferences"))
        self.setMinimumSize(600, 550)
        self.resize(680, 620)

        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()
        tabs.addTab(self._scrollable(self._create_general_tab()), T("pref_general"))
        tabs.addTab(self._scrollable(self._create_processing_tab()), T("pref_processing"))
        tabs.addTab(self._scrollable(self._create_auxiliary_tab()), T("pref_auxiliary"))
        tabs.addTab(self._scrollable(self._create_misc_tab()), T("pref_misc"))
        layout.addWidget(tabs)

        # OK / Cancel buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _scrollable(widget: QWidget) -> QScrollArea:
        """Wrap a tab widget in a scroll area to prevent overlap."""
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        return scroll

    def _create_general_tab(self) -> QWidget:
        """General tab: observatory, mount connection, layout."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Observatory group
        obs_group = QGroupBox(T("pref_observatory"))
        obs_form = QFormLayout(obs_group)

        self._observatory_name = QLineEdit(self._settings.get("observatory_name"))
        self._observatory_name.setToolTip(T("tt_obs_name"))
        obs_form.addRow(T("pref_observatory"), self._observatory_name)

        self._mount_name = QLineEdit(self._settings.get("mount_name"))
        self._mount_name.setToolTip(T("tt_mount_name"))
        obs_form.addRow(T("pref_mount_name"), self._mount_name)
        layout.addWidget(obs_group)

        # Connection group
        conn_group = QGroupBox(T("pref_connection"))
        conn_form = QFormLayout(conn_group)

        self._protocol = QComboBox()
        self._protocol.addItems(["LX200 (TCP/IP)", "LX200 (Serial)", "ASCOM", "Simulation"])
        protocol_map = {"lx200": 0, "lx200_serial": 1, "ascom": 2, "simulation": 3}
        self._protocol.setCurrentIndex(protocol_map.get(self._settings.get("mount_protocol"), 0))
        self._protocol.setToolTip(T("tt_protocol"))
        self._protocol.currentIndexChanged.connect(self._on_protocol_changed)
        conn_form.addRow(T("pref_protocol"), self._protocol)

        self._mount_ip = QLineEdit(self._settings.get("mount_ip"))
        self._mount_ip.setToolTip(T("tt_mount_ip"))
        conn_form.addRow(T("pref_mount_ip"), self._mount_ip)

        self._mount_port = QSpinBox()
        self._mount_port.setRange(1, 65535)
        self._mount_port.setValue(self._settings.get("mount_port"))
        self._mount_port.setToolTip(T("tt_mount_port"))
        conn_form.addRow(T("pref_mount_port"), self._mount_port)

        # Serial port selector (auto-detected)
        self._serial_port = QComboBox()
        self._serial_port.setEditable(True)
        self._refresh_serial_ports()
        current_serial = self._settings.get("serial_port")
        if current_serial:
            self._serial_port.setCurrentText(current_serial)
        self._serial_port.setToolTip(T("tt_serial_port"))
        conn_form.addRow(T("pref_serial_port"), self._serial_port)

        # Vitesse de la liaison série. Elle était figée à 9600 bauds ; une
        # monture réglée autrement ne répondait alors rien du tout, sans que
        # rien n'indique pourquoi.
        self._serial_baudrate = QComboBox()
        for vitesse in (9600, 19200, 38400, 57600, 115200):
            self._serial_baudrate.addItem(str(vitesse), vitesse)
        actuelle = self._settings.get("serial_baudrate")
        index = self._serial_baudrate.findData(actuelle)
        self._serial_baudrate.setCurrentIndex(index if index >= 0 else 0)
        self._serial_baudrate.setToolTip(T("tt_serial_baud"))
        conn_form.addRow("Bauds", self._serial_baudrate)

        ascom_row = QHBoxLayout()
        self._ascom_driver = QLineEdit(self._settings.get("ascom_driver"))
        self._ascom_driver.setToolTip(T("tt_ascom_id"))
        self._ascom_driver.setReadOnly(True)
        ascom_row.addWidget(self._ascom_driver)

        self._ascom_choose_btn = QPushButton(T("pref_select_ascom"))
        self._ascom_choose_btn.setToolTip(T("tt_ascom_choose"))
        self._ascom_choose_btn.clicked.connect(self._on_ascom_choose)
        ascom_row.addWidget(self._ascom_choose_btn)
        conn_form.addRow(T("pref_ascom_driver"), ascom_row)

        layout.addWidget(conn_group)

        # Layout group
        layout_group = QGroupBox(T("pref_layout"))
        layout_form = QFormLayout(layout_group)

        self._graph_ratio = QSpinBox()
        self._graph_ratio.setRange(1, 10)
        self._graph_ratio.setValue(self._settings.get("graph_textbox_ratio"))
        self._graph_ratio.setToolTip(T("tt_ratio"))
        layout_form.addRow(T("pref_graph_ratio"), self._graph_ratio)

        # Language. The list is built from i18n so that adding a language is a
        # one-line change there, and each one is named in its own tongue —
        # someone looking for their language does not read the current one.
        self._language = QComboBox()
        self._codes_langue = ["auto"] + list(langues_disponibles().keys())
        self._language.addItem("Auto")
        for code, nom in langues_disponibles().items():
            self._language.addItem(nom)
        courant = self._settings.get("language")
        self._language.setCurrentIndex(
            self._codes_langue.index(courant) if courant in self._codes_langue else 0
        )
        self._language.setToolTip(T("tt_language"))
        layout_form.addRow(T("pref_language"), self._language)

        layout.addWidget(layout_group)
        layout.addStretch()

        self._on_protocol_changed(self._protocol.currentIndex())
        return widget

    def _create_processing_tab(self) -> QWidget:
        """Processing tab: polling, STDEV, tolerances, logging."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Polling
        poll_group = QGroupBox(T("pref_polling_group"))
        poll_form = QFormLayout(poll_group)

        self._polling_freq = QDoubleSpinBox()
        self._polling_freq.setRange(0.1, 20.0)
        self._polling_freq.setValue(self._settings.get("polling_frequency_hz"))
        self._polling_freq.setSuffix(" Hz")
        self._polling_freq.setDecimals(1)
        self._polling_freq.setToolTip(T("tt_polling"))
        poll_form.addRow(T("pref_polling"), self._polling_freq)

        self._running_range = QComboBox()
        self._running_range.addItems(["60 s", "120 s", "300 s", "900 s"])
        range_map = {60: 0, 120: 1, 300: 2, 900: 3}
        self._running_range.setCurrentIndex(range_map.get(self._settings.get("running_range_seconds"), 0))
        self._running_range.setToolTip(T("tt_run_range"))
        poll_form.addRow(T("pref_running_range"), self._running_range)

        self._correct_graphs = QCheckBox()
        self._correct_graphs.setChecked(self._settings.get("correct_graphs_for_range"))
        self._correct_graphs.setToolTip(T("tt_shift_graphs"))
        poll_form.addRow(T("pref_correct_graphs"), self._correct_graphs)

        layout.addWidget(poll_group)

        # Reference and tolerances
        tol_group = QGroupBox(T("tolerance"))
        tol_form = QFormLayout(tol_group)

        self._reference_mode = QComboBox()
        self._reference_mode.addItems([T("ref_median"), T("ref_target")])
        self._reference_mode.setCurrentIndex(0 if self._settings.get("reference_mode") == "median" else 1)
        self._reference_mode.setToolTip(T("tt_reference"))
        tol_form.addRow(T("pref_reference"), self._reference_mode)

        self._tol_ra = QDoubleSpinBox()
        self._tol_ra.setRange(0.05, 60.0)
        self._tol_ra.setValue(self._settings.get("tolerance_ra_arcsec"))
        self._tol_ra.setSuffix("\"")
        self._tol_ra.setDecimals(2)
        self._tol_ra.setToolTip(T("tt_tol_ra"))
        tol_form.addRow(T("pref_tolerance_ra"), self._tol_ra)

        self._tol_dec = QDoubleSpinBox()
        self._tol_dec.setRange(0.05, 60.0)
        self._tol_dec.setValue(self._settings.get("tolerance_dec_arcsec"))
        self._tol_dec.setSuffix("\"")
        self._tol_dec.setDecimals(2)
        self._tol_dec.setToolTip(T("tt_tol_dec"))
        tol_form.addRow(T("pref_tolerance_dec"), self._tol_dec)

        self._ra_degres = QCheckBox(T("pref_ra_degrees"))
        self._ra_degres.setChecked(bool(self._settings.get("ra_in_degrees")))
        tol_form.addRow(self._ra_degres)

        self._tol_ha = QCheckBox(T("pref_show_ra_ha"))
        self._tol_ha.setChecked(self._settings.get("tolerance_as_ha_seconds"))
        self._tol_ha.setToolTip(T("tt_tol_ha"))
        tol_form.addRow("", self._tol_ha)

        self._tol_seismic = QDoubleSpinBox()
        self._tol_seismic.setRange(0.1, 50.0)
        self._tol_seismic.setValue(self._settings.get("tolerance_seismic_percent"))
        self._tol_seismic.setSuffix(" %")
        self._tol_seismic.setSingleStep(0.5)
        self._tol_seismic.setDecimals(1)
        self._tol_seismic.setToolTip(T("tt_tol_sei"))
        tol_form.addRow(T("pref_tolerance_seismic"), self._tol_seismic)

        layout.addWidget(tol_group)

        # Logging
        log_group = QGroupBox(T("pref_log_mode"))
        log_form = QFormLayout(log_group)

        self._log_mode = QComboBox()
        self._log_mode.addItems([T("log_all"), T("log_tracking_only")])
        self._log_mode.setCurrentIndex(0 if self._settings.get("log_mode") == "all" else 1)
        self._log_mode.setToolTip(T("tt_log_mode"))
        log_form.addRow(T("pref_log_mode_label"), self._log_mode)

        # Observing site. Only used when the mount does not report one --
        # and it often does not: a .dat without a site is a .dat whose
        # twilights cannot be recomputed on replay.
        self._site_lat = QLineEdit(str(self._settings.get("site_latitude") or ""))
        self._site_lat.setPlaceholderText("49.3061")
        self._site_lat.setToolTip(T("tt_site_auto"))
        log_form.addRow(T("pref_site_lat"), self._site_lat)

        self._site_lon = QLineEdit(str(self._settings.get("site_longitude") or ""))
        self._site_lon.setPlaceholderText("2.7553")
        self._site_lon.setToolTip(T("tt_site_lon"))
        log_form.addRow(T("pref_site_lon"), self._site_lon)

        self._site_elev = QLineEdit(str(self._settings.get("site_elevation_m") or ""))
        self._site_elev.setPlaceholderText("57")
        log_form.addRow(T("pref_site_elev"), self._site_elev)

        # Arming. Put next to the log mode because it answers the same
        # question -- what ends up in the file -- and because a mount
        # connected at noon for a night that starts at 19:00 writes seven
        # hours of nothing.
        self._autostart = QCheckBox(T("pref_autostart"))
        self._autostart.setChecked(bool(self._settings.get("autostart_on_tracking")))
        self._autostart.setToolTip(T("tt_arm"))
        log_form.addRow(self._autostart)

        self._autostop = QCheckBox(T("pref_pause"))
        self._autostop.setChecked(bool(self._settings.get("pause_when_not_tracking")))
        self._autostop.setToolTip(T("tt_pause"))
        log_form.addRow(self._autostop)

        self._park_delay = QSpinBox()
        self._park_delay.setRange(0, 3600)
        self._park_delay.setValue(int(self._settings.get("pause_delay_s") or 120))
        self._park_delay.setSuffix(" s")
        self._park_delay.setToolTip(T("tt_pause_delay"))
        self._park_delay.setEnabled(self._autostop.isChecked())
        self._autostop.toggled.connect(self._park_delay.setEnabled)
        log_form.addRow("    ↳", self._park_delay)

        self._close_sunrise = QCheckBox(T("pref_close_sunrise"))
        self._close_sunrise.setChecked(bool(self._settings.get("close_at_sunrise")))
        self._close_sunrise.setToolTip(T("tt_sunrise"))
        log_form.addRow(self._close_sunrise)

        self._delay_slew = QDoubleSpinBox()
        self._delay_slew.setRange(0, 60)
        self._delay_slew.setValue(self._settings.get("delay_after_slew_seconds"))
        self._delay_slew.setSuffix(" s")
        self._delay_slew.setToolTip(T("tt_delay_slew"))
        log_form.addRow(T("pref_delay_slew"), self._delay_slew)

        self._axial_mode = QComboBox()
        self._axial_mode.addItems([T("axial_off"), T("axial_velocity"), T("axial_displacement")])
        mode_map = {"off": 0, "velocity": 1, "displacement": 2}
        self._axial_mode.setCurrentIndex(mode_map.get(self._settings.get("axial_mode"), 0))
        self._axial_mode.setToolTip(T("tt_axial"))
        log_form.addRow(T("pref_axial_mode"), self._axial_mode)

        self._reset_mode = QComboBox()
        self._reset_mode.addItems([T("mode_manual"), T("mode_slewing")])
        reset_mode_map = {"manual": 0, "slewing": 1}
        self._reset_mode.setCurrentIndex(reset_mode_map.get(self._settings.get("reset_mode"), 0))
        self._reset_mode.setToolTip(T("tt_reset_mode"))
        log_form.addRow(T("pref_reset_mode"), self._reset_mode)

        self._dump_mode = QComboBox()
        self._dump_mode.addItems([
            T("mode_manual"), T("mode_slewing"), T("mode_parking"),
            T("mode_full"),
        ])
        dump_mode_map = {"manual": 0, "slewing": 1, "parking": 2, "full": 3}
        self._dump_mode.setCurrentIndex(dump_mode_map.get(self._settings.get("dump_mode"), 0))
        self._dump_mode.setToolTip(T("tt_dump_mode"))
        log_form.addRow(T("pref_dump_graphs"), self._dump_mode)

        self._close_files_mode = QComboBox()
        self._close_files_mode.addItems([
            T("mode_manual"), T("mode_slewing"), T("mode_parking"),
        ])
        close_mode_map = {"manual": 0, "slewing": 1, "parking": 2}
        self._close_files_mode.setCurrentIndex(close_mode_map.get(self._settings.get("close_files_mode"), 0))
        self._close_files_mode.setToolTip(T("tt_close_mode"))
        log_form.addRow(T("pref_close_files"), self._close_files_mode)

        self._history_lines = QSpinBox()
        self._history_lines.setRange(10, 200)
        self._history_lines.setValue(self._settings.get("history_lines"))
        self._history_lines.setSingleStep(10)
        self._history_lines.setToolTip(T("tt_history"))
        log_form.addRow(T("pref_history_lines"), self._history_lines)

        layout.addWidget(log_group)
        layout.addStretch()
        return widget

    def _create_auxiliary_tab(self) -> QWidget:
        """Auxiliary tab: NTP server, seismometer."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # NTP
        ntp_group = QGroupBox(T("pref_ntp_group"))
        ntp_form = QFormLayout(ntp_group)

        self._ntp_enabled = QCheckBox()
        self._ntp_enabled.setChecked(self._settings.get("ntp_enabled"))
        self._ntp_enabled.setToolTip(T("tt_ntp_on"))
        ntp_form.addRow(T("pref_ntp_enabled"), self._ntp_enabled)

        self._ntp_server = QLineEdit(self._settings.get("ntp_server"))
        self._ntp_server.setToolTip(T("tt_ntp_server"))
        ntp_form.addRow(T("pref_ntp_server"), self._ntp_server)

        self._ntp_interval = QSpinBox()
        self._ntp_interval.setRange(10, 3600)
        self._ntp_interval.setValue(self._settings.get("ntp_interval_seconds"))
        self._ntp_interval.setSuffix(" s")
        self._ntp_interval.setToolTip(T("tt_ntp_interval"))
        ntp_form.addRow(T("pref_ntp_interval"), self._ntp_interval)

        layout.addWidget(ntp_group)

        # Seismometer
        sei_group = QGroupBox(T("pref_seismometer"))
        sei_form = QFormLayout(sei_group)

        self._sei_enabled = QCheckBox()
        self._sei_enabled.setChecked(self._settings.get("seismometer_enabled"))
        self._sei_enabled.setToolTip(T("tt_sei_on"))
        sei_form.addRow(T("pref_enable"), self._sei_enabled)

        self._sei_port = QComboBox()
        self._sei_port.setEditable(True)
        ports = Seismometer.list_ports()
        self._sei_port.addItems(ports)
        current_port = self._settings.get("seismometer_port")
        if current_port:
            self._sei_port.setCurrentText(current_port)
        self._sei_port.setToolTip(T("tt_sei_port"))
        sei_form.addRow(T("pref_serial_port"), self._sei_port)

        self._sei_freq = QDoubleSpinBox()
        self._sei_freq.setRange(1, 100)
        self._sei_freq.setValue(self._settings.get("seismometer_frequency_hz"))
        self._sei_freq.setSuffix(" Hz")
        self._sei_freq.setToolTip(T("tt_sei_freq"))
        sei_form.addRow(T("pref_frequency"), self._sei_freq)

        self._sei_offset = QSpinBox()
        self._sei_offset.setRange(0, 10000)
        self._sei_offset.setValue(self._settings.get("seismometer_offset"))
        self._sei_offset.setToolTip(T("tt_sei_offset"))
        sei_form.addRow(T("pref_sei_offset"), self._sei_offset)

        self._sei_range = QSpinBox()
        self._sei_range.setRange(100, 100000)
        self._sei_range.setValue(self._settings.get("seismometer_range"))
        self._sei_range.setToolTip(T("tt_sei_range"))
        sei_form.addRow(T("pref_range"), self._sei_range)

        layout.addWidget(sei_group)
        layout.addStretch()
        return widget

    def _create_misc_tab(self) -> QWidget:
        """Miscellaneous tab: mount checks with expected-value dropdowns."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        checks_group = QGroupBox(T("pref_mount_checks"))
        checks_grid = QGridLayout(checks_group)

        expected_label = QLabel(T("pref_expected_value"))
        expected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checks_grid.addWidget(expected_label, 0, 1)

        # Row 1: Refraction
        self._check_refraction = QCheckBox(T("check_refraction_label"))
        self._check_refraction.setChecked(self._settings.get("check_refraction_enabled"))
        self._check_refraction.setToolTip(T("tt_chk_refr"))
        checks_grid.addWidget(self._check_refraction, 1, 0)

        self._refraction_value = QComboBox()
        self._refraction_value.addItems([
            T("refraction_not_updating"),
            T("refraction_not_tracking"),
            T("refraction_continuous"),
        ])
        ref_val_map = {
            "not_updating": 0,
            "not_updating_tracking": 1,
            "continuously_updating": 2,
        }
        self._refraction_value.setCurrentIndex(
            ref_val_map.get(self._settings.get("check_refraction_value"), 2)
        )
        self._refraction_value.setToolTip(T("tt_chk_refr_mode"))
        checks_grid.addWidget(self._refraction_value, 1, 1)

        # Row 2: Tracking rate
        self._check_tracking = QCheckBox(T("check_tracking_label"))
        self._check_tracking.setChecked(self._settings.get("check_tracking_rate"))
        self._check_tracking.setToolTip(T("tt_chk_rate"))
        checks_grid.addWidget(self._check_tracking, 2, 0)

        self._tracking_rate_value = QComboBox()
        self._tracking_rate_value.addItems(["sidereal", "lunar", "solar", "king"])
        rate_val_map = {"sidereal": 0, "lunar": 1, "solar": 2, "king": 3}
        self._tracking_rate_value.setCurrentIndex(
            rate_val_map.get(self._settings.get("check_tracking_rate_value"), 0)
        )
        self._tracking_rate_value.setToolTip(T("tt_chk_rate_val"))
        checks_grid.addWidget(self._tracking_rate_value, 2, 1)

        # Row 3: GPS sync
        self._check_gps = QCheckBox(T("check_gps_label"))
        self._check_gps.setChecked(self._settings.get("check_gps_sync"))
        self._check_gps.setToolTip(T("tt_chk_gps"))
        checks_grid.addWidget(self._check_gps, 3, 0)

        self._gps_sync_value = QComboBox()
        self._gps_sync_value.addItems(["synchronising", "not synchronising"])
        gps_val_map = {"synchronising": 0, "not synchronising": 1}
        self._gps_sync_value.setCurrentIndex(
            gps_val_map.get(self._settings.get("check_gps_sync_value"), 0)
        )
        self._gps_sync_value.setToolTip(T("tt_chk_gps_val"))
        checks_grid.addWidget(self._gps_sync_value, 3, 1)

        # Row 4: Dual tracking
        self._check_dual = QCheckBox(T("check_dual_label"))
        self._check_dual.setChecked(self._settings.get("check_dual_tracking"))
        self._check_dual.setToolTip(T("tt_chk_dual"))
        checks_grid.addWidget(self._check_dual, 4, 0)

        self._dual_tracking_value = QComboBox()
        self._dual_tracking_value.addItems(["enabled", "disabled"])
        dual_val_map = {"enabled": 0, "disabled": 1}
        self._dual_tracking_value.setCurrentIndex(
            dual_val_map.get(self._settings.get("check_dual_tracking_value"), 0)
        )
        self._dual_tracking_value.setToolTip(T("tt_chk_dual_val"))
        checks_grid.addWidget(self._dual_tracking_value, 4, 1)

        layout.addWidget(checks_group)
        layout.addStretch()
        return widget

    def _on_protocol_changed(self, index: int):
        """Enable/disable fields based on protocol."""
        is_tcp = (index == 0)        # LX200 TCP/IP
        is_serial = (index == 1)     # LX200 Serial
        is_ascom = (index == 2)      # ASCOM
        self._mount_ip.setEnabled(is_tcp)
        self._mount_port.setEnabled(is_tcp)
        self._serial_port.setEnabled(is_serial)
        self._serial_baudrate.setEnabled(is_serial)
        self._ascom_driver.setEnabled(is_ascom)
        self._ascom_choose_btn.setEnabled(is_ascom)

    def _on_ascom_choose(self):
        """Open the ASCOM Chooser dialog."""
        current = self._ascom_driver.text()
        result = _ascom_choose(current)
        if result:
            self._ascom_driver.setText(result)

    def _refresh_serial_ports(self):
        """Populate serial port dropdown with detected ports."""
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        self._serial_port.clear()
        self._serial_port.addItems(ports)

    def _save_and_accept(self):
        """Save settings and close dialog."""
        s = self._settings

        # General
        s.set("observatory_name", self._observatory_name.text())
        s.set("mount_name", self._mount_name.text())
        protocol_map = {0: "lx200", 1: "lx200_serial", 2: "ascom", 3: "simulation"}
        s.set("mount_protocol", protocol_map.get(self._protocol.currentIndex(), "lx200"))
        s.set("mount_ip", self._mount_ip.text())
        s.set("mount_port", self._mount_port.value())
        s.set("serial_port", self._serial_port.currentText())
        s.set("serial_baudrate", self._serial_baudrate.currentData())
        s.set("ascom_driver", self._ascom_driver.text())
        s.set("graph_textbox_ratio", self._graph_ratio.value())
        i = self._language.currentIndex()
        s.set("language", self._codes_langue[i] if 0 <= i < len(self._codes_langue) else "auto")
        s.set("ra_in_degrees", self._ra_degres.isChecked())
        s.set("site_latitude", self._site_lat.text().strip())
        s.set("site_longitude", self._site_lon.text().strip())
        s.set("site_elevation_m", self._site_elev.text().strip())
        s.set("autostart_on_tracking", self._autostart.isChecked())
        s.set("pause_when_not_tracking", self._autostop.isChecked())
        s.set("pause_delay_s", self._park_delay.value())
        s.set("close_at_sunrise", self._close_sunrise.isChecked())

        # Processing
        s.set("polling_frequency_hz", self._polling_freq.value())
        range_map = {0: 60, 1: 120, 2: 300, 3: 900}
        s.set("running_range_seconds", range_map.get(self._running_range.currentIndex(), 60))
        s.set("correct_graphs_for_range", self._correct_graphs.isChecked())
        s.set("reference_mode", "median" if self._reference_mode.currentIndex() == 0 else "target")
        s.set("tolerance_ra_arcsec", self._tol_ra.value())
        s.set("tolerance_dec_arcsec", self._tol_dec.value())
        s.set("tolerance_as_ha_seconds", self._tol_ha.isChecked())
        s.set("tolerance_seismic_percent", self._tol_seismic.value())
        s.set("log_mode", "all" if self._log_mode.currentIndex() == 0 else "tracking_only")
        s.set("delay_after_slew_seconds", self._delay_slew.value())
        axial_map = {0: "off", 1: "velocity", 2: "displacement"}
        s.set("axial_mode", axial_map.get(self._axial_mode.currentIndex(), "off"))
        reset_map = {0: "manual", 1: "slewing"}
        s.set("reset_mode", reset_map.get(self._reset_mode.currentIndex(), "manual"))
        dump_map = {0: "manual", 1: "slewing", 2: "parking", 3: "full"}
        s.set("dump_mode", dump_map.get(self._dump_mode.currentIndex(), "manual"))
        close_map = {0: "manual", 1: "slewing", 2: "parking"}
        s.set("close_files_mode", close_map.get(self._close_files_mode.currentIndex(), "manual"))
        s.set("history_lines", self._history_lines.value())

        # Auxiliary
        s.set("ntp_enabled", self._ntp_enabled.isChecked())
        s.set("ntp_server", self._ntp_server.text())
        s.set("ntp_interval_seconds", self._ntp_interval.value())
        s.set("seismometer_enabled", self._sei_enabled.isChecked())
        s.set("seismometer_port", self._sei_port.currentText())
        s.set("seismometer_frequency_hz", self._sei_freq.value())
        s.set("seismometer_offset", self._sei_offset.value())
        s.set("seismometer_range", self._sei_range.value())

        # Misc
        s.set("check_refraction_enabled", self._check_refraction.isChecked())
        refraction_map = {0: "not_updating", 1: "not_updating_tracking", 2: "continuously_updating"}
        s.set("check_refraction_value", refraction_map.get(self._refraction_value.currentIndex(), "continuously_updating"))
        s.set("check_tracking_rate", self._check_tracking.isChecked())
        s.set("check_tracking_rate_value", self._tracking_rate_value.currentText())
        s.set("check_gps_sync", self._check_gps.isChecked())
        s.set("check_gps_sync_value", self._gps_sync_value.currentText())
        s.set("check_dual_tracking", self._check_dual.isChecked())
        s.set("check_dual_tracking_value", self._dual_tracking_value.currentText())

        s.save()
        self.accept()
