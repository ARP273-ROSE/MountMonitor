"""FFT Analysis window.

Displays frequency and period domain analysis of RA, DEC,
and seismometer data using pyqtgraph.
"""

import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .theme import Colors
from ..utils.i18n import T


def _meaningful_periods(freqs):
    """Mask of the periods worth drawing: positive frequency, and a period
    that fits at least once in the data. The spectrum is zero-padded x4 to
    x8 (src/core/spectrum.py), so its longest periods go up to eight times
    the data span: a smooth plateau that looked like a signal."""
    freqs = np.asarray(freqs)
    positive = freqs > 0
    if not np.any(positive):
        return positive
    longest = 1.0 / float(np.min(freqs[positive])) / 8.0
    return positive & (freqs >= 1.0 / longest)


class FFTWindow(QWidget):
    """Standalone FFT analysis window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("fft_title"))
        self.setMinimumSize(800, 500)
        self.resize(930, 426)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Info bar
        info_layout = QHBoxLayout()
        self._freq_label = QLabel("")
        self._freq_label.setFont(QFont('Source Code Pro', 9))
        self._freq_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        info_layout.addWidget(self._freq_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Splitter: frequency domain (top) and period domain (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Frequency domain graph
        self._freq_plot = pg.PlotWidget(title=T("frequency_domain"))
        self._freq_plot.setBackground(Colors.BG_GRAPH)
        self._freq_plot.showGrid(x=True, y=True, alpha=0.15)
        self._freq_plot.setLabel('bottom', T('frequency_label'), units='Hz')
        self._freq_plot.setLabel('left', T('amplitude_peak'))
        self._freq_plot.addLegend(offset=(10, 10))

        self._freq_ra = self._freq_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_RA, width=1.5), name="RA"
        )
        self._freq_dec = self._freq_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_DEC, width=1.5), name="DEC"
        )
        self._freq_seismic = self._seismic_axis(self._freq_plot, "Seismic")

        # Period domain graph
        self._period_plot = pg.PlotWidget(title=T("period_domain"))
        self._period_plot.setBackground(Colors.BG_GRAPH)
        self._period_plot.showGrid(x=True, y=True, alpha=0.15)
        self._period_plot.setLabel('bottom', T('period_label'), units='s')
        self._period_plot.setLabel('left', T('amplitude_peak'))

        self._period_ra = self._period_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_RA, width=1.5)
        )
        self._period_dec = self._period_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_DEC, width=1.5)
        )
        self._period_seismic = self._seismic_axis(self._period_plot)

        # Thousands of bins every 2 s: draw only what fits on screen.
        for plot in (self._freq_plot, self._period_plot):
            plot.setDownsampling(auto=True, mode='peak')
            plot.setClipToView(True)
            # The vertical scale follows what is shown horizontally, so a
            # zoom on a few peaks rescales to them.
            plot.getViewBox().setAutoVisible(y=True)
            plot.getViewBox().sigRangeChangedManually.connect(self._user_moved)
        # Horizontal range: the whole spectrum of all three curves until the
        # user zooms or pans; the reset button brings it back.
        self._full_x = True

        splitter.addWidget(self._freq_plot)
        splitter.addWidget(self._period_plot)
        layout.addWidget(splitter)

        # Zoom controls
        ctrl_layout = QHBoxLayout()
        for label, slot in [
            ("+", self._zoom_in), ("-", self._zoom_out),
            ("<", self._shift_left), (">", self._shift_right),
            ("\u27f2", self._reset_view),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(40, 28)
            btn.clicked.connect(slot)
            ctrl_layout.addWidget(btn)
        btn.setToolTip(T("tt_fft_reset"))
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

    def _seismic_axis(self, plot, name=None):
        """Seismic curve on its OWN scale (right axis, ADC counts).

        On the arcsecond scale of RA and DEC its counts went far off the
        top of the graph and flattened the two others."""
        pi = plot.getPlotItem()
        vb = pg.ViewBox(enableMouse=False)
        vb.setMenuEnabled(False)
        pi.showAxis('right')
        pi.scene().addItem(vb)
        axis = pi.getAxis('right')
        axis.linkToView(vb)
        axis.setLabel(T("fft_seismic_axis"), color=Colors.GRAPH_SEISMIC.name())
        axis.enableAutoSIPrefix(False)
        vb.setXLink(pi.vb)
        vb.enableAutoRange(axis=pg.ViewBox.YAxis)
        vb.setAutoVisible(y=True)

        def align():
            vb.setGeometry(pi.vb.sceneBoundingRect())
            vb.linkedViewChanged(pi.vb, vb.XAxis)
        pi.vb.sigResized.connect(align)
        curve = pg.PlotDataItem(pen=pg.mkPen(Colors.GRAPH_SEISMIC, width=1))
        curve.setDownsampling(auto=True, method='peak')
        curve.setClipToView(True)
        vb.addItem(curve)
        if name and pi.legend is not None:
            pi.legend.addItem(curve, name)
        return curve

    def update_fft(self, ra_freqs=None, ra_mags=None,
                   dec_freqs=None, dec_mags=None,
                   sei_freqs=None, sei_mags=None,
                   ra_sample_rate=None, dec_sample_rate=None,
                   sei_sample_rate=None):
        """Update FFT graphs with new data."""
        if ra_freqs is not None and len(ra_freqs) > 0:
            self._freq_ra.setData(ra_freqs, ra_mags)
            # Period domain: period = 1/freq (skip freq=0)
            mask = _meaningful_periods(ra_freqs)
            self._period_ra.setData(1.0 / ra_freqs[mask], ra_mags[mask])

        if dec_freqs is not None and len(dec_freqs) > 0:
            self._freq_dec.setData(dec_freqs, dec_mags)
            mask = _meaningful_periods(dec_freqs)
            self._period_dec.setData(1.0 / dec_freqs[mask], dec_mags[mask])

        if sei_freqs is not None and len(sei_freqs) > 0:
            self._freq_seismic.setData(sei_freqs, sei_mags)
            mask = _meaningful_periods(sei_freqs)
            self._period_seismic.setData(1.0 / sei_freqs[mask], sei_mags[mask])

        if self._full_x:
            self._fit_x()

        # Update frequency info
        parts = []
        if ra_sample_rate:
            parts.append(f"RA: {ra_sample_rate:.1f} Hz")
        if dec_sample_rate:
            parts.append(f"DEC: {dec_sample_rate:.1f} Hz")
        if sei_sample_rate:
            parts.append(f"Seismic: {sei_sample_rate:.1f} Hz")
        self._freq_label.setText("  |  ".join(parts))

    def _zoom_in(self):
        self._full_x = False
        self._freq_plot.getViewBox().scaleBy((0.5, 1))
        self._period_plot.getViewBox().scaleBy((0.5, 1))

    def _zoom_out(self):
        self._full_x = False
        self._freq_plot.getViewBox().scaleBy((2, 1))
        self._period_plot.getViewBox().scaleBy((2, 1))

    def _shift_left(self):
        self._full_x = False
        for plot in [self._freq_plot, self._period_plot]:
            vb = plot.getViewBox()
            x_range = vb.viewRange()[0]
            shift = (x_range[1] - x_range[0]) * 0.2
            vb.translateBy((-shift, 0))

    def _shift_right(self):
        self._full_x = False
        for plot in [self._freq_plot, self._period_plot]:
            vb = plot.getViewBox()
            x_range = vb.viewRange()[0]
            shift = (x_range[1] - x_range[0]) * 0.2
            vb.translateBy((shift, 0))

    def _user_moved(self, *_):
        self._full_x = False

    def _fit_x(self):
        """Whole x range of RA and DEC -- the tracking is what this window
        is for; the seismic curve alone when there is nothing else. Its own
        view box is not seen by the plot's auto-range, hence done by hand.
        The seismometer's higher frequencies are one "-" click away."""
        for plot, main, seismic in (
                (self._freq_plot, (self._freq_ra, self._freq_dec), self._freq_seismic),
                (self._period_plot, (self._period_ra, self._period_dec),
                 self._period_seismic)):
            xs = [c.xData for c in main if c.xData is not None and len(c.xData)]
            if not xs and seismic.xData is not None and len(seismic.xData):
                xs = [seismic.xData]
            if xs:
                lo = min(float(np.min(x)) for x in xs)
                hi = max(float(np.max(x)) for x in xs)
                if hi > lo:
                    plot.getViewBox().setXRange(lo, hi, padding=0.02)

    def _reset_view(self):
        """Back to the full horizontal range, vertical scales refitted."""
        self._full_x = True
        self._fit_x()
        for plot in (self._freq_plot, self._period_plot):
            plot.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        for curve in (self._freq_seismic, self._period_seismic):
            vb = curve.getViewBox()
            if vb is not None:
                vb.enableAutoRange(axis=pg.ViewBox.YAxis)

    def export_to_image(self, directory: str):
        """Export FFT graphs as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for plot, name in [(self._freq_plot, "FFT_Freq"), (self._period_plot, "FFT_Period")]:
            filename = dir_path / f"{name}_{timestamp}.png"
            try:
                export = pg.exporters.ImageExporter(plot.plotItem)
                export.parameters()['width'] = 1600
                export.export(str(filename))
                logger.info(f"FFT exported: {filename}")
            except Exception as e:
                logger.warning(f"Failed to export FFT: {e}")

    def reset(self):
        """Clear all FFT data."""
        for curve in [self._freq_ra, self._freq_dec, self._freq_seismic,
                      self._period_ra, self._period_dec, self._period_seismic]:
            curve.setData([], [])
