"""Real-time graph widgets using pyqtgraph.

Provides the main graph panels for:
- RA tracking data
- DEC tracking data
- Seismometer data
- Time comparison data
Each graph supports zoom, tolerance lines, STDEV overlay, min/max lines.
"""

import logging
import os
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
    """Configure pyqtgraph defaults for astronomy theme.

    Antialiasing costs about 40 % of the drawing time: kept on machines with
    eight threads or more, off on small observatory PCs (2-4 cores) where it
    would compete with the polling. OpenGL stays off: old Intel iGPUs and
    remote desktop sessions are where it fails.
    """
    pg.setConfigOptions(
        background=Colors.BG_GRAPH,
        foreground=Colors.TEXT_SECONDARY,
        antialias=(os.cpu_count() or 2) >= 8,
        useOpenGL=False,
    )
    # No automatic SI prefixes on the axes: they turned 4000 ms into "kms",
    # 0.4" into "m"" (read as minutes) and 0.004 "/s into "m"/s".
    if not getattr(pg.AxisItem, "_no_prefix", False):
        _init = pg.AxisItem.__init__

        def _init_no_prefix(self, *a, **k):
            _init(self, *a, **k)
            self.autoSIPrefix = False
        pg.AxisItem.__init__ = _init_no_prefix
        pg.AxisItem._no_prefix = True


_setup_pyqtgraph()



LEFT_AXIS_WIDTH = 70
RIGHT_AXIS_WIDTH = 62


def align_axes(plot):
    """Same left and right axis widths on every graph, so that the plot areas
    line up: a spike in RA sits right above the same instant in the time
    graph (time jumps cause RA jumps). The RA/DEC graphs carry the sigma
    axis on the right; the others get an empty one of the same width."""
    pi = plot.getPlotItem()
    pi.getAxis('left').setWidth(LEFT_AXIS_WIDTH)
    pi.showAxis('right')
    right = pi.getAxis('right')
    right.setWidth(RIGHT_AXIS_WIDTH)
    right.setStyle(showValues=False, tickLength=0)
    right.setPen(pg.mkPen(None))
    return right


def match_axes(plot):
    """Copy the view box range onto the axis ticks.

    The graphs change their range while the view box signals are blocked
    — on purpose, to avoid a cascade of recomputations at every refresh.
    But that very signal is what notifies the axes: blocked, it leaves
    them on the range they had when created, that is [0, 1].

    Result: the curves moved, the ticks stayed frozen from zero to one.
    A graph showing forty seconds of data was ticked "0.2; 0.4; 0.6" with
    "Time (s)" below — and the displacement in arcseconds was read on an
    equally wrong scale. Literally nothing accurate could be read on these
    graphs.

    Checked by measurement: `axis.range` was [0, 1] while the view
    covered [0; 39.46].
    """
    view = plot.getViewBox()
    (x0, x1), (y0, y1) = view.viewRange()
    plot.getAxis('bottom').setRange(x0, x1)
    plot.getAxis('left').setRange(y0, y1)


