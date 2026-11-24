"""Audit of 24/11/2026: freezes, long runs, small PCs."""
from tests.test_feedback_4_x import window  # noqa: F401,E402  (fixture)
import numpy as np

from src.models.data_buffer import DataBuffer


def test_clock_set_back_restarts_the_series():
    b = DataBuffer(1000)
    for i in range(100):
        b.append(10_000.0 + i, float(i))
    b.append(10_099.5, 1.0)                 # jitter: kept in order
    t, _ = b.get_arrays()
    assert np.all(np.diff(t) >= 0)
    b.append(10_099.0 - 3600, 2.0)          # clock set back one hour
    t, v = b.get_arrays()
    assert len(t) == 1 and v[0] == 2.0
    assert b.get_minmax()[1] >= 99 if hasattr(b, "get_minmax") else True


def test_log_files_that_cannot_be_created_are_said(tmp_path):
    from src.logging_module.file_logger import FileLogger
    from src.models.mount_data import SessionInfo
    blocked = tmp_path / "file"
    blocked.write_text("x")                 # a file where the folder should be
    lg = FileLogger(base_dir=blocked)
    assert lg.start_session(SessionInfo()) is False
    assert lg.write_error
    ok = FileLogger(base_dir=tmp_path)
    assert ok.start_session(SessionInfo()) is True
    ok.close()


def test_same_exception_reported_once(tmp_path, monkeypatch):
    from src.logging_module.crash_reporter import CrashReporter
    import reporting
    sent = []
    monkeypatch.setattr(reporting, "signaler_plantage", lambda txt: sent.append(txt))
    c = CrashReporter(tmp_path)
    monkeypatch.setattr(c, "_original_excepthook", lambda *a: None)
    for _ in range(50):
        try:
            raise OSError("disk full")
        except OSError as e:
            c._handle_exception(type(e), e, e.__traceback__)
    assert len(sent) == 1


def test_curves_drawn_at_two_points_per_pixel_and_dense_without_antialias():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.graph_widgets import TrackingGraph, DOWNSAMPLE_FACTOR
    from src.gui.theme import Colors
    g = TrackingGraph("RA", Colors.GRAPH_RA)
    g.resize(800, 300); g.show(); app.processEvents()
    assert g._data_curve.opts["autoDownsampleFactor"] == DOWNSAMPLE_FACTOR == 1.0
    t = np.arange(-3600.0, 0.0, 0.5) + 1e9
    v = np.random.default_rng(1).normal(0, 0.3, len(t))
    g.update_data(t, v, span_s=3600)
    assert g._data_curve.curve.opts["antialias"] is False
    g.update_data(t[-200:], v[-200:], span_s=120)
    assert g._data_curve.curve.opts["antialias"] is True
    g.close()


def test_fft_computed_off_the_gui_thread(window):
    from PyQt6.QtWidgets import QApplication
    w = window
    p = w._processor
    t0 = 1.9e9
    for i in range(600):
        p.ra_buffer.append(t0 + i, np.sin(i / 8.0))
        p.dec_buffer.append(t0 + i, np.cos(i / 5.0))
    w._show_fft()
    w._update_fft()
    w._fft_job.join(10)
    for _ in range(5):
        QApplication.processEvents()
    x, y = w._fft_window._freq_ra.getData()
    assert x is not None and len(x) > 10


def test_disconnect_does_not_wait_for_a_busy_driver(window):
    import time as _t
    from src.core.poller import MountPoller
    w = window

    class Busy(MountPoller):
        def run(self):
            while self._running:
                _t.sleep(0.05)
            _t.sleep(3.0)                    # a driver call that will not return

    p = Busy(connection=None, processor=None)
    p._running = True
    p.start()
    a = _t.perf_counter()
    w._release_poller(p)
    assert _t.perf_counter() - a < 0.3
    assert p in w._finishing_pollers
    p.wait(5000)
