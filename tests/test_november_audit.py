# -*- coding: utf-8 -*-
"""Audit of November 2026: every figure checked against a signal whose truth
is known, plus the connection and buffer defects found the same day.

    python -m pytest -q tests/test_november_audit.py
"""
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.spectrum import spectrum, find_peaks, remove_jumps  # noqa: E402
from src.models.data_buffer import DataBuffer, running_stdev  # noqa: E402
from src.utils.coordinates import parse_ra, parse_dec  # noqa: E402


def _pe(t, amp=1.5, period=480.0):
    return amp * np.sin(2 * np.pi * t / period)


def _main_peak(f, a):
    i = find_peaks(f, a, n=1)[0]
    return 1.0 / f[i], a[i]


# ── Spectrum ─────────────────────────────────────────────────────

def test_peak_amplitude_of_a_sine():
    t = np.arange(0, 4 * 3600, 0.5)
    period, amp = _main_peak(*spectrum(t, _pe(t)))
    assert abs(period - 480) < 10
    assert abs(amp - 1.5) < 0.1          # was 0.67" (Hann window not compensated)


def test_drift_no_longer_masks_pe():
    t = np.arange(0, 4 * 3600, 0.5)
    v = _pe(t) + 20.0 * t / 3600.0      # 20"/h drift
    period, amp = _main_peak(*spectrum(t, v))
    assert abs(period - 480) < 10       # was a 5000 s "peak"
    assert abs(amp - 1.5) < 0.15