def horizontal_window(widget, rel_times, t_end, zoom):
    """Start of the displayed range, according to the horizontal zoom.

    Follows the rule of the Java MountMonitor: at zoom 1, one data point
    takes one pixel, so the screen shows as many points as it is pixels
    wide; at zoom 5, each point takes five pixels, so one sees five times
    less data — but in detail.

    The "Horizontal zoom" menu existed and did nothing: the setting was
    saved, never applied.

    🔴 The rule applies AT zoom 1 TOO. A first version returned 0.0 in that
    case — i.e. the start of the buffer — and zoom 1 being the default,
    the curves no longer scrolled at all: the axis started at zero and
    stretched as the night went on, squeezing the data into the middle. On
    a seven-hour session the axis reached 26 ks and the displayed standard
    deviation climbed to 1960 arcsec, while the mount was holding to 0.06.
    """
    try:
        zoom = max(1, int(zoom))
    except (TypeError, ValueError):
        zoom = 1
    if len(rel_times) == 0:
        return 0.0
    span = max(200, int(widget.width()))
    visible_points = max(10, span // zoom)
    if len(rel_times) <= visible_points:
        return 0.0
    return float(rel_times[-visible_points])


WINDOW_SPAN_S = 120.0


def window_width(zoom, base=WINDOW_SPAN_S):
    """Width, in seconds, of the window that scrolls at the present.

    At zoom 1 one sees the last two minutes; at zoom 5, the last
    twenty-four seconds, in detail.
    """
    try:
        zoom = max(1, int(zoom))
    except (TypeError, ValueError):
        zoom = 1
    return float(base) / zoom


# Offered widths (View menu and right-click on a graph). The horizontal
# zoom could only shrink the initial two minutes: no way to see half an
# hour of tracking, which the Java MountMonitor did.
SPANS_S = (30, 60, 120, 300, 600, 1800, 3600)


def shown_span(value, base=WINDOW_SPAN_S):
    """Configured width ("time_span_s"), clamped to a sensible value."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(base)
    if not (v > 0):
        return float(base)
    return min(max(v, 10.0), 4 * 3600.0)


def span_name(seconds):
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    return f"{s / 3600:g} h"


def tick_spacing(span):
    """Hour tick spacing: about ten at most on screen, whatever the
    width (every 30 s over two minutes, every 5 min over an
    hour)."""
    for step in (30, 60, 120, 300, 600, 900, 1800, 3600):
        if span / step <= 10:
            return float(step)
    return 3600.0


def vertical_range(mode, values, tolerance, min_val=None, max_val=None):
    """(low, high) of the vertical axis of a tracking graph per the chosen mode.

    - data: the data alone, centred on their median — the tolerance lines
      leave the frame when tracking is much better than them;
    - tolerance: +-tolerance;
    - maximum: whichever of the two is larger (the old behaviour, which
      was applied whatever the menu choice);
    - minmax: the min/max lines of the night.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    tol = abs(float(tolerance or 0.0))
    if mode == "tolerance" and tol > 0:
        return -1.2 * tol, 1.2 * tol
    if mode == "minmax" and min_val is not None and max_val is not None:
        m = max(abs(min_val), abs(max_val), 0.05) * 1.2
        return -m, m
    if len(v) == 0:
        m = max(tol, 0.1) * 1.3
        return -m, m
    if mode == "data":
        center = float(np.median(v))
        half = float(np.max(np.abs(v - center))) * 1.3
        half = max(half, 0.05)
        return center - half, center + half
    m = max(float(np.max(np.abs(v))), tol) * 1.3
    return -m, m


DRIFT_DURATION_S = 1800.0


def clock_drift(t, v, duration=DRIFT_DURATION_S):
    """Drift of the PC - mount offset, in ms per hour.

    Least-squares slope over the last `duration` seconds, after rejecting
    outliers (beyond 4 median absolute deviations from the line: a slow
    loop gives a spike of several hundred ms). The old formula — last
    point minus first point of the displayed window — jumped at every new
    sample, since each point carries tens of milliseconds of noise.

    None until there are two minutes of data: a slope over a few seconds
    means nothing.
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    if len(t) < 20:
        return None
    keep = t >= t[-1] - float(duration)
    t, v = t[keep], v[keep]
    if len(t) < 20 or t[-1] - t[0] < 120.0:
        return None
    x = (t - t[-1]) / 3600.0
    for _ in range(2):
        a, b = np.polyfit(x, v, 1)
        r = v - (a * x + b)
        mad = float(np.median(np.abs(r - np.median(r))))
        if mad <= 0:
            break
        keep = np.abs(r) <= 4.0 * 1.4826 * mad
        if keep.sum() < 20 or keep.all():
            break
        x, v = x[keep], v[keep]
    a, _ = np.polyfit(x, v, 1)
    return float(a)


def stdev_scale(sd_max):
    """(top, step) of the standard deviation axis, MountMonitor 3 rule:

        theLog = round(log10(maxSD * 3.3)), at least -3
        top = 10^theLog ; step = 2 * 10^(theLog - 1)

    i.e. a power of ten between one and ten times the largest sigma,
    ticked in five.
    """
    try:
        x = float(sd_max) * 3.3
    except (TypeError, ValueError):
        x = 0.0
    if not (x > 0) or not np.isfinite(x):
        n = -1
    else:
        n = max(-3, int(round(np.log10(x))))
    high = 10.0 ** n
    if sd_max and high < sd_max:     # never cut the curve
        high *= 10.0
        n += 1
    return high, 2.0 * 10.0 ** (n - 1)


def window_start(timestamps, limit):
    """Index of the first sample to keep to plot from `limit`.

    One sample before the limit is kept, so that the curve touches the
    left edge instead of starting in mid-air.

    🔴 This, not the graph, is where the night is cut. The graph used to
    receive the WHOLE buffer — up to 50,000 samples, i.e. several nights
    in a row — reduced to 5,000 points; the "one point per pixel" rule
    applied to those reduced points, each worth about ten samples. The
    window thus covered hours, the axis started at the buffer start and
    was ticked in ks, and nothing scrolled.
    """
    if len(timestamps) == 0:
        return 0
    i = int(np.searchsorted(timestamps, limit, side='left'))
    return max(0, i - 1)


def cut_to_present(t, v, span_s, t_end=None, *others):
    """Keep from (t, v, others...) only the last `span_s` seconds."""
    if t is None or len(t) == 0:
        return (t, v) + others
    if t_end is None:
        t_end = float(t[-1])
    i = window_start(t, t_end - span_s)
    cuts = tuple(a[i:] if a is not None and len(a) == len(t) else None
                   for a in others)
    return (t[i:], v[i:]) + cuts


def hour_label(t_abs):
    """Local time of a timestamp, or elapsed time if it is not a date."""
    if t_abs > 1e9:
        return datetime.fromtimestamp(t_abs).strftime("%H:%M:%S")
    m, s_ = divmod(int(t_abs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s_:02d}" if h > 0 else f"{m:02d}:{s_:02d}"


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
        self._vertical_mode = "data"
        self._unit = '"'      # '"' (arcsec) or 's' (seconds of time, RA)
        self._decimals = 2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create plot widget — disable auto-range to prevent signal cascades
        self._plot = pg.PlotWidget()
        self._right_axis = align_axes(self._plot)
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(title, color=data_color.name(), size='11pt')
        self._plot.setLabel('left', T('deviation'), units='"', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s', color=Colors.TEXT_SECONDARY.name())
        self._plot.getViewBox().disableAutoRange()

        # Data line. One hour at 2 Hz is 7200 points: only one per pixel
        # is drawn (peaks kept), and only within the frame.
        self._plot.setDownsampling(auto=True, mode='peak')
        self._plot.setClipToView(True)
        pen = pg.mkPen(color=data_color, width=1.5)
        self._data_curve = self._plot.plot(pen=pen, name=title)

        # STDEV on its own scale (right axis), from zero at the bottom, as in
        # MountMonitor 3: on the deviation scale a 0.1" sigma was a flat line
        # at the foot of the graph, and under non-sidereal tracking (Sun,
        # planets, comets) the drift pushed the scale so far it vanished.
        # The second view is never linked: its range is set by hand in
        # update_data, signals blocked like the main one (no range cascade).
        self._vb_sd = pg.ViewBox(enableMouse=False)
        self._vb_sd.disableAutoRange()
        self._vb_sd.setMenuEnabled(False)
        pi = self._plot.getPlotItem()
        pi.showAxis('right')
        pi.scene().addItem(self._vb_sd)
        right_axis = pi.getAxis('right')
        right_axis.setStyle(showValues=True, tickLength=5)
        right_axis.linkToView(self._vb_sd)
        right_axis.setLabel('σ', units='"', color=Colors.GRAPH_STDEV.name())
        right_axis.enableAutoSIPrefix(False)
        right_axis.setPen(pg.mkPen(Colors.GRAPH_STDEV))
        right_axis.setTextPen(pg.mkPen(Colors.GRAPH_STDEV))

        def _align():
            self._vb_sd.setGeometry(pi.vb.sceneBoundingRect())
        pi.vb.sigResized.connect(_align)
        self._align_sd = _align

        stdev_pen = pg.mkPen(color=Colors.GRAPH_STDEV, width=1.5)
        self._stdev_curve = pg.PlotDataItem(pen=stdev_pen)
        self._stdev_curve.setDownsampling(auto=True, method='peak')
        self._stdev_curve.setClipToView(True)
        self._vb_sd.addItem(self._stdev_curve)

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
        self._vb_sd.addItem(self._max_stdev_line)
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
        self._min_label.setFont(QFont('Source Code Pro', 8))
        self._plot.addItem(self._min_label)
        self._min_label.setVisible(False)

        self._max_label = pg.TextItem(
            text='', color=data_color, anchor=(0, 0.5)
        )
        self._max_label.setFont(QFont('Source Code Pro', 8))
        self._plot.addItem(self._max_label)
        self._max_label.setVisible(False)

        # Max STDEV annotation
        self._max_stdev_label = pg.TextItem(
            text='', color=Colors.GRAPH_STDEV, anchor=(0, 0.5)
        )
        self._max_stdev_label.setFont(QFont('Source Code Pro', 8))
        self._vb_sd.addItem(self._max_stdev_label)
        self._max_stdev_label.setVisible(False)

        # Stats text overlay
        self._stats_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY,
            anchor=(1, 0)
        )
        self._stats_text.setFont(QFont('Source Code Pro', 9))
        self._plot.addItem(self._stats_text)

        # Tolerance value annotations (labels showing the arcsec value)
        self._tol_upper_label = pg.TextItem(
            text='', color=Colors.GRAPH_TOLERANCE, anchor=(1, 1)
        )
        self._tol_upper_label.setFont(QFont('Source Code Pro', 8))
        self._plot.addItem(self._tol_upper_label)

        self._tol_lower_label = pg.TextItem(
            text='', color=Colors.GRAPH_TOLERANCE, anchor=(1, 0)
        )
        self._tol_lower_label.setFont(QFont('Source Code Pro', 8))
        self._plot.addItem(self._tol_lower_label)

        # Time fix markers (grey vertical lines every 30s)
        # Pool a fixed max number to avoid unbounded growth over long sessions
        self._time_fixes = []
        self._time_fix_labels = []
        self._MAX_TIME_FIXES = 40  # Max visible at once; recycle pool
        # Cache pen/font objects — avoid recreating every refresh
        self._fix_pen = pg.mkPen(Colors.TEXT_MUTED, width=1, style=Qt.PenStyle.DotLine)
        self._fix_label_font = QFont('Source Code Pro', 7)

        layout.addWidget(self._plot)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None,
                    stdev_timestamps: np.ndarray = None,
                    min_val: float = None, max_val: float = None,
                    max_stdev: float = None,
                    mount_times: list = None,
                    span_s: float = None):
        """Update graph with new data.

        Manages range manually to avoid sigRangeChanged cascades.

        With `span_s`, the graph scrolls at the present: the abscissa is
        the time before now (from -span_s to 0), and `timestamps` must
        contain only the window (see `cut_to_present`). Without it, it
        shows a whole session (replay), from its start.
        """
        if len(timestamps) == 0:
            return

        # Normalize timestamps to relative seconds
        t0 = timestamps[-1] if span_s else timestamps[0]
        rel_times = timestamps - t0
        t_end = rel_times[-1]

        # Block signals during batch update to prevent cascades
        vb = self._plot.getViewBox()
        vb.blockSignals(True)

        self._data_curve.setData(rel_times, values)

        # Update STDEV (with optional corrected timestamps)
        if stdev_values is not None and stdev_timestamps is not None:
            if len(stdev_values) == len(stdev_timestamps):
                self._stdev_curve.setData(stdev_timestamps - t0, stdev_values)
        elif stdev_values is not None and len(stdev_values) == len(rel_times):
            self._stdev_curve.setData(rel_times, stdev_values)

        # Update min/max lines with annotations
        if min_val is not None and max_val is not None:
            self._min_line.setPos(min_val)
            self._max_line.setPos(max_val)
            self._min_line.setVisible(True)
            self._max_line.setVisible(True)
            self._min_label.setText(f" {min_val:+.{self._decimals}f}{self._unit}")
            self._min_label.setPos(t_end, min_val)
            self._min_label.setVisible(True)
            self._max_label.setText(f" {max_val:+.{self._decimals}f}{self._unit}")
            self._max_label.setPos(t_end, max_val)
            self._max_label.setVisible(True)

        # Update max STDEV line with annotation
        if max_stdev is not None and max_stdev > 0:
            self._max_stdev_line.setPos(max_stdev)
            self._max_stdev_line.setVisible(True)
            self._max_stdev_label.setText(
                f" max σ={max_stdev:.{self._decimals + 1}f}{self._unit}")
            self._max_stdev_label.setPos(t_end, max_stdev)
            self._max_stdev_label.setVisible(True)

        # Stats text
        if len(values) > 0:
            current = values[-1]
            rms = float(np.std(values))
            d, u = self._decimals, self._unit
            self._stats_text.setText(f"{current:+.{d}f}{u}  \u03c3={rms:.{d}f}{u}")

        # Manually set range (replaces auto-range)
        y_low, y_high = vertical_range(self._vertical_mode, values,
                                        self._tolerance, min_val, max_val)
        if span_s:
            x0, x1 = -float(span_s), 0.0
        else:
            x0 = horizontal_window(self, rel_times, t_end,
                                     getattr(self, '_horizontal_zoom', 1))
            x1 = max(t_end, x0 + 1.0)
        vb.setRange(xRange=(x0, x1), yRange=(y_low, y_high), padding=0)
        vb.blockSignals(False)
        match_axes(self._plot)

        # Sigma scale: 0 at the bottom, top from the largest sigma seen.
        sd_max = float(max_stdev or 0.0)
        if stdev_values is not None and len(stdev_values):
            sd_max = max(sd_max, float(np.nanmax(stdev_values)))
        sd_high, sd_step = stdev_scale(sd_max)
        self._vb_sd.blockSignals(True)
        self._vb_sd.setRange(xRange=(x0, x1), yRange=(0.0, sd_high), padding=0)
        self._vb_sd.blockSignals(False)
        right_axis = self._plot.getPlotItem().getAxis('right')
        right_axis.setRange(0.0, sd_high)
        right_axis.setTickSpacing(sd_step * 5, sd_step)
        self._align_sd()

        # Time fix markers every 30 seconds (after the range: they read it)
        self._update_time_fixes(t0, rel_times, mount_times)

        # Position overlays after range is set
        x_right = x1
        self._watermark.setPos((x0 + x1) / 2, 0)
        self._stats_text.setPos(x_right, y_high)
        self._tol_upper_label.setPos(x_right, self._tolerance)
        self._tol_lower_label.setPos(x_right, -self._tolerance)

    def set_tolerance(self, arcsec: float):
        """Update tolerance lines and their annotations (only if changed)."""
        if arcsec == self._tolerance:
            return
        self._tolerance = arcsec
        self._tol_upper.setPos(arcsec)
        self._tol_lower.setPos(-arcsec)
        d, u = self._decimals, self._unit
        self._tol_upper_label.setText(f'{arcsec:+.{d}f}{u}')
        self._tol_lower_label.setText(f'{-arcsec:+.{d}f}{u}')

    def set_unit(self, unit: str):
        """'"' (arcseconds) or 's' (seconds of time, RA in hours mode)."""
        if unit == self._unit:
            return
        self._unit = unit
        self._decimals = 3 if unit == 's' else 2
        self._plot.setLabel('left', T('deviation'), units=unit,
                            color=Colors.TEXT_SECONDARY.name())
        self._plot.getPlotItem().getAxis('right').setLabel(
            'σ', units=unit, color=Colors.GRAPH_STDEV.name())
        t, self._tolerance = self._tolerance, None
        self.set_tolerance(t)

    def set_vertical_zoom(self, mode: str):
        """Vertical axis mode: data, tolerance, maximum, minmax.

        Applied at every refresh (see `vertical_range`). Before, the
        choice was saved and then overwritten four times a second by a
        range that always included the tolerance lines.
        """
        if mode in ("data", "tolerance", "maximum", "minmax"):
            self._vertical_mode = mode

    def export_to_image(self, directory: str):
        """Export graph as PNG to the specified directory."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"{self._title}_{timestamp}.png"
        try:
            export = pg.exporters.ImageExporter(self._plot.plotItem)
            export.parameters()['width'] = 1600
            export.export(str(filename))
            logger.info(f"Graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export graph: {e}")

    def _update_time_fixes(self, t0: float, rel_times: np.ndarray,
                           mount_times: list = None):
        """Draw grey vertical lines every 30 seconds with time labels.

        Uses a fixed-size pool of plot items to avoid unbounded growth.
        Only shows marks within the visible time range.
        """
        if len(rel_times) == 0:
            return

        t_max = rel_times[-1]

        # The marks fall on the 30 s multiples of real time: they
        # therefore slide with the curve instead of staying fixed on screen.
        vr = self._plot.getViewBox().viewRange()
        x_min, x_max = vr[0]
        y_top = vr[1][1]
        a_min = t0 + max(x_min, float(rel_times[0]))
        a_max = t0 + min(x_max, float(t_max))
        step = tick_spacing(x_max - x_min)
        first_mark = int(np.ceil(a_min / step))
        last_mark = int(np.floor(a_max / step))
        visible_marks = list(range(first_mark, last_mark + 1))

        # Limit to pool size
        if len(visible_marks) > self._MAX_TIME_FIXES:
            visible_marks = visible_marks[-self._MAX_TIME_FIXES:]

        # Grow pool up to max if needed (using cached pen/font)
        while len(self._time_fixes) < min(len(visible_marks), self._MAX_TIME_FIXES):
            line = pg.InfiniteLine(pos=0, angle=90, pen=self._fix_pen)
            label = pg.TextItem(text='', color=Colors.TEXT_MUTED, anchor=(0.5, 1))
            label.setFont(self._fix_label_font)
            self._plot.addItem(line)
            self._plot.addItem(label)
            self._time_fixes.append(line)
            self._time_fix_labels.append(label)

        # Update pool items: assign visible marks to pool slots
        for i in range(len(self._time_fixes)):
            if i < len(visible_marks):
                t_abs = step * visible_marks[i]
                t = t_abs - t0
                self._time_fixes[i].setPos(t)
                self._time_fixes[i].setVisible(True)

                self._time_fix_labels[i].setText(hour_label(t_abs))
                self._time_fix_labels[i].setPos(t, y_top)
                self._time_fix_labels[i].setVisible(True)
            else:
                self._time_fixes[i].setVisible(False)
                self._time_fix_labels[i].setVisible(False)

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
            item.setVisible(False)
        for item in self._time_fix_labels:
            item.setVisible(False)


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
        self._right_axis = align_axes(self._plot)
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(T("time_graph_title"), color='#aaaaaa', size='11pt')
        self._plot.setDownsampling(auto=True, mode='peak')
        self._plot.setClipToView(True)
        self._plot.setLabel('left', T('time_diff'), units='ms', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s', color=Colors.TEXT_SECONDARY.name())
        # pyqtgraph picks a prefix on its own and sticks it before the unit.
        # On an already prefixed unit such as "ms", that gave "mms" —
        # milli-milliseconds — and ticks unrelated to the values shown in
        # the legend, which are in milliseconds. On this axis milliseconds
        # are the right order of magnitude: the unit is kept as is.
        self._plot.getAxis('left').enableAutoSIPrefix(False)

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
        red = QColor(Colors.GRAPH_TIME_MOUNT)
        red.setAlpha(150)      # under the green, without hiding it
        self._mount_loop_curve = self._plot.plot(
            pen=pg.mkPen(red, width=1),
            name="Mount loop"
        )
        # Green (PC loop) drawn on top, as in MountMonitor 3: the mount loop
        # (red) otherwise hid it completely.
        self._pc_loop_curve.setZValue(10)
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
            text=T("time_graph"), color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
        )
        self._watermark.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)

        # Current values + drift overlay
        self._values_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY, anchor=(1, 0)
        )
        self._values_text.setFont(QFont('Source Code Pro', 9))
        self._plot.addItem(self._values_text)
        self._plot.getViewBox().disableAutoRange()

        layout.addWidget(self._plot)

    def update_data(self, diff_t, diff_v, pc_loop_t=None, pc_loop_v=None,
                    mount_loop_t=None, mount_loop_v=None,
                    ntp_t=None, ntp_v=None, span_s=None,
                    drift_ms_h=None):
        """Update time graph data (at the present if `span_s`).

        `drift_ms_h`: clock drift, fitted over the last minutes (see
        `clock_drift`). Without it, no drift is displayed rather than a
        false one."""
        if len(diff_t) > 0:
            t0 = diff_t[-1] if span_s else diff_t[0]
            vb = self._plot.getViewBox()
            vb.blockSignals(True)

            rel_t = diff_t - t0
            self._diff_curve.setData(rel_t, diff_v)
            if pc_loop_t is not None and len(pc_loop_t) > 0:
                self._pc_loop_curve.setData(pc_loop_t - t0, pc_loop_v)
            if mount_loop_t is not None and len(mount_loop_t) > 0:
                self._mount_loop_curve.setData(mount_loop_t - t0, mount_loop_v)
            if ntp_t is not None and len(ntp_t) > 0:
                self._ntp_curve.setData(ntp_t - t0, ntp_v)

            # Manual range
            all_v = [diff_v]
            if pc_loop_v is not None and len(pc_loop_v) > 0:
                all_v.append(pc_loop_v)
            if mount_loop_v is not None and len(mount_loop_v) > 0:
                all_v.append(mount_loop_v)
            combined = np.concatenate(all_v)
            y_min = float(np.min(combined))
            y_max = float(np.max(combined))
            y_margin = max(abs(y_max - y_min) * 0.1, 1.0)
            t_end = rel_t[-1]
            if span_s:
                x0, x1 = -float(span_s), 0.0
            else:
                x0 = horizontal_window(self, rel_t, t_end,
                                         getattr(self, '_horizontal_zoom', 1))
                x1 = max(t_end, x0 + 1.0)
            vb.setRange(xRange=(x0, x1),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)
            vb.blockSignals(False)
            match_axes(self._plot)

            # Position overlays
            self._values_text.setPos(x1, y_max + y_margin)
            self._watermark.setPos((x0 + x1) / 2, (y_min + y_max) / 2)

            # Values + drift rate annotation
            parts = []
            if len(diff_v) > 0:
                parts.append(f"PC-Mount: {diff_v[-1]:+.1f}ms")
                if drift_ms_h is not None:
                    parts.append(f"Drift: {drift_ms_h:+.1f}ms/h")
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
            export = pg.exporters.ImageExporter(self._plot.plotItem)
            export.parameters()['width'] = 1600
            export.export(str(filename))
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
        self._right_axis = align_axes(self._plot)
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(T("seismic_title"), color='#aaaaaa', size='11pt')
        self._plot.setDownsampling(auto=True, mode='peak')
        self._plot.setClipToView(True)
        self._plot.setLabel('left', T('seismic_counts'), color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s', color=Colors.TEXT_SECONDARY.name())

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
            text=T("seismic"), color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
        )
        self._watermark.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)
        self._plot.getViewBox().disableAutoRange()

        layout.addWidget(self._plot)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None, span_s: float = None,
                    stdev_timestamps: np.ndarray = None):
        """Update seismic graph (at the present if `span_s`)."""
        if len(timestamps) > 0:
            t0 = timestamps[-1] if span_s else timestamps[0]
            vb = self._plot.getViewBox()
            vb.blockSignals(True)

            rel_t = timestamps - t0
            self._data_curve.setData(rel_t, values)
            if stdev_values is not None and stdev_timestamps is not None:
                if len(stdev_values) == len(stdev_timestamps):
                    self._stdev_curve.setData(stdev_timestamps - t0, stdev_values)
            elif stdev_values is not None and len(stdev_values) == len(timestamps):
                self._stdev_curve.setData(rel_t, stdev_values)

            # Manual range
            t_end = float(rel_t[-1])
            y_min = float(np.min(values))
            y_max = float(np.max(values))
            y_margin = max(abs(y_max - y_min) * 0.15, 1.0)
            if span_s:
                x0, x1 = -float(span_s), 0.0
            else:
                x0 = horizontal_window(self, rel_t, t_end,
                                         getattr(self, '_horizontal_zoom', 1))
                x1 = max(t_end, x0 + 1.0)
            vb.setRange(xRange=(x0, x1),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)
            vb.blockSignals(False)
            match_axes(self._plot)

            # Position watermark
            self._watermark.setPos((x0 + x1) / 2, (y_min + y_max) / 2)

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
            export = pg.exporters.ImageExporter(self._plot.plotItem)
            export.parameters()['width'] = 1600
            export.export(str(filename))
            logger.info(f"Seismic graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export seismic graph: {e}")

    def reset(self):
        self._data_curve.setData([], [])
        self._stdev_curve.setData([], [])


