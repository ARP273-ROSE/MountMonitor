"""Real-time graph widgets using pyqtgraph.

Provides the main graph panels for:
- RA tracking data
- DEC tracking data
- Seismometer data
- Time comparison data
Each graph supports zoom, tolerance lines, STDEV overlay, min/max lines.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

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

        # Stats text overlay
        self._stats_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY,
            anchor=(1, 0)
        )
        self._stats_text.setFont(QFont('Consolas', 9))
        self._plot.addItem(self._stats_text)

        layout.addWidget(self._plot)

        # Connect resize to update watermark position
        self._plot.sigRangeChanged.connect(self._update_overlay_positions)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None,
                    min_val: float = None, max_val: float = None,
                    max_stdev: float = None):
        """Update graph with new data."""
        if len(timestamps) == 0:
            return

        # Normalize timestamps to relative seconds
        t0 = timestamps[0]
        rel_times = timestamps - t0

        self._data_curve.setData(rel_times, values)

        # Update STDEV
        if stdev_values is not None and len(stdev_values) == len(rel_times):
            self._stdev_curve.setData(rel_times, stdev_values)

        # Update min/max lines
        if min_val is not None and max_val is not None:
            self._min_line.setPos(min_val)
            self._max_line.setPos(max_val)
            self._min_line.setVisible(True)
            self._max_line.setVisible(True)

        # Update max STDEV line
        if max_stdev is not None and max_stdev > 0:
            self._max_stdev_line.setPos(max_stdev)
            self._max_stdev_line.setVisible(True)

        # Stats text
        if len(values) > 0:
            current = values[-1]
            rms = float(np.std(values))
            self._stats_text.setText(
                f"{current:+.2f}\"  σ={rms:.2f}\""
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

    def reset(self):
        """Clear graph data."""
        self._data_curve.setData([], [])
        self._stdev_curve.setData([], [])
        self._min_line.setVisible(False)
        self._max_line.setVisible(False)
        self._max_stdev_line.setVisible(False)


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

        layout.addWidget(self._plot)

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

    def reset(self):
        self._data_curve.setData([], [])
        self._stdev_curve.setData([], [])
