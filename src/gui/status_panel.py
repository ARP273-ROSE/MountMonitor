"""Status panel widget for MountMonitor.

Displays scrolling log messages, current values, connection state,
and tolerance alerts. Equivalent to the text boxes in the original Java version.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor

from .theme import Colors
from ..utils.i18n import T
from ..utils.coordinates import format_ra, format_dec
from ..models.mount_data import MountSample, MountStatus


class StatusPanel(QWidget):
    """Status panel showing current values and scrolling messages."""

    def __init__(self, max_lines: int = 50, parent=None):
        super().__init__(parent)
        self._max_lines = max_lines
        self._tolerance_ra_arcsec = 1.5
        self._tolerance_dec_arcsec = 1.5
        self._tolerance_as_ha_seconds = False
        self._declination_deg = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Current values grid
        values_frame = QFrame()
        values_frame.setStyleSheet(
            f"QFrame {{ background-color: {Colors.BG_MEDIUM.name()}; "
            f"border: 1px solid {Colors.BORDER.name()}; border-radius: 4px; }}"
        )
        values_layout = QGridLayout(values_frame)
        values_layout.setContentsMargins(8, 6, 8, 6)
        values_layout.setSpacing(4)

        mono_font = QFont("Consolas", 10)

        # Connection status
        self._status_indicator = QLabel("●")
        self._status_indicator.setFont(QFont("Arial", 14))
        self._status_indicator.setStyleSheet(f"color: {Colors.STATUS_INACTIVE.name()};")
        values_layout.addWidget(self._status_indicator, 0, 0)

        self._status_label = QLabel(T("disconnected"))
        self._status_label.setFont(mono_font)
        values_layout.addWidget(self._status_label, 0, 1, 1, 3)

        # RA values
        ra_label = QLabel(T("label_ra"))
        ra_label.setFont(mono_font)
        ra_label.setStyleSheet(f"color: {Colors.GRAPH_RA.name()};")
        ra_label.setToolTip("EN: Right Ascension\nFR: Ascension Droite")
        values_layout.addWidget(ra_label, 1, 0)

        self._ra_value = QLabel("--:--:--.--")
        self._ra_value.setFont(mono_font)
        values_layout.addWidget(self._ra_value, 1, 1)

        self._ra_dev = QLabel("Δ --.--\"")
        self._ra_dev.setFont(mono_font)
        values_layout.addWidget(self._ra_dev, 1, 2)

        self._ra_stdev = QLabel("σ --.--\"")
        self._ra_stdev.setFont(mono_font)
        self._ra_stdev.setStyleSheet(f"color: {Colors.GRAPH_STDEV.name()};")
        values_layout.addWidget(self._ra_stdev, 1, 3)

        # DEC values
        dec_label = QLabel(T("label_dec"))
        dec_label.setFont(mono_font)
        dec_label.setStyleSheet(f"color: {Colors.GRAPH_DEC.name()};")
        dec_label.setToolTip("EN: Declination\nFR: Déclinaison")
        values_layout.addWidget(dec_label, 2, 0)

        self._dec_value = QLabel("+--:--:--.--")
        self._dec_value.setFont(mono_font)
        values_layout.addWidget(self._dec_value, 2, 1)

        self._dec_dev = QLabel("Δ --.--\"")
        self._dec_dev.setFont(mono_font)
        values_layout.addWidget(self._dec_dev, 2, 2)

        self._dec_stdev = QLabel("σ --.--\"")
        self._dec_stdev.setFont(mono_font)
        self._dec_stdev.setStyleSheet(f"color: {Colors.GRAPH_STDEV.name()};")
        values_layout.addWidget(self._dec_stdev, 2, 3)

        # Frequency and sample count
        self._freq_label = QLabel(f"0.0 Hz | 0 {T('samples')}")
        self._freq_label.setFont(QFont("Consolas", 9))
        self._freq_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        self._freq_label.setToolTip("EN: Polling frequency and sample count\nFR: Fréquence d'acquisition et nombre d'échantillons")
        values_layout.addWidget(self._freq_label, 3, 0, 1, 4)

        layout.addWidget(values_frame)

        # Scrolling message log
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont("Consolas", 9))
        self._log_text.setMaximumHeight(200)
        self._log_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        layout.addWidget(self._log_text)

    def set_tolerances(self, ra_arcsec: float, dec_arcsec: float,
                       as_ha_seconds: bool = False, declination_deg: float = 0.0):
        """Configure tolerance thresholds and display mode."""
        self._tolerance_ra_arcsec = ra_arcsec
        self._tolerance_dec_arcsec = dec_arcsec
        self._tolerance_as_ha_seconds = as_ha_seconds
        self._declination_deg = declination_deg

    def update_mount_sample(self, sample: MountSample):
        """Update display with new mount data."""
        self._ra_value.setText(sample.ra_raw_str or format_ra(sample.ra_hours))
        self._dec_value.setText(sample.dec_raw_str or format_dec(sample.dec_degrees))
        self._declination_deg = sample.dec_degrees

        # RA deviation display
        ra_dev = sample.ra_deviation_arcsec
        if self._tolerance_as_ha_seconds:
            import math
            cos_dec = math.cos(math.radians(abs(self._declination_deg)))
            if cos_dec > 0.001:
                ra_time_s = ra_dev / 15.0 / cos_dec
                self._ra_dev.setText(f"\u0394 {ra_time_s:+.3f}s")
            else:
                self._ra_dev.setText(f"\u0394 {ra_dev:+.2f}\"")
        else:
            self._ra_dev.setText(f"\u0394 {ra_dev:+.2f}\"")
        self._dec_dev.setText(f"\u0394 {sample.dec_deviation_arcsec:+.2f}\"")

        # Color deviation text based on tolerance
        ra_color = Colors.ACCENT_RED.name() if abs(ra_dev) > self._tolerance_ra_arcsec else Colors.TEXT_PRIMARY.name()
        dec_color = Colors.ACCENT_RED.name() if abs(sample.dec_deviation_arcsec) > self._tolerance_dec_arcsec else Colors.TEXT_PRIMARY.name()
        self._ra_dev.setStyleSheet(f"color: {ra_color};")
        self._dec_dev.setStyleSheet(f"color: {dec_color};")

    def update_status(self, status: MountStatus):
        """Update connection/tracking status."""
        status_map = {
            MountStatus.TRACKING: (Colors.STATUS_OK, T("mount_tracking")),
            MountStatus.SLEWING: (Colors.STATUS_WARNING, T("mount_slewing")),
            MountStatus.PARKED: (Colors.STATUS_INACTIVE, T("mount_parked")),
            MountStatus.IDLE: (Colors.STATUS_INACTIVE, T("mount_idle")),
            MountStatus.ERROR: (Colors.STATUS_ERROR, T("error_status")),
            MountStatus.UNKNOWN: (Colors.STATUS_INACTIVE, T("disconnected")),
        }
        color, text = status_map.get(status, (Colors.STATUS_INACTIVE, "?"))
        self._status_indicator.setStyleSheet(f"color: {color.name()};")
        self._status_label.setText(text)

    def update_frequency(self, freq_hz: float, sample_count: int):
        """Update frequency and sample count display."""
        self._freq_label.setText(f"{freq_hz:.1f} Hz | {sample_count} {T('samples')}")

    def update_stdev(self, ra_stdev: float, dec_stdev: float):
        """Update STDEV display values."""
        self._ra_stdev.setText(f"σ {ra_stdev:.2f}\"")
        self._dec_stdev.setText(f"σ {dec_stdev:.2f}\"")

    def add_message(self, message: str, color: QColor = None):
        """Add a message to the scrolling log (newest on top)."""
        if color is None:
            color = Colors.TEXT_SECONDARY
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        html = f'<span style="color:{color.name()}">{ts} {message}</span>'

        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.insertHtml(html + "<br>")

        # Limit lines
        doc = self._log_text.document()
        if doc.blockCount() > self._max_lines:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

    def set_connected(self, connected: bool):
        """Update connection state display."""
        if connected:
            self._status_indicator.setStyleSheet(f"color: {Colors.STATUS_OK.name()};")
            self._status_label.setText(T("connected"))
        else:
            self._status_indicator.setStyleSheet(f"color: {Colors.STATUS_INACTIVE.name()};")
            self._status_label.setText(T("disconnected"))

    def clear(self):
        """Clear all displayed data."""
        self._ra_value.setText("--:--:--.--")
        self._dec_value.setText("+--:--:--.--")
        self._ra_dev.setText("Δ --.--\"")
        self._dec_dev.setText("Δ --.--\"")
        self._ra_stdev.setText("σ --.--\"")
        self._dec_stdev.setText("σ --.--\"")
        self._freq_label.setText(f"0.0 Hz | 0 {T('samples')}")
        self._log_text.clear()
