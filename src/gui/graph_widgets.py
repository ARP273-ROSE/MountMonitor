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
        useOpenGL=False,
    )


_setup_pyqtgraph()



def accorder_les_axes(plot):
    """Recopie la plage du repere sur les graduations.

    Les graphes changent leur plage pendant que les signaux du repere sont
    bloques — c'est voulu, pour eviter une cascade de recalculs a chaque
    rafraichissement. Mais c'est precisement ce signal qui previent les axes :
    bloque, il les laisse sur la plage qu'ils avaient a leur creation,
    c'est-a-dire [0, 1].

    Resultat : les courbes bougeaient, la graduation restait figee de zero a
    un. Un graphe montrant quarante secondes de donnees etait gradue « 0,2 ;
    0,4 ; 0,6 » avec « Time (s) » dessous — et le deplacement en secondes
    d'arc se lisait sur une echelle tout aussi fausse. On ne pouvait
    litteralement rien lire d'exact sur ces graphes.

    Verifie a la mesure : `axe.range` valait [0, 1] alors que la vue portait
    sur [0 ; 39,46].
    """
    vue = plot.getViewBox()
    (x0, x1), (y0, y1) = vue.viewRange()
    plot.getAxis('bottom').setRange(x0, x1)
    plot.getAxis('left').setRange(y0, y1)


