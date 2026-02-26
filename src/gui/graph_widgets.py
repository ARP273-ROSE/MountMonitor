"""Real-time graph widgets using pyqtgraph.

Provides the main graph panels for:
- RA tracking data
- DEC tracking data
- Seismometer data
- Time comparison data
Each graph supports zoom, tolerance lines, STDEV overlay, min/max lines.
"""

import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

logger = logging.getLogger(__name__)

from .theme import Colors
from ..utils.i18n import T


def _setup_pyqtgraph():
    """Configure pyqtgraph defaults for astronomy theme."""
    pg.setConfigOptions(
        background=Colors.BG_GRAPH,
        foreground=Colors.TEXT_SECONDARY,
        antialias=True,
        useOpenGL=True,
    )


_setup_pyqtgraph()


class TrackingGraph(QWidget):
    """Real-time tracking graph for RA or DEC data.

    Shows:
    - Main data line (deviation from reference in arcseconds)
    - Running STDEV line (blue, right Y axis)
    - Tolerance lines (green horizontal)
    - Min/Max lines (dashed horizontal)
    - Time fix marks (gray vertical lines every 30s)
    - Background watermark text
    """

    def __init__(self, title: str, data_color: QColor, parent=None):
        super().__init__(parent)
        self._title = title
        self._data_color = data_color
        self._tolerance = 1.5  # arcseconds

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create plot widget
        self._plot = pg.PlotWidget()
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setLabel('left', 'Deviation', units='"', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', 'Time', units='s', color=Colors.TEXT_SECONDARY.name())

        # Right Y axis for STDEV
        self._stdev_viewbox = pg.ViewBox()
        self._plot.scene().addItem(self._stdev_viewbox)
        self._plot.getAxis('right').linkToView(self._stdev_viewbox)
        self._stdev_viewbox.setXLink(self._plot)
        self._plot.showAxis('right')
        self._plot.getAxis('right').setLabel('STDEV', units='"', color=Colors.GRAPH_STDEV.name())

        # Data line
        pen = pg.mkPen(color=data_color, width=1.5)
        self._data_curve = self._plot.plot(pen=pen, name=title)

        # STDEV line (in stdev viewbox)
        stdev_pen = pg.mkPen(color=Colors.GRAPH_STDEV, width=1.5)
        self._stdev_curve = pg.PlotCurveItem(pen=stdev_pen)
        self._stdev_viewbox.addItem(self._stdev_curve)

        # Tolerance lines (green horizontal)
        tol_pen = pg.mkPen(color=Colors.GRAPH_TOLERANCE, width=1, style=Qt.PenStyle.SolidLine)
        self._tol_upper = pg.InfiniteLine(pos=self._tolerance, angle=0, pen=tol_pen)
        self._tol_lower = pg.InfiniteLine(pos=-self._tolerance, angle=0, pen=tol_pen)
        self._plot.addItem(self._tol_upper)
        self._plot.addItem(self._tol_lower)

        # Min/Max lines (dashed)
        mm_pen = pg.mkPen(color=data_color, width=1, style=Qt.PenStyle.DashLine)
        self._min_line = pg.InfiniteLine(pos=0, angle=0, pen=mm_pen, movable=False)
        self._max_line = pg.InfiniteLine(pos=0, angle=0, pen=mm_pen, movable=False)
        self._plot.addItem(self._min_line)
        self._plot.addItem(self._max_line)
        self._min_line.setVisible(False)
        self._max_line.setVisible(False)

        # Median line (gray center)
        median_pen = pg.mkPen(color=Colors.TEXT_MUTED, width=1, style=Qt.PenStyle.DashDotLine)
        self._median_line = pg.InfiniteLine(pos=0, angle=0, pen=median_pen)
        self._plot.addItem(self._median_line)

        # Max STDEV line (blue dashed)
        max_stdev_pen = pg.mkPen(color=Colors.GRAPH_STDEV, width=1, style=Qt.PenStyle.DashLine)
        self._max_stdev_line = pg.InfiniteLine(pos=0, angle=0, pen=max_stdev_pen)
        self._stdev_viewbox.addItem(self._max_stdev_line)
        self._max_stdev_line.setVisible(False)

        # Watermark text
        self._watermark = pg.TextItem(
            text=title, color=Colors.TEXT_MUTED,
            anchor=(0.5, 0.5)
        )
        font = QFont('Arial', 24, QFont.Weight.Bold)
        self._watermark.setFont(font)
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)

        # Min/Max annotation labels
        self._min_label = pg.TextItem(
            text='', color=data_color, anchor=(0, 0.5)
        )
        self._min_label.setFont(QFont('Consolas', 8))
        self._plot.addItem(self._min_label)
        self._min_label.setVisible(False)

        self._max_label = pg.TextItem(
            text='', color=data_color, anchor=(0, 0.5)
        )
        self._max_label.setFont(QFont('Consolas', 8))
        self._plot.addItem(self._max_label)
        self._max_label.setVisible(False)

        # Max STDEV annotation
        self._max_stdev_label = pg.TextItem(
            text='', color=Colors.GRAPH_STDEV, anchor=(0, 0.5)
        )
        self._max_stdev_label.setFont(QFont('Consolas', 8))
        self._stdev_viewbox.addItem(self._max_stdev_label)
        self._max_stdev_label.setVisible(False)

        # Stats text overlay
        self._stats_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY,
            anchor=(1, 0)
        )
        self._stats_text.setFont(QFont('Consolas', 9))
        self._plot.addItem(self._stats_text)

        # Time fix markers (grey vertical lines every 30s)
        self._time_fixes = []
        self._time_fix_labels = []

        layout.addWidget(self._plot)

        # Connect resize to update watermark position
        self._plot.sigRangeChanged.connect(self._update_overlay_positions)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None,
                    min_val: float = None, max_val: float = None,
                    max_stdev: float = None,
                    mount_times: list = None):
        """Update graph with new data.

        Args:
            timestamps: Array of POSIX timestamps
            values: Array of deviation values in arcseconds
            stdev_values: Running STDEV array
            min_val: Minimum deviation value
            max_val: Maximum deviation value
            max_stdev: Maximum STDEV value
            mount_times: Optional list of (timestamp, time_string) for time fixes
        """
        if len(timestamps) == 0:
            return

        # Normalize timestamps to relative seconds
        t0 = timestamps[0]
        rel_times = timestamps - t0
        t_end = rel_times[-1]

        self._data_curve.setData(rel_times, values)

        # Update STDEV
        if stdev_values is not None and len(stdev_values) == len(rel_times):
            self._stdev_curve.setData(rel_times, stdev_values)

        # Update min/max lines with annotations
        if min_val is not None and max_val is not None:
            self._min_line.setPos(min_val)
            self._max_line.setPos(max_val)
            self._min_line.setVisible(True)
            self._max_line.setVisible(True)
            # Annotations showing deviation from median
            self._min_label.setText(f" {min_val:+.2f}\"")
            self._min_label.setPos(t_end, min_val)
            self._min_label.setVisible(True)
            self._max_label.setText(f" {max_val:+.2f}\"")
            self._max_label.setPos(t_end, max_val)
            self._max_label.setVisible(True)

        # Update max STDEV line with annotation
        if max_stdev is not None and max_stdev > 0:
            self._max_stdev_line.setPos(max_stdev)
            self._max_stdev_line.setVisible(True)
            self._max_stdev_label.setText(f" max σ={max_stdev:.3f}\"")
            self._max_stdev_label.setPos(t_end, max_stdev)
            self._max_stdev_label.setVisible(True)

        # Time fix markers every 30 seconds
        self._update_time_fixes(t0, rel_times, mount_times)

        # Stats text
        if len(values) > 0:
            current = values[-1]
            rms = float(np.std(values))
            self._stats_text.setText(
                f"{current:+.2f}\"  \u03c3={rms:.2f}\""
            )

    def set_tolerance(self, arcsec: float):
        """Update tolerance lines."""
        self._tolerance = arcsec
        self._tol_upper.setPos(arcsec)
        self._tol_lower.setPos(-arcsec)

    def set_vertical_zoom(self, mode: str):
        """Set vertical zoom mode: data, tolerance, maximum, minmax."""
        vb = self._plot.getViewBox()
        if mode == "data":
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        elif mode == "tolerance":
            margin = self._tolerance * 1.2
            vb.setYRange(-margin, margin)
        elif mode == "maximum":
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        elif mode == "minmax":
            vb.enableAutoRange(axis=pg.ViewBox.YAxis)

    def _update_overlay_positions(self):
        """Update watermark and stats text positions after range change."""
        vb = self._plot.getViewBox()
        view_range = vb.viewRange()
        if view_range:
            x_center = (view_range[0][0] + view_range[0][1]) / 2
            y_center = (view_range[1][0] + view_range[1][1]) / 2
            self._watermark.setPos(x_center, y_center)
            self._stats_text.setPos(view_range[0][1], view_range[1][1])

    def export_to_image(self, directory: str):
        """Export graph as PNG to the specified directory."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"{self._title}_{timestamp}.png"
        try:
            exporter = pg.exporters.ImageExporter(self._plot.plotItem)
            exporter.parameters()['width'] = 1600
            exporter.export(str(filename))
            logger.info(f"Graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export graph: {e}")

    def _update_time_fixes(self, t0: float, rel_times: np.ndarray,
                           mount_times: list = None):
        """Draw grey vertical lines every 30 seconds with time labels."""
        # Remove old time fixes
        for item in self._time_fixes:
            self._plot.removeItem(item)
        for item in self._time_fix_labels:
            self._plot.removeItem(item)
        self._time_fixes.clear()
        self._time_fix_labels.clear()

        if len(rel_times) == 0:
            return

        t_max = rel_times[-1]
        fix_pen = pg.mkPen(Colors.TEXT_MUTED, width=1, style=Qt.PenStyle.DotLine)

        # Place a line every 30 seconds
        t = 30.0
        while t < t_max:
            line = pg.InfiniteLine(pos=t, angle=90, pen=fix_pen)
            self._plot.addItem(line)
            self._time_fixes.append(line)

            # Time label from mount_times or from offset
            label_text = ""
            if mount_times:
                # Find closest mount time to this offset
                target_ts = t0 + t
                closest = min(mount_times, key=lambda mt: abs(mt[0] - target_ts), default=None)
                if closest and abs(closest[0] - target_ts) < 15:
                    label_text = closest[1]
            if not label_text:
                # Fallback: show relative seconds
                m, s = divmod(int(t), 60)
                label_text = f"{m:02d}:{s:02d}"

            label = pg.TextItem(text=label_text, color=Colors.TEXT_MUTED, anchor=(0.5, 1))
            label.setFont(QFont('Consolas', 7))
            vr = self._plot.getViewBox().viewRange()
            y_top = vr[1][1] if vr else 0
            label.setPos(t, y_top)
            self._plot.addItem(label)
            self._time_fix_labels.append(label)

            t += 30.0

    def reset(self):
        """Clear graph data."""
        self._data_curve.setData([], [])
        self._stdev_curve.setData([], [])
        self._min_line.setVisible(False)
        self._max_line.setVisible(False)
        self._max_stdev_line.setVisible(False)
        self._min_label.setVisible(False)
        self._max_label.setVisible(False)
        self._max_stdev_label.setVisible(False)
        for item in self._time_fixes:
            self._plot.removeItem(item)
        for item in self._time_fix_labels:
            self._plot.removeItem(item)
        self._time_fixes.clear()
        self._time_fix_labels.clear()


class TimeGraph(QWidget):
    """Time comparison graph.

    Shows:
    - PC-Mount time difference (gray/white)
    - PC loop time (green)
    - Mount loop time (red)
    - PC-NTP difference (blue, when connected)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setLabel('left', 'Time diff', units='ms', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', 'Time', units='s', color=Colors.TEXT_SECONDARY.name())

        # Add legend
        self._plot.addLegend(offset=(10, 10))

        # Data curves
        self._diff_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_TIME_DIFF, width=1.5),
            name="PC-Mount"
        )
        self._pc_loop_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_TIME_PC, width=1),
            name="PC loop"
        )
        self._mount_loop_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_TIME_MOUNT, width=1),
            name="Mount loop"
        )
        self._ntp_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_NTP, width=1.5),
            name="PC-NTP"
        )

        # Zero line
        zero_pen = pg.mkPen(Colors.TEXT_MUTED, width=1, style=Qt.PenStyle.DashLine)
        self._zero_line = pg.InfiniteLine(pos=0, angle=0, pen=zero_pen)
        self._plot.addItem(self._zero_line)

        # Watermark
        self._watermark = pg.TextItem(
            text="TIME", color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
        )
        self._watermark.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)

        # Current values + drift overlay
        self._values_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY, anchor=(1, 0)
        )
        self._values_text.setFont(QFont('Consolas', 9))
        self._plot.addItem(self._values_text)
        self._plot.sigRangeChanged.connect(self._update_values_pos)

        layout.addWidget(self._plot)

    def _update_values_pos(self):
        """Keep values text in top-right corner."""
        vr = self._plot.getViewBox().viewRange()
        if vr:
            self._values_text.setPos(vr[0][1], vr[1][1])

    def update_data(self, diff_t, diff_v, pc_loop_t=None, pc_loop_v=None,
                    mount_loop_t=None, mount_loop_v=None,
                    ntp_t=None, ntp_v=None):
        """Update time graph data."""
        if len(diff_t) > 0:
            t0 = diff_t[0]
            self._diff_curve.setData(diff_t - t0, diff_v)
            if pc_loop_t is not None and len(pc_loop_t) > 0:
                self._pc_loop_curve.setData(pc_loop_t - t0, pc_loop_v)
            if mount_loop_t is not None and len(mount_loop_t) > 0:
                self._mount_loop_curve.setData(mount_loop_t - t0, mount_loop_v)
            if ntp_t is not None and len(ntp_t) > 0:
                self._ntp_curve.setData(ntp_t - t0, ntp_v)

            # Values + drift rate annotation
            parts = []
            if len(diff_v) > 0:
                parts.append(f"PC-Mount: {diff_v[-1]:+.1f}ms")
                # Compute drift rate (ms/min)
                if len(diff_v) > 20 and len(diff_t) > 20:
                    dt = diff_t[-1] - diff_t[0]
                    if dt > 0:
                        drift = (diff_v[-1] - diff_v[0]) / (dt / 60.0)
                        parts.append(f"Drift: {drift:+.2f}ms/min")
            if pc_loop_v is not None and len(pc_loop_v) > 0:
                parts.append(f"PC loop: {pc_loop_v[-1]:.1f}ms")
            if mount_loop_v is not None and len(mount_loop_v) > 0:
                parts.append(f"Mt loop: {mount_loop_v[-1]:.1f}ms")
            if ntp_v is not None and len(ntp_v) > 0:
                parts.append(f"NTP: {ntp_v[-1]:+.1f}ms")
            self._values_text.setText("  ".join(parts))

    def export_to_image(self, directory: str):
        """Export time graph as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"Time_{timestamp}.png"
        try:
            exporter = pg.exporters.ImageExporter(self._plot.plotItem)
            exporter.parameters()['width'] = 1600
            exporter.export(str(filename))
            logger.info(f"Time graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export time graph: {e}")

    def reset(self):
        """Clear all curves."""
        for curve in [self._diff_curve, self._pc_loop_curve,
                      self._mount_loop_curve, self._ntp_curve]:
            curve.setData([], [])


class SeismicGraph(QWidget):
    """Seismometer data graph.

    Shows raw seismic data with STDEV overlay and tolerance lines.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setLabel('left', 'Amplitude', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', 'Time', units='s', color=Colors.TEXT_SECONDARY.name())

        # Data curve
        self._data_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_SEISMIC, width=1)
        )

        # STDEV
        self._stdev_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_STDEV, width=1.5)
        )

        # Tolerance lines
        tol_pen = pg.mkPen(Colors.GRAPH_TOLERANCE, width=1)
        self._tol_upper = pg.InfiniteLine(pos=100, angle=0, pen=tol_pen)
        self._tol_lower = pg.InfiniteLine(pos=-100, angle=0, pen=tol_pen)
        self._plot.addItem(self._tol_upper)
        self._plot.addItem(self._tol_lower)

        # Watermark
        self._watermark = pg.TextItem(
            text="SEISMIC", color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
        )
        self._watermark.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)

        layout.addWidget(self._plot)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None):
        """Update seismic graph."""
        if len(timestamps) > 0:
            t0 = timestamps[0]
            self._data_curve.setData(timestamps - t0, values)
            if stdev_values is not None and len(stdev_values) == len(timestamps):
                self._stdev_curve.setData(timestamps - t0, stdev_values)

    def set_tolerance(self, percent: float, data_range: int):
        """Set tolerance as percentage of range."""
        tol = data_range * percent / 100.0
        self._tol_upper.setPos(tol)
        self._tol_lower.setPos(-tol)

    def export_to_image(self, directory: str):
        """Export seismic graph as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"Seismic_{timestamp}.png"
        try:
            exporter = pg.exporters.ImageExporter(self._plot.plotItem)
            exporter.parameters()['width'] = 1600
            exporter.export(str(filename))
            logger.info(f"Seismic graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export seismic graph: {e}")

    def reset(self):
        self._data_curve.setData([], [])
        self._stdev_curve.setData([], [])
