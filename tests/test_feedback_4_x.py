# -*- coding: utf-8 -*-
"""Feedback on 4.1.0 (19/11/2026): displayed duration, vertical scale,
right panel, clock drift, armed button."""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gui.graph_widgets import (clock_drift, shown_span,  # noqa: E402
                                   span_name, tick_spacing,
                                   vertical_range, SPANS_S)


def test_half_hour_and_one_hour_offered():
    assert 1800 in SPANS_S and 3600 in SPANS_S
    assert shown_span(1800) == 1800.0
    assert shown_span(None) == 120.0
    assert shown_span("x") == 120.0
    assert shown_span(-5) == 120.0
    assert span_name(1800) == "30 min" and span_name(30) == "30 s"


def test_hour_ticks_readable_over_one_hour():
    for span in SPANS_S:
        assert span / tick_spacing(span) <= 10
    assert tick_spacing(120) == 30


def test_data_scale_ignores_tolerance():
    v = np.array([0.02, -0.03, 0.05, 0.0])
    low, high = vertical_range("data", v, tolerance=0.25)
    assert high < 0.25 and low > -0.25          # tolerance lines off the frame
    assert low <= v.min() and high >= v.max()
    low, high = vertical_range("tolerance", v, tolerance=0.25)
    assert high == pytest.approx(0.3)
    low, high = vertical_range("maximum", v, tolerance=0.25)
    assert high >= 0.25
    low, high = vertical_range("minmax", v, 0.25, min_val=-0.4, max_val=0.1)
    assert high == pytest.approx(0.48)


def test_data_scale_constant_values():
    low, high = vertical_range("data", np.zeros(10), tolerance=1.0)
    assert high - low > 0


def test_drift_stable_despite_noise_and_spikes():
    rng = np.random.default_rng(1)
    t = np.arange(0, 2400, 0.5)
    v = -10 + 12.0 * t / 3600 + rng.normal(0, 15, len(t))   # 12 ms/h
    v[::97] += 600                                          # slow loops
    d = [clock_drift(t[:n], v[:n]) for n in range(3600, len(t), 7)]
    assert all(abs(x - 12.0) < 5 for x in d)
    # from one sample to the next, the value no longer jumps
    assert max(abs(a - b) for a, b in zip(d, d[1:])) < 1.0


def test_no_drift_without_enough_data():
    t = np.arange(0, 60, 0.5)
    assert clock_drift(t, t * 0) is None