def test_dithers_make_no_ghost_peaks():
    rng = np.random.default_rng(1)
    t = np.arange(0, 4 * 3600, 0.5)
    steps = np.repeat(rng.uniform(-4, 4, len(t) // 600 + 1), 600)[:len(t)]
    noise_v = rng.normal(0, 0.05, len(t))
    f, a = spectrum(t, steps + noise_v)
    # No phantom peak where a worm period lives (1 to 60 min): there were
    # 0.84" lines at 18.5, 20 and 10 min. Below 1/h, the noise left at each
    # removed step adds up to a slow wander of a few tenths: harmless.
    band = (f > 1 / 3600.0) & (f < 1 / 60.0)
    assert a[band].max() < 0.15
    period, amp = _main_peak(*spectrum(t, steps + noise_v + _pe(t)))
    assert abs(period - 480) < 10 and abs(amp - 1.5) < 0.2


def test_gap_does_not_skew_period():
    t = np.arange(0, 4 * 3600, 0.5)
    keep = (t < 3600) | (t > 3600 + 2400)        # 40 min gap
    period, _ = _main_peak(*spectrum(t[keep], _pe(t[keep])))
    assert abs(period - 480) < 12               # was 576 s


def test_harmonic_appears_in_peaks():
    t = np.arange(0, 4 * 3600, 0.5)
    f, a = spectrum(t, _pe(t) + _pe(t, 0.5, 240.0))
    periods = sorted(1.0 / f[i] for i in find_peaks(f, a, n=3)[:2])
    assert abs(periods[0] - 240) < 6 and abs(periods[1] - 480) < 10


def test_remove_jumps_keeps_slope():
    v = np.linspace(0, 10, 1000)
    v[500:] += 30.0
    r = remove_jumps(v)
    assert abs((r[-1] - r[0]) - 10.0) < 0.1


# ── Running STDEV ────────────────────────────────────────────────

def _slow_stdev(t, v, w):
    out = np.zeros(len(v))
    for i in range(len(v)):
        m = (t >= t[i] - w) & (t <= t[i])
        if m.sum() > 1:
            out[i] = np.std(v[m], ddof=1)
    return out


def test_running_stdev_vectorised_identical():
    rng = np.random.default_rng(2)
    t = np.cumsum(rng.uniform(0.3, 0.7, 3000))
    v = rng.normal(100.0, 0.3, 3000)          # large mean: precision kept
    assert np.allclose(running_stdev(t, v, 60.0), _slow_stdev(t, v, 60.0), atol=1e-9)


def test_ring_buffer_keeps_most_recent():
    b = DataBuffer(max_size=100)
    for i in range(1000):
        b.append(float(i), float(i))
    t, v = b.get_arrays()
    assert len(t) == 100 and t[0] == 900 and t[-1] == 999
    tt, vv, _, _ = b.get_tail(10)
    assert tt[-1] == 999 and tt[0] <= 989
    b.compute_running_stdev(5)
    assert len(b.get_stdev_array()) == 100


def test_running_stdev_fast():
    t = np.arange(50_000) * 0.1
    v = np.random.default_rng(3).normal(0, 1, 50_000)
    t0 = time.perf_counter()
    running_stdev(t, v, 60.0)
    assert time.perf_counter() - t0 < 0.05    # the Python loop took 50 ms here


# ── Jitter, time, coordinates ────────────────────────────────────

def test_jitter_without_dither_excludes_drift():
    from src.logging_module.log_parser import TargetSegment
    rng = np.random.default_rng(4)
    t = np.arange(0, 4 * 3600, 0.5)
    dev = rng.normal(0, 0.2, len(t)) + 5.0 * t / 3600.0
    j = TargetSegment(ra_deviations=dev, timestamps=t).jitter(dev)
    assert abs(j - 0.2) < 0.03               # was 5.85" with the drift inside


def test_end_of_daylight_saving_on_replay():
    from src.logging_module.log_parser import _unwrap_hours
    # 02:59:58 local, then the clock goes back to 02:00:00
    sec = [2 * 3600 + 59 * 60 + 58, 2 * 3600 + 59 * 60 + 59, 2 * 3600, 2 * 3600 + 1]
    out = _unwrap_hours(sec)
    assert np.all(np.diff(out) > 0) and abs(out[2] - out[1] - 1.0) < 1e-9
    midnight = _unwrap_hours([86399.0, 0.5])
    assert abs(midnight[1] - midnight[0] - 1.5) < 1e-9


def test_short_lx200_formats():
    assert abs(parse_ra("02:44.1") - (2 + 44.1 / 60)) < 1e-9
    assert abs(parse_dec("+61*10") - (61 + 10 / 60)) < 1e-9
    assert abs(parse_dec("-00*30:00") + 0.5) < 1e-9


def test_ascom_time_to_hundredth_and_precision():
    from src.core.ascom_connection import _hours_to_hms, _degrees_to_dms
    assert _hours_to_hms(1.99999999) == "02:00:00.0000"
    assert abs(parse_ra(_hours_to_hms(5.123456789)) - 5.123456789) * 54000 < 0.002
    assert abs(parse_dec(_degrees_to_dms(-12.3456789)) + 12.3456789) * 3600 < 0.001


def test_axial_speed_in_arcseconds():
    from src.core.data_processor import DataProcessor
    from src.models.mount_data import MountSample, MountStatus
    from datetime import datetime
    p = DataProcessor()
    for i, pos in enumerate((10.0, 10.0 + 15.041 / 3600.0)):
        s = MountSample(timestamp=datetime.now(), mount_time_str="", ra_hours=1.0,
                        dec_degrees=10.0, ra_raw_str="", dec_raw_str="",
                        status=MountStatus.TRACKING)
        s.ra_axis_position, s.dec_axis_position = pos, 30.0
        p._process_axial_data(100.0 + i, s)
    assert abs(s.ra_axis_speed - 15.041) < 1e-6      # was 0.0042 "/s


# ── Connection ───────────────────────────────────────────────────

def test_reconnection_never_gives_up():
    from src.core.lx200_protocol import LX200Connection
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    c = LX200Connection(host='127.0.0.1', port=port, timeout=0.5)
    assert not any(c.reconnect() for _ in range(7))
    server = socket.socket(); server.bind(('127.0.0.1', port)); server.listen(1)
    try:
        assert c.reconnect()                  # the mount is back: found again
    finally:
        c.disconnect(); server.close()


def test_precision_set_without_waiting_for_reply():
    """A mount that does not answer :U2# must not cost a timeout nor the link."""
    from src.core.lx200_protocol import LX200Connection
    server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1)
    port = server.getsockname()[1]
    received = []

    def mount():
        conn, _ = server.accept()
        conn.settimeout(3)
        try:
            while True:
                d = conn.recv(64)
                if not d:
                    break
                received.append(d)
                if b':GR#' in d:
                    conn.sendall(b'12:34:56.78#')
        except OSError:
            pass
        conn.close()

    th = threading.Thread(target=mount, daemon=True); th.start()
    c = LX200Connection(host='127.0.0.1', port=port, timeout=2.0)
    t0 = time.monotonic()
    assert c.connect()
    assert time.monotonic() - t0 < 1.0 and c.connected
    assert c.get_ra() == '12:34:56.78'
    c.disconnect(); server.close()
    assert b':U2#' in b''.join(received) and b':U#' not in b''.join(received)


def test_stray_byte_does_not_crash():
    from src.core.lx200_protocol import LX200Connection
    server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1)
    port = server.getsockname()[1]

    def mount():
        conn, _ = server.accept()
        try:
            while True:
                d = conn.recv(64)
                if not d:
                    break
                if b':GR#' in d:
                    conn.sendall(b'12:3\xff4:56#')
        except OSError:
            pass
        conn.close()

    threading.Thread(target=mount, daemon=True).start()
    c = LX200Connection(host='127.0.0.1', port=port, timeout=2.0)
    assert c.connect()
    assert c.get_ra() is not None             # no UnicodeDecodeError
    c.disconnect(); server.close()


def test_seismometer_timestamps_spread():
    from src.core.data_processor import DataProcessor
    t = DataProcessor.seismic_times(100.0, 20)
    assert len(set(t)) == 20 and t[-1] == 100.0 and abs(t[1] - t[0] - 0.05) < 1e-9
