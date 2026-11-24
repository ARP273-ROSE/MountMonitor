"""Remarks of the MM3 author on 4.5.4 (24/11/2026)."""
from pathlib import Path
import pytest

from tests.test_feedback_4_x import window  # noqa: F401  (fixture)


def test_axial_off_in_pure_ascom(window):
    w = window
    s = w._settings
    s.set("axial_mode", "velocity")
    s.set("mount_protocol", "lx200")
    assert w._axial_mode() == "velocity"
    s.set("mount_protocol", "ascom")
    s.set("ascom_10micron_commands", False)
    assert w._axial_mode() == "off"            # chosen before switching: ignored
    s.set("ascom_10micron_commands", True)
    assert w._axial_mode() == "velocity"


def test_preferences_grey_axial_and_reopen_last_tab(window):
    from src.gui.preferences_dialog import PreferencesDialog
    s = window._settings
    s.set("mount_protocol", "lx200")
    s.set("preferences_tab", 2)
    d = PreferencesDialog(s)
    assert d._tabs.currentIndex() == 2
    assert d._axial_mode.isEnabled()
    d._protocol.setCurrentIndex(2)               # ASCOM
    d._ascom_10micron.setChecked(False)
    assert not d._axial_mode.isEnabled()
    d._ascom_10micron.setChecked(True)
    assert d._axial_mode.isEnabled()
    d._tabs.setCurrentIndex(1)
    assert s.get("preferences_tab") == 1
    d.close()


def test_graphs_ignore_wheel_and_dumps_keep_colours(window, tmp_path):
    w = window
    vb = w._ra_graph._plot.getViewBox()
    assert vb.state["mouseEnabled"] == [False, False]
    g = w._ra_graph
    g.set_tracking(False)
    seen = []
    import pyqtgraph.exporters as ex
    orig = ex.ImageExporter.export
    try:
        ex.ImageExporter.export = lambda self, f=None: seen.append(g._tracking)
        g.export_to_image(str(tmp_path))
    finally:
        ex.ImageExporter.export = orig
    assert seen == [True] and g._tracking is False


def test_update_offer_is_modeless_and_ownerless():
    """24/11/2026: a modal update dialog owned by the window, hidden at an
    unattended start, left the window unusable."""
    src = (Path(__file__).resolve().parent.parent / 'src' / 'gui' / 'main_window.py').read_text(encoding='utf-8')
    body = src.split('def _show_update_dialog', 1)[1].split('\n    def ', 1)[0]
    assert 'QDialog(None)' in body and 'dlg.exec()' not in body and 'dlg.show()' in body
    close = src.split('def closeEvent', 1)[1].split('\n    def ', 1)[0]
    assert '_update_offer' in close


def test_unattended_second_instance_shows_no_box():
    src = (Path(__file__).resolve().parent.parent / 'main.py').read_text(encoding='utf-8')
    block = src.split('if not _lock_file.tryLock(_wait_ms):', 1)[1].split('app._instance_lock', 1)[0]
    assert block.index('args.connect') < block.index('QMessageBox')


def test_update_offer_returns_at_once(window):
    window._show_update_dialog({"version": "9.9.9", "notes": "x", "size": 0})
    dlg = window._update_offer
    assert dlg is not None and dlg.isVisible() and not dlg.isModal()
    assert dlg.parent() is None and window.isEnabled()
    dlg.reject()
    assert window._update_offer is None


def test_menus_tidied(window):
    from PyQt6.QtWidgets import QPushButton, QToolBar
    from src.utils.i18n import T
    titles = [a.text() for a in window.menuBar().actions()]
    assert titles == [T("menu_file"), T("menu_view"), T("menu_language"), T("menu_help")]
    file_menu = window.menuBar().actions()[0].menu()
    texts = [a.text() for a in file_menu.actions() if a.text()]
    assert T("menu_preferences") in texts and T("btn_connect") in texts
    assert T("btn_disconnect") in texts and T("dump_graphs_action") in texts
    for bar in window.findChildren(QToolBar):
        assert T("menu_preferences") not in [b.text() for b in bar.findChildren(QPushButton)]


def test_fft_span_same_window_for_all_series(window, monkeypatch):
    """Nicolas, 24/11: over the whole buffer the mount spectrum covered hours
    and the seismometer's 41 min. The chosen span applies to all three."""
    import numpy as np, time as _t
    p = window._processor
    for b in (p.ra_buffer, p.dec_buffer, p.seismic_buffer):
        b.clear() if hasattr(b, "clear") else None
    t0 = 1_000_000.0
    for i in range(7200):                    # 1 h at 2 Hz
        p.ra_buffer.append(t0 + i / 2.0, np.sin(i / 50.0))
        p.dec_buffer.append(t0 + i / 2.0, np.cos(i / 50.0))
    for i in range(20 * 1200):               # 20 min at 20 Hz
        p.seismic_buffer.append(t0 + i / 20.0, np.sin(i / 7.0))
    window._settings.set("fft_span_min", 10)
    got = {}
    window.fft_computed.disconnect()
    window.fft_computed.connect(lambda r: got.update(r))
    window._logging_active = True
    window._update_fft()
    window._fft_job.join(10)
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    d = got["durations"]
    assert abs(d["ra"] - 600) < 2 and abs(d["sei"] - 600) < 2


def test_period_curve_increasing_and_thinned_by_period():
    """Vertical bars and sawtooth in the period domain (N. de Hilster,
    24/11/2026, 30 min at 2 Hz): 1/f was handed to pyqtgraph backwards
    and thinned by equal point counts."""
    import numpy as np
    from src.core.spectrum import spectrum
    from src.gui.fft_window import _period_curve
    t = np.arange(0, 1740, 0.5)
    v = 0.3 * np.sin(2 * np.pi * t / 480) + 0.02 * np.random.default_rng(1).normal(size=len(t))
    f, a = spectrum(t, v)
    p, m = _period_curve(f, a)
    assert np.all(np.diff(p) > 0)
    assert len(p) <= 3000
    assert abs(p[np.argmax(m)] - 480) < 25
    # the long periods are kept point by point, not merged into bars
    long_f = f[(f > 0) & (1 / f > 300) & (1 / f <= p[-1])]
    assert np.sum(p > 300) == len(long_f)
    # seismometer-sized spectrum: thinned, peak preserved
    f2 = np.linspace(1e-4, 10, 131072)
    a2 = np.zeros_like(f2); a2[5000] = 1.0
    p2, m2 = _period_curve(f2, a2)
    assert len(p2) <= 3000 and m2.max() == 1.0


def test_period_plot_not_auto_downsampled(window):
    from src.gui.fft_window import FFTWindow
    w = FFTWindow()
    for c in (w._period_ra, w._period_dec):
        assert not c.opts.get('autoDownsample')
        assert not c.opts.get('clipToView')
    assert w._freq_ra.opts.get('autoDownsample')
    from PyQt6.QtWidgets import QApplication
    w.close()
    w.deleteLater()
    QApplication.processEvents()