@pytest.fixture
def window(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.main_window import MainWindow
    w = MainWindow()
    monkeypatch.setattr(w._settings, "save", lambda: None)   # not the real file
    yield w
    w.close()
    app.processEvents()


def test_graph_menu_and_applied_scale(window):
    from src.gui.graph_widgets import TrackingGraph
    w = window
    assert not w._ra_graph._plot.plotItem.getViewBox().menuEnabled()
    w._set_vertical_zoom("data")
    t = np.arange(0, 300, 0.5) + 1e6
    v = 0.03 * np.sin(t)
    w._ra_graph.set_tolerance(0.25)
    w._ra_graph.update_data(t, v, span_s=120)
    (_, _), (y0, y1) = w._ra_graph._plot.getViewBox().viewRange()
    assert y1 < 0.25
    w._set_span(1800)
    assert w._span() == 1800.0


def test_armed_button_says_it_waits_for_night(window, monkeypatch):
    from src.models.mount_data import MountStatus
    from src.utils.i18n import T
    w = window
    w._prev_mount_status = MountStatus.TRACKING
    monkeypatch.setattr(w, "_is_daytime", lambda: True)
    monkeypatch.setattr(w, "_start_logging", lambda: None)
    w._arm()
    assert w._logging_armed
    assert w._btn_logging.text() == T("btn_armed_night")
    w._disarm()
    assert w._btn_logging.text() == T("btn_start_log")


def test_right_panel_history_expandable(window):
    from PyQt6.QtWidgets import QSizePolicy
    p = window._status_panel
    assert p._log_text.maximumHeight() > 10000
    from PyQt6.QtWidgets import QFrame
    frame = p.findChild(QFrame, "values")
    assert frame.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed


def test_files_written_to_disk_every_5_s(tmp_path, monkeypatch):
    from src.logging_module import file_logger as fl
    calls = []
    monkeypatch.setattr(fl.os, "fsync", lambda fd: calls.append(fd))
    lg = fl.FileLogger.__new__(fl.FileLogger)
    f = open(tmp_path / "x.dat", "w")
    for name in ("_log_file", "_dti_file", "_sei_file", "_fft_file", "_env_file"):
        setattr(lg, name, None)
    lg._dat_file = f
    lg._write_count, lg._flush_interval = 0, 20
    lg._last_flush = fl.time.monotonic() - 6
    assert lg._safe_write(f, "a\n")
    assert calls, "no forced write to disk after 5 s"
    f.close()


def test_auto_options_on_first_tab_and_right_click(window, monkeypatch):
    from src.gui.preferences_dialog import PreferencesDialog
    from src.utils.i18n import T
    from PyQt6.QtWidgets import QGroupBox
    d = PreferencesDialog(window._settings, window)
    titles = [g.title() for g in d.findChildren(QGroupBox)]
    assert T("pref_unattended") in titles
    d.close()
    # "Night only" unticked in broad daylight, mount tracking: immediate start
    from src.models.mount_data import MountStatus
    w = window
    w._prev_mount_status = MountStatus.TRACKING
    started_calls = []
    monkeypatch.setattr(w, "_start_logging", lambda: started_calls.append(1))
    monkeypatch.setattr(w._settings, "set", lambda k, v: None)
    day = {"v": True}
    monkeypatch.setattr(w, "_is_daytime", lambda: day["v"])
    w._arm()
    assert not started_calls
    day["v"] = False
    w._auto_option("close_at_sunrise", False)
    assert started_calls


# ── Feedback of 20/11/2026 (comparison with MM3) ───────────────────────────

def test_stdev_scale_mm3_rule():
    from src.gui.graph_widgets import stdev_scale
    assert stdev_scale(0.3) == (1.0, 0.2)        # log10(0.99) -> 0
    high, step = stdev_scale(0.04)                # log10(0.132) -> -1
    assert high == pytest.approx(0.1) and step == pytest.approx(0.02)
    assert stdev_scale(1.6)[0] == 10.0
    for sd in (0.001, 0.02, 0.13, 0.31, 0.95, 2.9, 40.0):
        assert stdev_scale(sd)[0] >= sd          # the curve always fits
    assert stdev_scale(0)[0] > 0


def test_deviations_centred_on_visible_median():
    from src.core.data_processor import deviations_from_median
    v = np.linspace(10.0, 10.0 + 20 / 54000, 101)       # drift of 20" in RA
    e = deviations_from_median(v, 54000.0, 24.0)
    assert np.median(e) == pytest.approx(0.0, abs=1e-9)
    assert e[0] == pytest.approx(-10.0) and e[-1] == pytest.approx(10.0)
    # crossing 0 h: no 24 h jump
    w = np.array([23.99999, 0.00001, 0.00002])
    assert np.ptp(deviations_from_median(w, 3600.0, 24.0)) < 0.2


def test_seismometer_line_cr_lf_or_alone():
    from src.core.seismometer import line_value, _EOL
    lines = _EOL.split(b"512\r\n498\n503\r-12,5\rX\r")
    vals = [line_value(l) for l in lines]
    assert vals[:4] == [512.0, 498.0, 503.0, -12.5]
    assert line_value(b"abc") is None


def test_refraction_mode_read_by_wsg(monkeypatch):
    from src.core.lx200_protocol import LX200Connection
    c = LX200Connection.__new__(LX200Connection)
    sent = []
    def send(cmd, fixed_len=None):
        sent.append(cmd)
        return {":WSG#": "2", ":GREF#": "1"}[cmd]
    monkeypatch.setattr(c, "_send_command", send)
    assert c.get_refraction_mode() == "continuously_updating"
    assert c.is_refraction_enabled() is True
    assert sent == [":WSG#", ":GREF#"]


def test_checks_in_mm3_order_with_separate_refraction(window):
    from src.gui.preferences_dialog import PreferencesDialog
    from src.utils.i18n import T
    from PyQt6.QtWidgets import QCheckBox
    d = PreferencesDialog(window._settings, window)
    expected_values = [T(k) for k in ("check_refr_status_label", "check_refraction_label",
                               "check_gps_label", "check_dual_label", "check_tracking_label")]
    grid = d._check_refr_status.parentWidget().layout()
    order = []
    for line in range(1, grid.rowCount()):
        it = grid.itemAtPosition(line, 0)
        if it and isinstance(it.widget(), QCheckBox):
            order.append(it.widget().text())
    assert order[:5] == expected_values
    d.close()
    # refraction correction off: a single warning, not the mode
    w = window
    msgs = []
    w._status_panel.add_message = lambda m, c=None: msgs.append(m)
    w._judge_checks({"refraction": False, "mode": "not_updating"}, True)
    assert any(T("chk_refr_status_ko").split("{")[0] in m for m in msgs)
    assert not any("not updating" in m for m in msgs)


def test_ra_in_time_seconds_or_arcseconds(window, monkeypatch):
    w = window
    vals = {"ra_in_degrees": False, "tolerance_ra_arcsec": 1.5}
    orig = w._settings.get
    monkeypatch.setattr(w._settings, "get", lambda k: vals.get(k, orig(k)))
    assert w._displayed_ra_tolerance() == pytest.approx(0.1)
    vals["ra_in_degrees"] = True
    assert w._displayed_ra_tolerance() == pytest.approx(1.5)


def test_green_curve_on_top_in_time_graph(window):
    g = window._time_graph
    assert g._pc_loop_curve.zValue() > max(g._mount_loop_curve.zValue(), g._diff_curve.zValue())


# ── Feedback of 20/11/2026 evening (4.3.0 on his mount) ────────────────────

def test_solar_rate_no_longer_taken_for_sidereal():
    from src.core.mount_connection import classify_tracking_rate
    assert classify_tracking_rate("60.2") == "sidereal"
    assert classify_tracking_rate("60.3") == "solar"          # used to pass for sidereal
    assert classify_tracking_rate("62.4#") == "lunar"
    assert classify_tracking_rate("Solar") == "solar"         # ASCOM
    assert classify_tracking_rate("59.1") is None
    assert classify_tracking_rate(None) is None


def test_rate_alert_once_and_history_without_repeats(window, monkeypatch):
    from src.utils.i18n import T
    w = window
    vals = {"check_tracking_rate": True, "check_tracking_rate_value": "sidereal",
            "check_refraction_status": False, "check_refraction_enabled": False,
            "check_gps_sync": False, "check_dual_tracking": False, "mount_alert_popup": True}
    orig = w._settings.get
    monkeypatch.setattr(w._settings, "get", lambda k: vals.get(k, orig(k)))
    msgs = []
    w._status_panel.add_message = lambda m, c=None: msgs.append(m)
    for _ in range(3):                                  # periodic check
        w._judge_checks({"rate": "60.3"}, True)
    assert sum(T("val_solar") in m for m in msgs) == 1  # one line, not three
    box = w._alert_box
    assert box.isVisible() and T("val_solar") in box.text()
    w._judge_checks({"rate": "60.2"}, True)          # corrected on the keypad
    assert not box.isVisible()


def test_seismometer_centred_like_mm3():
    from src.core.seismometer import Seismometer
    s = Seismometer(offset=300)
    received_list = []
    s.set_callback(lambda t, v: received_list.extend(v))

    class Port:
        def __init__(self):
            self.data = [b"-354\r\n-344\r\n-256\r\n"]
            self.in_waiting = 0
        def read(self, n):
            s._running = bool(self.data) and s._running
            return self.data.pop(0) if self.data else b""
    s._serial = Port()
    s._running = True
    s._read_loop()
    assert s.get_recent_data(3) == [-54.0, -44.0, 44.0]


def test_graphs_right_aligned(window):
    from src.gui.graph_widgets import RIGHT_AXIS_WIDTH, LEFT_AXIS_WIDTH
    for g in (window._ra_graph, window._dec_graph, window._time_graph, window._seismic_graph):
        pi = g._plot.getPlotItem()
        assert pi.getAxis('right').fixedWidth == RIGHT_AXIS_WIDTH
        assert pi.getAxis('left').fixedWidth == LEFT_AXIS_WIDTH


# ── Feedback of 20/11/2026 night: time graph as in MM3 ───────────────────

def test_loop_times_centred_on_their_average(window):
    from src.gui.graph_widgets import loop_average
    assert loop_average([990.0, 1010.0], [1000.0, 1000.0]) == pytest.approx(1000.0)
    assert loop_average(None, []) == 0.0
    g = window._time_graph
    t = np.arange(0, 120, 1.0) + 1e6
    g.update_data(t, -300 + 0 * t, t, 1000 + np.sin(t) * 20, t, 1000 + np.cos(t) * 40,
                  span_s=120)
    y = g._pc_loop_curve.yData           # raw data, before clipping
    assert abs(float(np.mean(y))) < 10                  # centred, not at 1000
    assert g._right_axis.offset == pytest.approx(1000.0, abs=5)
    assert g._right_axis.tickStrings([0.0, 100.0], 1, 1) == ["1000", "1100"]
    (_, _), (y0, y1) = g._plot.getViewBox().viewRange()
    assert y1 - y0 < 600                                # no 1300 ms stretch


# ── Feedback of 20/11/2026 night: checks made the link time out ──────────

def _fake_mount(replies):
    """A socket pair whose far end answers each command like a 10Micron."""
    import socket, threading
    a, b = socket.socketpair()

    def serve():
        buf = b""
        while True:
            try:
                data = b.recv(1024)
            except OSError:
                return
            if not data:
                return
            buf += data
            while b"#" in buf:
                cmd, buf = buf.split(b"#", 1)
                b.sendall(replies[cmd.decode() + "#"])
    threading.Thread(target=serve, daemon=True).start()
    return a, b


def test_commands_without_hash_do_not_time_out():
    import threading, time
    from src.core.lx200_protocol import LX200Connection
    a, b = _fake_mount({":GREF#": b"1", ":Gdat#": b"0", ":GT#": b"60.3#",
                        ":GVN#": b"3.2.5#", ":gtgpps#": b"1#", ":Gstat#": b"0#"})
    a.settimeout(2.0)
    c = LX200Connection.__new__(LX200Connection)
    c._socket, c._connected, c._io_lock = a, True, threading.RLock()
    t = time.monotonic()
    assert c.is_refraction_enabled() is True
    assert c.is_dual_tracking_enabled() is False
    assert c.get_tracking_rate() == "60.3"          # no stray "1" in front
    c.get_firmware_version()
    assert c.is_gps_synced() is True                # :gtgpps# on 3.2.5
    assert c._connected and time.monotonic() - t < 1.0
    a.close(); b.close()


def test_stray_bytes_are_dropped_before_the_next_command():
    import threading
    from src.core.lx200_protocol import LX200Connection
    a, b = _fake_mount({":GT#": b"60.2#"})
    a.settimeout(2.0)
    c = LX200Connection.__new__(LX200Connection)
    c._socket, c._connected, c._io_lock = a, True, threading.RLock()
    b.sendall(b"1")                                  # late answer of an old query
    import time; time.sleep(0.1)
    assert c.get_tracking_rate() == "60.2"
    a.close(); b.close()
