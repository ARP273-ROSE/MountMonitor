"""Analysis dialog for 10micron mount .log10m files.

Displays comprehensive analysis of mount log data:
- Session overview (mount info, duration, data counts)
- Mount activity timeline (Gstat states, tracking efficiency)
- Time synchronization drift plot
- Detailed event table (all state transitions)

All text is bilingual FR/EN.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTextEdit, QLabel, QPushButton, QFileDialog, QProgressBar,
    QSplitter, QGroupBox, QGridLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QApplication, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush

from ..core.log10m_parser import (
    parse_log10m, Log10mFile, GSTAT_NAMES, GSTAT_NAMES_FR,
)
from ..core.log10m_analyzer import (
    analyze_log10m_files, Log10mAnalysis, SessionAnalysis,
    GstatSegment,
)
from .theme import Colors

logger = logging.getLogger(__name__)


def _tr(en: str, fr: str) -> str:
    """Return bilingual string."""
    import locale
    lang = locale.getdefaultlocale()[0] or "en"
    return fr if lang.startswith("fr") else en


def _fmt_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}min"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hours}h{mins:02d}m"


def _fmt_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# Colors for Gstat states in timeline
GSTAT_COLORS = {
    0: QColor(80, 180, 80),      # Tracking = green
    1: QColor(200, 200, 50),     # Stopped = yellow
    2: QColor(200, 130, 50),     # Slewing to park = orange
    3: QColor(130, 200, 200),    # Unparking = cyan
    5: QColor(100, 100, 140),    # Parked = gray-blue
    6: QColor(200, 100, 200),    # Slewing = magenta
    7: QColor(200, 200, 200),    # Not tracking = light gray
    8: QColor(200, 80, 80),      # Tracking outside limits = red
    9: QColor(200, 50, 50),      # Outside limits = dark red
}


class ParseWorker(QThread):
    """Background worker for parsing .log10m files."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)  # list[Log10mFile]
    error = pyqtSignal(str)

    def __init__(self, filepaths: list[Path]):
        super().__init__()
        self._filepaths = filepaths

    def run(self):
        try:
            results = []
            total = len(self._filepaths)
            for i, fp in enumerate(self._filepaths):
                def cb(pct, _i=i, _t=total):
                    overall = int((_i * 100 + pct) / _t)
                    self.progress.emit(overall)

                parsed = parse_log10m(fp, progress_callback=cb)
                results.append(parsed)

            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class Log10mAnalysisDialog(QDialog):
    """Dialog for analyzing 10micron .log10m mount logs."""

    def __init__(self, parent=None, initial_files: list[Path] | None = None):
        super().__init__(parent)
        self.setWindowTitle(_tr(
            "10micron Mount Log Analysis",
            "Analyse des logs monture 10micron"
        ))
        self.setMinimumSize(1100, 750)
        self.resize(1300, 850)

        self._analysis: Log10mAnalysis | None = None
        self._parsed_files: list[Log10mFile] = []
        self._worker: ParseWorker | None = None

        self._setup_ui()

        if initial_files:
            self._start_parsing(initial_files)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Top bar: file selection + progress
        top = QHBoxLayout()
        self._btn_open = QPushButton(_tr("Open .log10m files...", "Ouvrir fichiers .log10m..."))
        self._btn_open.setToolTip(_tr(
            "Select one or more .log10m files from the 10micron mount logger",
            "Sélectionner un ou plusieurs fichiers .log10m du logger 10micron"
        ))
        self._btn_open.clicked.connect(self._on_open_files)
        top.addWidget(self._btn_open)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        top.addWidget(self._progress, stretch=1)

        self._lbl_status = QLabel("")
        top.addWidget(self._lbl_status)
        layout.addLayout(top)

        # Tab widget for results
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Create tabs (initially empty)
        self._tab_overview = QWidget()
        self._tab_activity = QWidget()
        self._tab_timesync = QWidget()
        self._tab_events = QWidget()

        self._tabs.addTab(self._tab_overview, _tr("Overview", "Vue d'ensemble"))
        self._tabs.addTab(self._tab_activity, _tr("Activity", "Activité"))
        self._tabs.addTab(self._tab_timesync, _tr("Time Sync", "Synchro temps"))
        self._tabs.addTab(self._tab_events, _tr("Events", "Événements"))

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._btn_close = QPushButton(_tr("Close", "Fermer"))
        self._btn_close.clicked.connect(self.close)
        bottom.addWidget(self._btn_close)
        layout.addLayout(bottom)

    def _on_open_files(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            _tr("Select mount log files", "Sélectionner les fichiers log monture"),
            "",
            _tr("10micron logs (*.log10m);;All files (*)",
                "Logs 10micron (*.log10m);;Tous les fichiers (*)")
        )
        if filepaths:
            self._start_parsing([Path(f) for f in filepaths])

    def _start_parsing(self, filepaths: list[Path]):
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._btn_open.setEnabled(False)
        self._lbl_status.setText(_tr("Parsing...", "Analyse en cours..."))

        self._worker = ParseWorker(filepaths)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_parse_done)
        self._worker.error.connect(self._on_parse_error)
        self._worker.start()

    def _on_parse_done(self, results: list[Log10mFile]):
        self._parsed_files = results
        self._progress.setValue(100)
        self._btn_open.setEnabled(True)

        # Analyze
        self._analysis = analyze_log10m_files(results)

        total_sessions = len(self._analysis.sessions)
        self._lbl_status.setText(_tr(
            f"{len(results)} file(s), {total_sessions} session(s) analyzed",
            f"{len(results)} fichier(s), {total_sessions} session(s) analysée(s)"
        ))
        self._progress.setVisible(False)

        # Populate tabs
        self._populate_overview()
        self._populate_activity()
        self._populate_timesync()
        self._populate_events()

        self._worker = None

    def _on_parse_error(self, error_msg: str):
        self._progress.setVisible(False)
        self._btn_open.setEnabled(True)
        self._lbl_status.setText(f"Error: {error_msg}")
        self._worker = None

    # ─── Overview Tab ────────────────────────────────────────────

    def _populate_overview(self):
        if self._tab_overview.layout():
            QWidget().setLayout(self._tab_overview.layout())

        layout = QVBoxLayout(self._tab_overview)
        analysis = self._analysis

        # Session selector if multiple sessions
        if len(analysis.sessions) > 1:
            sel_layout = QHBoxLayout()
            sel_layout.addWidget(QLabel(_tr("Session:", "Session :")))
            self._session_combo = QComboBox()
            for s in analysis.sessions:
                label = f"#{s.session_index} — {s.mount_model} — {_fmt_datetime(s.start_time)}"
                self._session_combo.addItem(label)
            self._session_combo.currentIndexChanged.connect(self._on_session_changed)
            sel_layout.addWidget(self._session_combo, stretch=1)
            layout.addLayout(sel_layout)

        # Overview text
        self._overview_text = QTextEdit()
        self._overview_text.setReadOnly(True)
        self._overview_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self._overview_text)

        # Show first session
        if analysis.sessions:
            self._show_session_overview(analysis.sessions[0])

    def _on_session_changed(self, index: int):
        if 0 <= index < len(self._analysis.sessions):
            self._show_session_overview(self._analysis.sessions[index])
            self._show_session_activity(self._analysis.sessions[index])
            self._show_session_timesync(self._analysis.sessions[index])
            self._show_session_events(self._analysis.sessions[index])

    def _show_session_overview(self, s: SessionAnalysis):
        html = f"""
        <style>
            body {{ color: #c8c8d2; font-family: Consolas, monospace; }}
            h2 {{ color: #5082c8; margin-bottom: 8px; }}
            h3 {{ color: #50b450; margin-top: 12px; margin-bottom: 6px; }}
            table {{ border-collapse: collapse; margin: 8px 0; }}
            td {{ padding: 3px 12px 3px 0; }}
            .label {{ color: #8c8c9b; }}
            .value {{ color: #e0e0ea; font-weight: bold; }}
            .good {{ color: #50b450; }}
            .warn {{ color: #dcb432; }}
            .bad {{ color: #c85050; }}
        </style>

        <h2>{_tr("Session Overview", "Vue d'ensemble de la session")}</h2>

        <h3>{_tr("Mount Information", "Informations monture")}</h3>
        <table>
            <tr><td class="label">{_tr("Model", "Modèle")}:</td>
                <td class="value">{s.mount_model or '—'}</td></tr>
            <tr><td class="label">{_tr("Firmware", "Firmware")}:</td>
                <td class="value">{s.mount_firmware or '—'}</td></tr>
            <tr><td class="label">{_tr("Logger version", "Version logger")}:</td>
                <td class="value">{s.logger_version or '—'}</td></tr>
            <tr><td class="label">{_tr("RA encoder steps", "Steps encodeur RA")}:</td>
                <td class="value">{s.ra_steps:,.0f}</td></tr>
            <tr><td class="label">{_tr("DEC encoder steps", "Steps encodeur DEC")}:</td>
                <td class="value">{s.dec_steps:,.0f}</td></tr>
            <tr><td class="label">{_tr("IP address", "Adresse IP")}:</td>
                <td class="value">{s.ip_address or '—'}</td></tr>
            <tr><td class="label">{_tr("MAC address", "Adresse MAC")}:</td>
                <td class="value">{s.mac_address or '—'}</td></tr>
        </table>

        <h3>{_tr("Session Timing", "Timing de la session")}</h3>
        <table>
            <tr><td class="label">{_tr("Start", "Début")}:</td>
                <td class="value">{_fmt_datetime(s.start_time)}</td></tr>
            <tr><td class="label">{_tr("End", "Fin")}:</td>
                <td class="value">{_fmt_datetime(s.end_time)}</td></tr>
            <tr><td class="label">{_tr("Duration", "Durée")}:</td>
                <td class="value">{_fmt_duration(s.duration_seconds)}</td></tr>
            <tr><td class="label">{_tr("Sampling rate", "Taux d'échantillonnage")}:</td>
                <td class="value">{s.sampling_rate_hz:.2f} Hz</td></tr>
        </table>

        <h3>{_tr("Data Records", "Enregistrements")}</h3>
        <table>
            <tr><td class="label">{_tr("Status records (Gstat)", "Enregistrements état (Gstat)")}:</td>
                <td class="value">{s.gstat_record_count:,}</td></tr>
            <tr><td class="label">{_tr("Time sync records", "Enregistrements synchro temps")}:</td>
                <td class="value">{s.time_sync_count:,}</td></tr>
            <tr><td class="label">{_tr("GPS records", "Enregistrements GPS")}:</td>
                <td class="value">{s.gps_record_count:,}</td></tr>
            <tr><td class="label">{_tr("Tracking data (>G)", "Données suivi (>G)")}:</td>
                <td class="value">{s.g_record_count:,}</td></tr>
            <tr><td class="label">{_tr("Encoder data (>H)", "Données encodeurs (>H)")}:</td>
                <td class="value">{s.h_record_count:,}</td></tr>
        </table>

        <h3>{_tr("Tracking Efficiency", "Efficacité de suivi")}</h3>
        <table>
            <tr><td class="label">{_tr("Tracking time", "Temps de suivi")}:</td>
                <td class="value">{_fmt_duration(s.activity.tracking_seconds)}</td></tr>
            <tr><td class="label">{_tr("Slewing time", "Temps de déplacement")}:</td>
                <td class="value">{_fmt_duration(s.activity.slewing_seconds)}</td></tr>
            <tr><td class="label">{_tr("Parked time", "Temps parquée")}:</td>
                <td class="value">{_fmt_duration(s.activity.parked_seconds)}</td></tr>
            <tr><td class="label">{_tr("Efficiency", "Efficacité")}:</td>
                <td class="value {'good' if s.activity.tracking_efficiency_percent > 80 else 'warn' if s.activity.tracking_efficiency_percent > 50 else 'bad'}">{s.activity.tracking_efficiency_percent:.1f}%</td></tr>
            <tr><td class="label">{_tr("Number of slews", "Nombre de GoTo")}:</td>
                <td class="value">{s.activity.num_slews}</td></tr>
            <tr><td class="label">{_tr("Avg slew duration", "Durée moy. GoTo")}:</td>
                <td class="value">{s.activity.avg_slew_duration_seconds:.1f}s</td></tr>
        </table>
        """

        if s.activity.num_model_building_slews > 0:
            html += f"""
        <h3>{_tr("Model Building Detected", "Construction de modèle détectée")}</h3>
        <table>
            <tr><td class="label">{_tr("Alignment slews", "GoTo d'alignement")}:</td>
                <td class="value">{s.activity.num_model_building_slews}</td></tr>
            <tr><td class="label">{_tr("Duration", "Durée")}:</td>
                <td class="value">{_fmt_duration(s.activity.model_building_duration_seconds)}</td></tr>
        </table>
        """

        if s.align_star_counts:
            max_stars = max(s.align_star_counts)
            html += f"""
        <h3>{_tr("Alignment Model", "Modèle d'alignement")}</h3>
        <table>
            <tr><td class="label">{_tr("Max alignment stars", "Max étoiles d'alignement")}:</td>
                <td class="value">{max_stars}</td></tr>
        </table>
        """

        ts = s.time_sync
        if ts.num_samples > 0:
            drift_class = 'good' if abs(ts.drift_rate_ms_per_hour) < 10 else 'warn' if abs(ts.drift_rate_ms_per_hour) < 50 else 'bad'
            html += f"""
        <h3>{_tr("Time Synchronization", "Synchronisation temps")}</h3>
        <table>
            <tr><td class="label">{_tr("PC-Mount mean diff", "Diff. moy. PC-Monture")}:</td>
                <td class="value">{ts.mean_diff_ms:.1f} ms</td></tr>
            <tr><td class="label">{_tr("Standard deviation", "Écart-type")}:</td>
                <td class="value">{ts.stdev_diff_ms:.2f} ms</td></tr>
            <tr><td class="label">{_tr("Min / Max", "Min / Max")}:</td>
                <td class="value">{ts.min_diff_ms:.1f} / {ts.max_diff_ms:.1f} ms</td></tr>
            <tr><td class="label">{_tr("Drift rate", "Taux de dérive")}:</td>
                <td class="value {drift_class}">{ts.drift_rate_ms_per_hour:+.2f} ms/h</td></tr>
        </table>
        """

        self._overview_text.setHtml(html)

    # ─── Activity Tab ────────────────────────────────────────────

    def _populate_activity(self):
        if self._tab_activity.layout():
            QWidget().setLayout(self._tab_activity.layout())

        layout = QVBoxLayout(self._tab_activity)

        # Activity timeline graph
        self._activity_plot = pg.PlotWidget(
            title=_tr("Mount Activity Timeline", "Timeline d'activité monture")
        )
        self._activity_plot.setBackground(Colors.BG_GRAPH)
        self._activity_plot.showGrid(x=True, y=False, alpha=0.2)
        self._activity_plot.setLabel('bottom',
            _tr("Time (hours from start)", "Temps (heures depuis le début)"))
        self._activity_plot.setLabel('left',
            _tr("State", "État"))
        layout.addWidget(self._activity_plot, stretch=3)

        # Pie-chart-like summary as HTML
        self._activity_summary = QTextEdit()
        self._activity_summary.setReadOnly(True)
        self._activity_summary.setMaximumHeight(200)
        self._activity_summary.setFont(QFont("Consolas", 10))
        layout.addWidget(self._activity_summary, stretch=1)

        if self._analysis and self._analysis.sessions:
            self._show_session_activity(self._analysis.sessions[0])

    def _show_session_activity(self, s: SessionAnalysis):
        plot = self._activity_plot
        plot.clear()

        segments = s.activity.gstat_segments
        if not segments:
            return

        t0 = segments[0].start_time
        y_ticks = []
        seen_states = set()

        for seg in segments:
            x_start = (seg.start_time - t0).total_seconds() / 3600.0
            x_end = (seg.end_time - t0).total_seconds() / 3600.0
            width = max(x_end - x_start, 0.001)  # Minimum visible width

            color = GSTAT_COLORS.get(seg.gstat, QColor(150, 150, 150))
            brush = pg.mkBrush(color)

            bar = pg.BarGraphItem(
                x=[x_start + width / 2],
                height=[1],
                width=[width],
                y0=[seg.gstat - 0.4],
                brush=brush,
                pen=pg.mkPen(color.darker(150), width=0.5),
            )
            plot.addItem(bar)

            if seg.gstat not in seen_states:
                seen_states.add(seg.gstat)
                name = seg.state_name_fr if _tr("en", "fr") == "fr" else seg.state_name
                y_ticks.append((seg.gstat, name))

        # Set Y axis ticks
        y_axis = plot.getAxis('left')
        y_axis.setTicks([y_ticks])

        # Add legend via colored markers for model building
        for slew in s.activity.slew_events:
            if slew.is_model_building:
                x_mid = ((slew.start_time - t0).total_seconds() +
                         (slew.end_time - t0).total_seconds()) / 2 / 3600.0
                plot.plot([x_mid], [6], pen=None,
                         symbol='star', symbolBrush='y', symbolSize=8)

        # Activity summary
        act = s.activity
        total = act.total_duration_seconds
        if total <= 0:
            return

        def pct(val):
            return val / total * 100 if total > 0 else 0

        html = f"""
        <style>
            body {{ color: #c8c8d2; font-family: Consolas, monospace; }}
            .bar {{ display: inline-block; height: 16px; margin-right: 8px; vertical-align: middle; }}
            table {{ border-collapse: collapse; }}
            td {{ padding: 2px 10px 2px 0; }}
        </style>
        <table>
            <tr>
                <td style="color: #50b450;">■ {_tr("Tracking", "Suivi")}</td>
                <td style="color: #e0e0ea;">{_fmt_duration(act.tracking_seconds)}</td>
                <td style="color: #e0e0ea;">{pct(act.tracking_seconds):.1f}%</td>
            </tr>
            <tr>
                <td style="color: #c864c8;">■ {_tr("Slewing", "Déplacement")}</td>
                <td style="color: #e0e0ea;">{_fmt_duration(act.slewing_seconds)}</td>
                <td style="color: #e0e0ea;">{pct(act.slewing_seconds):.1f}%</td>
            </tr>
            <tr>
                <td style="color: #64648c;">■ {_tr("Parked", "Parquée")}</td>
                <td style="color: #e0e0ea;">{_fmt_duration(act.parked_seconds)}</td>
                <td style="color: #e0e0ea;">{pct(act.parked_seconds):.1f}%</td>
            </tr>
            <tr>
                <td style="color: #c8c8d2;">■ {_tr("Other", "Autre")}</td>
                <td style="color: #e0e0ea;">{_fmt_duration(act.other_seconds)}</td>
                <td style="color: #e0e0ea;">{pct(act.other_seconds):.1f}%</td>
            </tr>
        </table>
        <p><b>{_tr("Tracking efficiency", "Efficacité de suivi")}: {act.tracking_efficiency_percent:.1f}%</b>
        &nbsp;|&nbsp; {_tr("Slews", "GoTo")}: {act.num_slews}
        &nbsp;|&nbsp; {_tr("Model building slews", "GoTo alignement")}: {act.num_model_building_slews}</p>
        """
        self._activity_summary.setHtml(html)

    # ─── Time Sync Tab ───────────────────────────────────────────

    def _populate_timesync(self):
        if self._tab_timesync.layout():
            QWidget().setLayout(self._tab_timesync.layout())

        layout = QVBoxLayout(self._tab_timesync)

        # Drift plot
        self._sync_plot = pg.PlotWidget(
            title=_tr("PC - Mount Time Difference",
                      "Différence de temps PC - Monture")
        )
        self._sync_plot.setBackground(Colors.BG_GRAPH)
        self._sync_plot.showGrid(x=True, y=True, alpha=0.2)
        self._sync_plot.setLabel('bottom',
            _tr("Time (hours from start)", "Temps (heures depuis le début)"))
        self._sync_plot.setLabel('left',
            _tr("Difference (ms)", "Différence (ms)"))
        layout.addWidget(self._sync_plot, stretch=3)

        # Stats panel
        self._sync_stats = QTextEdit()
        self._sync_stats.setReadOnly(True)
        self._sync_stats.setMaximumHeight(160)
        self._sync_stats.setFont(QFont("Consolas", 10))
        layout.addWidget(self._sync_stats, stretch=1)

        if self._analysis and self._analysis.sessions:
            self._show_session_timesync(self._analysis.sessions[0])

    def _show_session_timesync(self, s: SessionAnalysis):
        plot = self._sync_plot
        plot.clear()

        ts = s.time_sync
        if ts.num_samples == 0:
            return

        # Convert to hours from start
        t0 = ts.timestamps[0]
        x = np.array([(t - t0) / 3600.0 for t in ts.timestamps])
        y = np.array(ts.diffs_ms)

        # Subsample if too many points (>10000) for smooth rendering
        if len(x) > 10000:
            step = len(x) // 10000
            x_plot = x[::step]
            y_plot = y[::step]
        else:
            x_plot = x
            y_plot = y

        # Main data line
        plot.plot(x_plot, y_plot, pen=pg.mkPen(Colors.GRAPH_TIME_DIFF, width=1),
                  name=_tr("PC-Mount diff", "Diff PC-Monture"))

        # Mean line
        plot.addLine(y=ts.mean_diff_ms,
                     pen=pg.mkPen(Colors.ACCENT_BLUE, width=1, style=Qt.PenStyle.DashLine),
                     label=f"mean={ts.mean_diff_ms:.1f}ms")

        # +/- stdev band
        if ts.stdev_diff_ms > 0:
            upper = ts.mean_diff_ms + ts.stdev_diff_ms
            lower = ts.mean_diff_ms - ts.stdev_diff_ms
            plot.addLine(y=upper,
                         pen=pg.mkPen(Colors.ACCENT_BLUE, width=0.5, style=Qt.PenStyle.DotLine))
            plot.addLine(y=lower,
                         pen=pg.mkPen(Colors.ACCENT_BLUE, width=0.5, style=Qt.PenStyle.DotLine))

        # Trend line (linear regression)
        if len(x) > 10:
            x_range = np.array([x[0], x[-1]])
            slope = ts.drift_rate_ms_per_hour
            intercept = ts.mean_diff_ms - slope * np.mean(x)
            y_trend = slope * x_range + intercept
            plot.plot(x_range, y_trend,
                      pen=pg.mkPen(Colors.ACCENT_RED, width=2, style=Qt.PenStyle.DashLine),
                      name=_tr("Drift trend", "Tendance dérive"))

        # Legend
        plot.addLegend(offset=(10, 10))

        # Stats text
        drift_sign = "+" if ts.drift_rate_ms_per_hour >= 0 else ""
        html = f"""
        <style>
            body {{ color: #c8c8d2; font-family: Consolas, monospace; }}
            td {{ padding: 2px 12px 2px 0; }}
            .label {{ color: #8c8c9b; }}
            .value {{ color: #e0e0ea; }}
        </style>
        <table>
            <tr>
                <td class="label">{_tr("Samples", "Échantillons")}:</td>
                <td class="value">{ts.num_samples:,}</td>
                <td class="label">{_tr("Mean", "Moyenne")}:</td>
                <td class="value">{ts.mean_diff_ms:.2f} ms</td>
                <td class="label">{_tr("Median", "Médiane")}:</td>
                <td class="value">{ts.median_diff_ms:.2f} ms</td>
            </tr>
            <tr>
                <td class="label">{_tr("Std dev", "Écart-type")}:</td>
                <td class="value">{ts.stdev_diff_ms:.2f} ms</td>
                <td class="label">{_tr("Min", "Min")}:</td>
                <td class="value">{ts.min_diff_ms:.2f} ms</td>
                <td class="label">{_tr("Max", "Max")}:</td>
                <td class="value">{ts.max_diff_ms:.2f} ms</td>
            </tr>
            <tr>
                <td class="label">{_tr("Drift rate", "Dérive")}:</td>
                <td class="value" colspan="5">{drift_sign}{ts.drift_rate_ms_per_hour:.3f} ms/h</td>
            </tr>
        </table>
        <p style="color: #8c8c9b; font-size: 9px;">
            {_tr(
                "Positive values mean PC clock is ahead of mount clock. "
                "A stable, near-zero drift rate indicates good clock synchronization.",
                "Valeurs positives = horloge PC en avance sur la monture. "
                "Un taux de dérive stable et proche de zéro indique une bonne synchronisation."
            )}
        </p>
        """
        self._sync_stats.setHtml(html)

    # ─── Events Tab ──────────────────────────────────────────────

    def _populate_events(self):
        if self._tab_events.layout():
            QWidget().setLayout(self._tab_events.layout())

        layout = QVBoxLayout(self._tab_events)

        self._events_table = QTableWidget()
        self._events_table.setColumnCount(5)
        self._events_table.setHorizontalHeaderLabels([
            _tr("Time (UTC)", "Heure (UTC)"),
            _tr("Duration", "Durée"),
            _tr("State", "État"),
            _tr("State (FR)", "État (FR)"),
            _tr("Details", "Détails"),
        ])
        header = self._events_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self._events_table.setAlternatingRowColors(True)
        layout.addWidget(self._events_table)

        if self._analysis and self._analysis.sessions:
            self._show_session_events(self._analysis.sessions[0])

    def _show_session_events(self, s: SessionAnalysis):
        segments = s.activity.gstat_segments
        self._events_table.setRowCount(len(segments))

        model_slew_times = set()
        for slew in s.activity.slew_events:
            if slew.is_model_building:
                model_slew_times.add(slew.start_time)

        for i, seg in enumerate(segments):
            # Time
            time_item = QTableWidgetItem(seg.start_time.strftime("%H:%M:%S"))
            self._events_table.setItem(i, 0, time_item)

            # Duration
            dur_item = QTableWidgetItem(_fmt_duration(seg.duration_seconds))
            self._events_table.setItem(i, 1, dur_item)

            # State EN
            state_item = QTableWidgetItem(seg.state_name)
            color = GSTAT_COLORS.get(seg.gstat, QColor(150, 150, 150))
            state_item.setForeground(QBrush(color))
            self._events_table.setItem(i, 2, state_item)

            # State FR
            state_fr_item = QTableWidgetItem(seg.state_name_fr)
            state_fr_item.setForeground(QBrush(color))
            self._events_table.setItem(i, 3, state_fr_item)

            # Details
            details = ""
            if seg.gstat == 6 and seg.start_time in model_slew_times:
                details = _tr("Model building / alignment star",
                             "Construction modèle / étoile d'alignement")
            elif seg.gstat == 0 and seg.duration_seconds > 3600:
                details = _tr("Long tracking session",
                             "Longue session de suivi")
            detail_item = QTableWidgetItem(details)
            self._events_table.setItem(i, 4, detail_item)