def fenetre_horizontale(widget, rel_times, t_end, zoom):
    """Debut de la plage affichee, selon le zoom horizontal.

    Reprend la regle du MountMonitor Java : au zoom 1, un point de donnee
    occupe un pixel, donc l'ecran montre autant de points qu'il a de pixels
    de large ; au zoom 5, chaque point occupe cinq pixels, et l'on voit donc
    cinq fois moins de donnees — mais en detail.

    Le menu « Zoom horizontal » existait et ne faisait rien : le reglage
    etait enregistre, jamais applique.

    🔴 La regle vaut AUSSI au zoom 1. Une premiere version rendait 0.0 dans
    ce cas — donc le debut du tampon — et le zoom 1 etant le defaut, les
    courbes ne defilaient plus du tout : l'axe partait de zero et s'etirait
    a mesure que la nuit avancait, tassant les donnees au milieu. Sur une
    session de sept heures l'axe atteignait 26 ks et l'ecart-type affiche
    montait a 1960 arcsec, alors que la monture tenait a 0,06.
    """
    try:
        zoom = max(1, int(zoom))
    except (TypeError, ValueError):
        zoom = 1
    if len(rel_times) == 0:
        return 0.0
    largeur = max(200, int(widget.width()))
    points_visibles = max(10, largeur // zoom)
    if len(rel_times) <= points_visibles:
        return 0.0
    return float(rel_times[-points_visibles])


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

        # Create plot widget — disable auto-range to prevent signal cascades
        self._plot = pg.PlotWidget()
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(title, color=data_color.name(), size='11pt')
        self._plot.setLabel('left', T('deviation'), units='"', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s', color=Colors.TEXT_SECONDARY.name())
        self._plot.getViewBox().disableAutoRange()

        # Data line
        pen = pg.mkPen(color=data_color, width=1.5)
        self._data_curve = self._plot.plot(pen=pen, name=title)

        # STDEV line (plotted on main axis — avoids dual-ViewBox signal loops)
        stdev_pen = pg.mkPen(color=Colors.GRAPH_STDEV, width=1.5)
        self._stdev_curve = self._plot.plot(pen=stdev_pen)

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
        self._plot.addItem(self._max_stdev_line)
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
        self._plot.addItem(self._max_stdev_label)
        self._max_stdev_label.setVisible(False)

        # Stats text overlay
        self._stats_text = pg.TextItem(
            text='', color=Colors.TEXT_SECONDARY,
            anchor=(1, 0)
        )
        self._stats_text.setFont(QFont('Consolas', 9))
        self._plot.addItem(self._stats_text)

        # Tolerance value annotations (labels showing the arcsec value)
        self._tol_upper_label = pg.TextItem(
            text='', color=Colors.GRAPH_TOLERANCE, anchor=(1, 1)
        )
        self._tol_upper_label.setFont(QFont('Consolas', 8))
        self._plot.addItem(self._tol_upper_label)

        self._tol_lower_label = pg.TextItem(
            text='', color=Colors.GRAPH_TOLERANCE, anchor=(1, 0)
        )
        self._tol_lower_label.setFont(QFont('Consolas', 8))
        self._plot.addItem(self._tol_lower_label)

        # Time fix markers (grey vertical lines every 30s)
        # Pool a fixed max number to avoid unbounded growth over long sessions
        self._time_fixes = []
        self._time_fix_labels = []
        self._MAX_TIME_FIXES = 40  # Max visible at once; recycle pool
        # Cache pen/font objects — avoid recreating every refresh
        self._fix_pen = pg.mkPen(Colors.TEXT_MUTED, width=1, style=Qt.PenStyle.DotLine)
        self._fix_label_font = QFont('Consolas', 7)

        layout.addWidget(self._plot)

    def update_data(self, timestamps: np.ndarray, values: np.ndarray,
                    stdev_values: np.ndarray = None,
                    stdev_timestamps: np.ndarray = None,
                    min_val: float = None, max_val: float = None,
                    max_stdev: float = None,
                    mount_times: list = None):
        """Update graph with new data.

        Manages range manually to avoid sigRangeChanged cascades.
        """
        if len(timestamps) == 0:
            return

        # Normalize timestamps to relative seconds
        t0 = timestamps[0]
        rel_times = timestamps - t0
        t_end = rel_times[-1]

        # Block signals during batch update to prevent cascades
        vb = self._plot.getViewBox()
        vb.blockSignals(True)

        self._data_curve.setData(rel_times, values)

        # Update STDEV (with optional corrected timestamps)
        if stdev_values is not None and len(stdev_values) == len(rel_times):
            if stdev_timestamps is not None:
                stdev_rel = stdev_timestamps - t0
                self._stdev_curve.setData(stdev_rel, stdev_values)
            else:
                self._stdev_curve.setData(rel_times, stdev_values)

        # Update min/max lines with annotations
        if min_val is not None and max_val is not None:
            self._min_line.setPos(min_val)
            self._max_line.setPos(max_val)
            self._min_line.setVisible(True)
            self._max_line.setVisible(True)
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

        # Manually set range (replaces auto-range)
        y_min = float(np.min(values))
        y_max = float(np.max(values))
        margin = max(abs(y_min), abs(y_max), self._tolerance) * 1.3
        x0 = fenetre_horizontale(self, rel_times, t_end,
                                 getattr(self, '_zoom_horizontal', 1))
        vb.setRange(xRange=(x0, max(t_end, x0 + 1.0)),
                    yRange=(-margin, margin), padding=0)
        vb.blockSignals(False)
        accorder_les_axes(self._plot)

        # Position overlays after range is set
        x_right = max(t_end, 1.0)
        self._watermark.setPos(t_end / 2, 0)
        self._stats_text.setPos(x_right, margin)
        self._tol_upper_label.setPos(x_right, self._tolerance)
        self._tol_lower_label.setPos(x_right, -self._tolerance)

    def set_tolerance(self, arcsec: float):
        """Update tolerance lines and their annotations (only if changed)."""
        if arcsec == self._tolerance:
            return
        self._tolerance = arcsec
        self._tol_upper.setPos(arcsec)
        self._tol_lower.setPos(-arcsec)
        self._tol_upper_label.setText(f'{arcsec:+.2f}"')
        self._tol_lower_label.setText(f'{-arcsec:+.2f}"')

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
        """Draw grey vertical lines every 30 seconds with time labels.

        Uses a fixed-size pool of plot items to avoid unbounded growth.
        Only shows marks within the visible time range.
        """
        if len(rel_times) == 0:
            return

        t_max = rel_times[-1]

        # Determine visible range — show last portion only for long sessions
        vr = self._plot.getViewBox().viewRange()
        x_min = max(0.0, vr[0][0]) if vr else 0.0
        x_max = vr[0][1] if vr else t_max
        y_top = vr[1][1] if vr else 0

        # Compute which 30s marks fall in visible range
        first_mark = max(1, int(x_min / 30.0) + 1)
        last_mark = int(min(t_max, x_max) / 30.0)
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
                mark_idx = visible_marks[i]
                t = 30.0 * mark_idx
                self._time_fixes[i].setPos(t)
                self._time_fixes[i].setVisible(True)

                # Time label
                m, s = divmod(int(t), 60)
                h, m = divmod(m, 60)
                if h > 0:
                    label_text = f"{h}:{m:02d}:{s:02d}"
                else:
                    label_text = f"{m:02d}:{s:02d}"

                self._time_fix_labels[i].setText(label_text)
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
        self._plot.setBackground(Colors.BG_GRAPH)
        self._plot.showGrid(x=False, y=True, alpha=0.1)
        self._plot.setTitle(T("time_graph_title"), color='#aaaaaa', size='11pt')
        self._plot.setLabel('left', T('time_diff'), units='ms', color=Colors.TEXT_SECONDARY.name())
        self._plot.setLabel('bottom', T('time_label'), units='s', color=Colors.TEXT_SECONDARY.name())
        # pyqtgraph choisit tout seul un prefixe et le colle devant l'unite.
        # Sur une unite deja prefixee comme « ms », cela donnait « mms » —
        # milli-millisecondes — et une graduation sans rapport avec les
        # valeurs affichees dans la legende, qui sont en millisecondes. Sur
        # cet axe, les millisecondes sont le bon ordre de grandeur : on garde
        # l'unite telle quelle.
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
            text=T("time_graph"), color=Colors.TEXT_MUTED, anchor=(0.5, 0.5)
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
        self._plot.getViewBox().disableAutoRange()

        layout.addWidget(self._plot)

    def update_data(self, diff_t, diff_v, pc_loop_t=None, pc_loop_v=None,
                    mount_loop_t=None, mount_loop_v=None,
                    ntp_t=None, ntp_v=None):
        """Update time graph data."""
        if len(diff_t) > 0:
            t0 = diff_t[0]
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
            x0 = fenetre_horizontale(self, rel_t, t_end,
                                     getattr(self, '_zoom_horizontal', 1))
            vb.setRange(xRange=(x0, max(t_end, x0 + 1.0)),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)
            vb.blockSignals(False)
            accorder_les_axes(self._plot)

            # Position overlays
            self._values_text.setPos(max(t_end, 1.0), y_max + y_margin)
            self._watermark.setPos(t_end / 2, (y_min + y_max) / 2)

            # Values + drift rate annotation
            parts = []
            if len(diff_v) > 0:
                parts.append(f"PC-Mount: {diff_v[-1]:+.1f}ms")
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
        self._plot.setTitle(T("seismic_title"), color='#aaaaaa', size='11pt')
        self._plot.setLabel('left', T('amplitude'), color=Colors.TEXT_SECONDARY.name())
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
                    stdev_values: np.ndarray = None):
        """Update seismic graph."""
        if len(timestamps) > 0:
            t0 = timestamps[0]
            vb = self._plot.getViewBox()
            vb.blockSignals(True)

            rel_t = timestamps - t0
            self._data_curve.setData(rel_t, values)
            if stdev_values is not None and len(stdev_values) == len(timestamps):
                self._stdev_curve.setData(rel_t, stdev_values)

            # Manual range
            t_end = float(rel_t[-1])
            y_min = float(np.min(values))
            y_max = float(np.max(values))
            y_margin = max(abs(y_max - y_min) * 0.15, 1.0)
            x0 = fenetre_horizontale(self, rel_t, t_end,
                                     getattr(self, '_zoom_horizontal', 1))
            vb.setRange(xRange=(x0, max(t_end, x0 + 1.0)),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)
            vb.blockSignals(False)
            accorder_les_axes(self._plot)

            # Position watermark
            self._watermark.setPos(t_end / 2, (y_min + y_max) / 2)

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
        self._reg_label.setFont(QFont('Consolas', 9))
        self._plot.addItem(self._reg_label)

        self._plot.getViewBox().disableAutoRange()
        layout.addWidget(self._plot)

    def update_data(self,
                    ra_raw_t=None, ra_raw_v=None,
                    dec_raw_t=None, dec_raw_v=None,
                    ra_avg_t=None, ra_avg_v=None,
                    dec_avg_t=None, dec_avg_v=None):
        """Update axial graph with speed data.

        All timestamps/values are numpy arrays.
        """
        # Determine t0 from first available data
        t0 = None
        for t_arr in [ra_raw_t, dec_raw_t, ra_avg_t, dec_avg_t]:
            if t_arr is not None and len(t_arr) > 0:
                if t0 is None or t_arr[0] < t0:
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
            # Le graphe axial trace plusieurs series de longueurs differentes :
            # il n'y a pas d'echelle de points commune a fenetrer.
            x0 = 0.0
            vb.setRange(xRange=(x0, max(t_end, x0 + 1.0)),
                        yRange=(y_min - y_margin, y_max + y_margin), padding=0)

        vb.blockSignals(False)
        accorder_les_axes(self._plot)

        # Position overlays
        self._watermark.setPos(t_end / 2, 0)
        if all_v:
            self._reg_label.setPos(max(t_end, 1.0), y_max + y_margin)

    def export_to_image(self, directory: str):
        """Export axial graph as PNG."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = dir_path / f"Axial_{timestamp}.png"
        try:
            exporter = pg.exporters.ImageExporter(self._plot.plotItem)
            exporter.parameters()['width'] = 1600
            exporter.export(str(filename))
            logger.info(f"Axial graph exported: {filename}")
        except Exception as e:
            logger.warning(f"Failed to export axial graph: {e}")

    def reset(self):
        """Clear all curves."""
        for curve in [self._ra_raw_curve, self._dec_raw_curve,
                      self._ra_avg_curve, self._dec_avg_curve,
                      self._ra_reg_curve, self._dec_reg_curve]:
            curve.setData([], [])
