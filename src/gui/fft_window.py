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
        self._freq_label.setFont(QFont("Consolas", 9))
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
        self._freq_plot.setLabel('left', T('amplitude'))
        self._freq_plot.addLegend(offset=(10, 10))

        self._freq_ra = self._freq_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_RA, width=1.5), name="RA"
        )
        self._freq_dec = self._freq_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_DEC, width=1.5), name="DEC"
        )
        self._freq_seismic = self._freq_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_SEISMIC, width=1), name="Seismic"
        )

        # Period domain graph
        self._period_plot = pg.PlotWidget(title=T("period_domain"))
        self._period_plot.setBackground(Colors.BG_GRAPH)
        self._period_plot.showGrid(x=True, y=True, alpha=0.15)
        self._period_plot.setLabel('bottom', T('period_label'), units='s')
        self._period_plot.setLabel('left', T('amplitude'))

        self._period_ra = self._period_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_RA, width=1.5)
        )
        self._period_dec = self._period_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_DEC, width=1.5)
        )
        self._period_seismic = self._period_plot.plot(
            pen=pg.mkPen(Colors.GRAPH_SEISMIC, width=1)
        )

        splitter.addWidget(self._freq_plot)
        splitter.addWidget(self._period_plot)
        layout.addWidget(splitter)

        # Zoom controls
        ctrl_layout = QHBoxLayout()
        for label, slot in [
            ("+", self._zoom_in), ("-", self._zoom_out),
            ("<", self._shift_left), (">", self._shift_right),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(40, 28)
            btn.clicked.connect(slot)
            ctrl_layout.addWidget(btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

    def update_fft(self, ra_freqs=None, ra_mags=None,
                   dec_freqs=None, dec_mags=None,
                   sei_freqs=None, sei_mags=None,
                   ra_sample_rate=None, dec_sample_rate=None,
                   sei_sample_rate=None):
        """Update FFT graphs with new data."""
        if ra_freqs is not None and len(ra_freqs) > 0:
            self._freq_ra.setData(ra_freqs, ra_mags)
            # Period domain: period = 1/freq (skip freq=0)
            mask = ra_freqs > 0
            self._period_ra.setData(1.0 / ra_freqs[mask], ra_mags[mask])

        if dec_freqs is not None and len(dec_freqs) > 0:
            self._freq_dec.setData(dec_freqs, dec_mags)
            mask = dec_freqs > 0
            self._period_dec.setData(1.0 / dec_freqs[mask], dec_mags[mask])

        if sei_freqs is not None and len(sei_freqs) > 0:
            self._freq_seismic.setData(sei_freqs, sei_mags)
            mask = sei_freqs > 0
            self._period_seismic.setData(1.0 / sei_freqs[mask], sei_mags[mask])

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
        self._freq_plot.getViewBox().scaleBy((0.5, 1))
        self._period_plot.getViewBox().scaleBy((0.5, 1))

    def _zoom_out(self):
        self._freq_plot.getViewBox().scaleBy((2, 1))
        self._period_plot.getViewBox().scaleBy((2, 1))

    def _shift_left(self):
        for plot in [self._freq_plot, self._period_plot]:
            vb = plot.getViewBox()
            x_range = vb.viewRange()[0]
            shift = (x_range[1] - x_range[0]) * 0.2
            vb.translateBy((-shift, 0))

    def _shift_right(self):
        for plot in [self._freq_plot, self._period_plot]:
            vb = plot.getViewBox()
            x_range = vb.viewRange()[0]
            shift = (x_range[1] - x_range[0]) * 0.2
            vb.translateBy((shift, 0))

    def export_to_image(self, directory: str):
        """Export FFT graphs as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for plot, name in [(self._freq_plot, "FFT_Freq"), (self._period_plot, "FFT_Period")]:
            filename = dir_path / f"{name}_{timestamp}.png"
            try:
                exporter = pg.exporters.ImageExporter(plot.plotItem)
                exporter.parameters()['width'] = 1600
                exporter.export(str(filename))
                logger.info(f"FFT exported: {filename}")
            except Exception as e:
                logger.warning(f"Failed to export FFT: {e}")

    def reset(self):
        """Clear all FFT data."""
        for curve in [self._freq_ra, self._freq_dec, self._freq_seismic,
                      self._period_ra, self._period_dec, self._period_seismic]:
            curve.setData([], [])