class AxialGraph(QWidget):
    """Axial velocity/displacement graph.

    Shows for RA and DEC axes:
    - Raw speed (thin grey)
    - 6-sample running average speed (thick bright line)
    - Linear regression overlay (extra thick, annotated with slope)
    Equivalent to the Java Axial Velocity/Displacement graph.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget()
        self._right_axis = align_axes(self._plot)
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(T("axial_title"), color='#aaaaaa', size='11pt')
        self._plot.setLabel('left', T('speed_label'), units='"/s',
                            color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s',
                            color=Colors.TEXT_SECONDARY.name())
        self._plot.addLegend(offset=(10, 10))

        # RA raw speed (thin grey)
        self._ra_raw_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_SPEED_RAW, width=1),
            name="RA raw"
        )
        # DEC raw speed (thin grey, slightly different shade)
        self._dec_raw_curve = self._plot.plot(
            pen=pg.mkPen(QColor(140, 140, 150), width=1),
            name="DEC raw"
        )
        # RA average speed (thick bright magenta)
        self._ra_avg_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_RA, width=2.5),
            name="RA avg"
        )
        # DEC average speed (thick bright red)
        self._dec_avg_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_DEC, width=2.5),
            name="DEC avg"
        )
        # Linear regression lines (extra thick white)
        self._ra_reg_curve = self._plot.plot(
            pen=pg.mkPen(Colors.GRAPH_SPEED_REG, width=3,
                         style=Qt.PenStyle.DashLine),
        )
        self._dec_reg_curve = self._plot.plot(
            pen=pg.mkPen(QColor(255, 200, 200), width=3,
                         style=Qt.PenStyle.DashLine),
        )

        # Zero line
        zero_pen = pg.mkPen(Colors.TEXT_MUTED, width=1,
                            style=Qt.PenStyle.DashLine)
        self._plot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=zero_pen))

        # Watermark
        self._watermark = pg.TextItem(
            text=T("axial_title").split("—")[0].strip(), color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
        )
        self._watermark.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self._watermark.setOpacity(0.15)
        self._plot.addItem(self._watermark)

        # Regression annotation
        self._reg_label = pg.TextItem(
            text='', color=Colors.GRAPH_SPEED_REG, anchor=(1, 0)
        )
        self._reg_label.setFont(QFont('Source Code Pro', 9))
        self._plot.addItem(self._reg_label)

        self._plot.getViewBox().disableAutoRange()
        layout.addWidget(self._plot)

    def update_data(self,
                    ra_raw_t=None, ra_raw_v=None,
                    dec_raw_t=None, dec_raw_v=None,
                    ra_avg_t=None, ra_avg_v=None,
                    dec_avg_t=None, dec_avg_v=None, span_s=None):
        """Update axial graph with speed data.

        All timestamps/values are numpy arrays. With `span_s`, the origin
        is the last sample and the graph scrolls at the present.
        """
        t0 = None
        for t_arr in [ra_raw_t, dec_raw_t, ra_avg_t, dec_avg_t]:
            if t_arr is not None and len(t_arr) > 0:
                if span_s:
                    if t0 is None or t_arr[-1] > t0:
                        t0 = t_arr[-1]
                elif t0 is None or t_arr[0] < t0:
                    t0 = t_arr[0]
        if t0 is None:
            return

        vb = self._plot.getViewBox()
        vb.blockSignals(True)

        # Plot raw speeds
        if ra_raw_t is not None and len(ra_raw_t) > 0:
            self._ra_raw_curve.setData(ra_raw_t - t0, ra_raw_v)
        if dec_raw_t is not None and len(dec_raw_t) > 0:
            self._dec_raw_curve.setData(dec_raw_t - t0, dec_raw_v)

        # Plot averaged speeds
        if ra_avg_t is not None and len(ra_avg_t) > 0:
            self._ra_avg_curve.setData(ra_avg_t - t0, ra_avg_v)
        if dec_avg_t is not None and len(dec_avg_t) > 0:
            self._dec_avg_curve.setData(dec_avg_t - t0, dec_avg_v)

        # Compute linear regression on RA average speed
        reg_parts = []
        if ra_avg_t is not None and len(ra_avg_v) > 10:
            t_rel = ra_avg_t - t0
            try:
                coeffs = np.polyfit(t_rel, ra_avg_v, 1)
                fit_y = np.polyval(coeffs, t_rel)
                self._ra_reg_curve.setData(t_rel, fit_y)
                slope_per_min = coeffs[0] * 60.0
                reg_parts.append(f"RA: {slope_per_min:+.4f}\"/s/min")
            except Exception:
                pass
        else:
            self._ra_reg_curve.setData([], [])

        if dec_avg_t is not None and len(dec_avg_v) > 10:
            t_rel = dec_avg_t - t0
            try:
                coeffs = np.polyfit(t_rel, dec_avg_v, 1)
                fit_y = np.polyval(coeffs, t_rel)
                self._dec_reg_curve.setData(t_rel, fit_y)
                slope_per_min = coeffs[0] * 60.0
                reg_parts.append(f"DEC: {slope_per_min:+.4f}\"/s/min")
            except Exception:
                pass
        else:
            self._dec_reg_curve.setData([], [])

        self._reg_label.setText("  ".join(reg_parts))

        # Manual range management
        all_v = []
        t_end = 0.0
        for t_arr, v_arr in [(ra_raw_t, ra_raw_v), (dec_raw_t, dec_raw_v),
                              (ra_avg_t, ra_avg_v), (dec_avg_t, dec_avg_v)]:
            if t_arr is not None and len(t_arr) > 0:
                all_v.append(v_arr)
                t_end = max(t_end, float((t_arr - t0)[-1]))
        if all_v:
            combined = np.concatenate(all_v)
            y_min = float(np.min(combined))
            y_max = float(np.max(combined))
            y_margin = max(abs(y_max - y_min) * 0.15, 0.01)
            # The axial graph plots several series of different lengths:
            # there is no common point scale to window.
            if span_s:
                x0, x1 = -float(span_s), 0.0
            else:
                x0, x1 = 0.0, max(t_end, 1.0)
            vb.setRange(xRange=(x0, x1),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)

        vb.blockSignals(False)
        match_axes(self._plot)

        # Position overlays
        if all_v:
            self._watermark.setPos((x0 + x1) / 2, 0)
            self._reg_label.setPos(x1, y_max + y_margin)

    def export_to_image(self, directory: str):
        """Export axial graph as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"Axial_{timestamp}.png"
        try:
            export = pg.exporters.ImageExporter(self._plot.plotItem)
            export.parameters()['width'] = 1600
            export.export(str(filename))
            logger.info(f"Axial graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export axial graph: {e}")

    def reset(self):
        """Clear all curves."""
        for curve in [self._ra_raw_curve, self._dec_raw_curve,
                      self._ra_avg_curve, self._dec_avg_curve,
                      self._ra_reg_curve, self._dec_reg_curve]:
            curve.setData([], [])
