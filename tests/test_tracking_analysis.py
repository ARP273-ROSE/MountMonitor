# -*- coding: utf-8 -*-
"""The RMS must describe tracking only — neither the slews nor the drift.

These tests replay a synthetic session whose ground truth is known: two
targets 14.7 deg apart, a jitter of 0.26" RMS and a drift of -5.65"/h. Before
the fix, the report announced a combined RMS of 16,446" and the rating BAD;
the cause was twofold.

1. Segmentation looked for a JUMP between two consecutive samples. A slew is
   a continuous movement: consecutive samples differ by a fraction of a
   degree and no jump is ever seen. Both targets therefore fell into a single
   segment, whose median sat between them.
2. The RMS mixed the slow drift with the jitter. A ramp of amplitude A has a
   standard deviation of A/sqrt(12): over 7 h at -5.65"/h, that alone makes
   12", whereas the same drift moves a star by only 0.28" during a 180 s
   exposure, and every dither cancels it.
"""
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.logging_module.log_parser import parse_dat_file  # noqa: E402

def _require_qt():
    """The report goes through the Qt dialog: without a graphical environment, skip.

    `pytest.importorskip` is not enough: depending on the installation,
    importing Qt raises something other than ImportError (TypeError from
    pyqtgraph, for example).
    """
    try:
        import PyQt6.QtWidgets  # noqa: F401
        import src.gui.analysis_dialog  # noqa: F401
    except Exception as exc:
        pytest.skip(f"Qt environment unavailable: {type(exc).__name__}")


JITTER = 0.26      # arcsec RMS, ground truth
DRIFT = -5.65     # arcsec/h in RA
HZ = 1.68
M31 = (0 + 44 / 60 + 28.8 / 3600, 41 + 26 / 60 + 27.1 / 3600)
M33 = (1 + 35 / 60 + 23.0 / 3600, 30 + 47 / 60 + 56.0 / 3600)


def _hms(h):
    h %= 24
    H = int(h); m = (h - H) * 60; M = int(m)
    return "%02d:%02d:%05.2f" % (H, M, (m - M) * 60)


def _dms(d):
    sg = '+' if d >= 0 else '-'
    d = abs(d); D = int(d); m = (d - D) * 60; M = int(m)
    return "%s%02d:%02d:%05.2f" % (sg, D, M, (m - M) * 60)


def _clock(t):
    t = int(t) % 86400
    return "%02d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60)


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """One night: M 31 for 48 min, a 30 s slew, M 33 for 7 h 20."""
    random.seed(42)
    dt = 1.0 / HZ
    lines = []

    def write(t, ra, dec):
        r, d = _hms(ra), _dms(dec)
        cols = [_clock(t), _clock(t), r, r, "0.150", d, d, "0.200"] + [''] * 6 + \
               [r, r, "0.150", d, d, "0.200", '', '', "0.000", '', '', "0.000", "TRACKING"]
        lines.append("\t".join(cols))

    t = 0.0
    n1 = 4898
    for _ in range(n1):
        dec = M31[1] + random.gauss(0, JITTER) / 3600
        ra = M31[0] + (DRIFT * t / 3600 + random.gauss(0, JITTER)) / 3600 / 15 / math.cos(math.radians(M31[1]))
        write(t, ra, dec); t += dt

    nslew = int(30 * HZ)
    for i in range(nslew):
        f = (i + 1) / nslew
        write(t, M31[0] + (M33[0] - M31[0]) * f, M31[1] + (M33[1] - M31[1]) * f)
        t += dt

    t2 = t
    n2 = int(7 * 3600 * HZ + 20 * 60 * HZ)
    for _ in range(n2):
        dec = M33[1] + random.gauss(0, JITTER) / 3600
        ra = M33[0] + (DRIFT * (t - t2) / 3600 + random.gauss(0, JITTER)) / 3600 / 15 / math.cos(math.radians(M33[1]))
        write(t, ra, dec); t += dt

    header = [
        "MountMonitor mount data file (v.1.9.0)", "Location:\tTest", "Mount:\tGM1000",
        "Mount ID:\t", "Firmware:\t3.20",
        "Telescopes are Unknown of the mount, pointing at azimuth 0.0, altitude 0.0",
        "\t".join(["RAW Mount time", "Mount time", "RAW RA", "RA", "RA StDev",
                   "RAW DEC", "DEC", "DEC StDev"] + ['x'] * 19 + ["Status"]),
    ]
    p = tmp_path_factory.mktemp("mm") / "MountMonitor_20260921-220015.dat"
    p.write_text("\n".join(header + lines) + "\n")
    return parse_dat_file(p)


def test_two_targets_are_separated(session):
    """A continuous slew must split the session, even with no jump between samples."""
    assert len(session.target_segments) == 2


def test_slew_samples_are_discarded(session):
    """They are movement, not tracking: outside the segments."""
    outside = session.tracking_sample_count - session.samples_in_segments
    assert 20 <= outside <= 60, f"{outside} samples discarded, expected ~50"


def test_jitter_recovers_ground_truth(session):
    """0.26\" injected, 0.26\" recovered — within 20 %."""
    for seg in session.target_segments:
        assert np.std(seg.ra_detrended) == pytest.approx(JITTER, rel=0.2)
        assert np.std(seg.dec_detrended) == pytest.approx(JITTER, rel=0.2)


def test_drift_recovers_ground_truth(session):
    for seg in session.target_segments:
        assert seg.ra_drift_arcsec_per_hour == pytest.approx(DRIFT, abs=0.5)
        assert abs(seg.dec_drift_arcsec_per_hour) < 0.5


def test_raw_rms_dominated_by_drift(session):
    """The trap that must never again be mistaken for a tracking error.

    A ramp of amplitude A has a standard deviation of A/sqrt(12).
    """
    long = max(session.target_segments, key=lambda g: g.sample_count)
    duration_h = (long.timestamps[-1] - long.timestamps[0]) / 3600.0
    expected_value = abs(DRIFT) * duration_h / math.sqrt(12)
    assert np.std(long.ra_deviations) == pytest.approx(expected_value, rel=0.15)
    # and it is worth several tens of times the jitter
    assert np.std(long.ra_deviations) > 20 * np.std(long.ra_detrended)


def test_global_rms_stays_below_one_arcsec(session):
    """The figure the rating is based on."""
    combine = math.hypot(float(np.std(session.ra_detrended)),
                         float(np.std(session.dec_detrended)))
    assert combine < 1.0, f"combined RMS {combine:.3f}\", expected < 1\""


def test_drift_masks_periodic_error():
    """A drift is not periodic, but a finite window turns it into a peak.

    MountMonitor exists to find the periodic error of the worm gear. As long
    as the FFT worked on the raw deviations, a 20"/h drift produced a
    "dominant peak" at 198 minutes with 15.8" amplitude, which does not exist,
    and pushed the real PE down to third place.
    """
    rng = np.random.default_rng(7)
    n, fs = 20000, 1.68
    t = np.arange(n) / fs
    period_min, amplitude = 8.0, 1.5
    signal = (20.0 * t / 3600                        # drift 20"/h
              + amplitude * np.sin(2 * np.pi * t / (period_min * 60))
              + rng.normal(0, 0.26, n))

    def dominant_peak(x):
        x = x - np.mean(x)
        w = np.hanning(len(x))
        spectrum = np.abs(np.fft.rfft(x * w))
        freqs = np.fft.rfftfreq(len(x), 1 / fs)
        spectrum[0] = 0.0
        i = int(np.argmax(spectrum))
        return 1 / freqs[i] / 60, 2 * spectrum[i] / np.sum(w)

    # raw: the dominant peak has nothing to do with the PE
    p_raw, _ = dominant_peak(signal)
    assert p_raw > 50, "the test itself is wrong if the drift does not dominate"

    # detrended: the PE comes out on top, at the right period and amplitude
    a, b = np.polyfit(t, signal, 1)
    p_clean, amp_net = dominant_peak(signal - (a * t + b))
    assert p_clean == pytest.approx(period_min, rel=0.05)
    assert amp_net == pytest.approx(amplitude, rel=0.1)


def test_staircase_is_not_jitter():
    """The dither moves the mount and it STAYS there: it is a staircase.

    Removing a straight line does not remove a staircase. On the real
    session of 21/09/2026, it left 9.1" of "jitter" while the mount held each
    step to 0.12". Jitter must therefore be measured BETWEEN the
    repositionings.
    """
    from src.logging_module.log_parser import TargetSegment

    rng = np.random.default_rng(3)
    true_jitter = 0.12
    steps = []
    position = 0.0
    for _ in range(40):                       # 40 exposures
        position += rng.normal(0, 8.0)        # a dither of a few arcseconds
        steps.append(rng.normal(position, true_jitter, 300))
    dev = np.concatenate(steps)

    seg = TargetSegment()
    assert seg.jitter(dev) == pytest.approx(true_jitter, rel=0.25)

    # the raw standard deviation measures the dither's wandering: irrelevant
    assert np.std(dev) > 20 * true_jitter

    # and linear detrending changes almost nothing
    t = np.arange(len(dev), dtype=float)
    a, b = np.polyfit(t, dev, 1)
    assert np.std(dev - (a * t + b)) > 10 * true_jitter


def test_real_session_of_21_september():
    """Non-regression on the file that triggered all this, if present."""
    file = Path(__file__).resolve().parents[1] / "Logs" / "MountMonitor_20260921-220015.dat"
    if not file.exists():
        pytest.skip("reference session missing from the repository")
    s = parse_dat_file(file)
    combine = math.hypot(s.ra_jitter, s.dec_jitter)
    # the original report announced 86.269" and the rating BAD
    assert combine < 0.5, f"jitter {combine:.3f}\", expected < 0.5\""
    assert s.recentrings > 50, "dithers must be seen as such"


def test_replay_graphs_get_same_size_arrays(session):
    """Black screens in replay mode: x and y did not have the same length.

    `timestamps` carries ALL the samples of the file, `ra_deviations` only
    those kept in the segments. On the 21/09/2026 session: 54,047 abscissas
    against 44,604 ordinates. pyqtgraph then draws nothing, and the
    exception went to stderr — invisible in a packaged build, so the console
    announced "REPLAY MODE" and nothing more happened, night report included.
    """
    assert len(session.deviation_timestamps) == len(session.ra_deviations)
    assert len(session.deviation_timestamps) == len(session.dec_deviations)
    assert len(session.deviation_ra_stdevs) == len(session.ra_deviations)
    assert len(session.deviation_dec_stdevs) == len(session.dec_deviations)


def test_night_report_writes_itself(tmp_path):
    """A report you have to remember to export is a report you do not have."""
    _require_qt()
    file = Path(__file__).resolve().parents[1] / "Logs" / "MountMonitor_20260921-220015.dat"
    if not file.exists():
        pytest.skip("reference session missing from the repository")
    copy_path = tmp_path / file.name
    copy_path.write_bytes(file.read_bytes())

    from src.gui.analysis_dialog import save_report

    output = save_report(copy_path, "fr")
    assert output is not None and output.exists()
    text = output.read_text(encoding="utf-8")
    # The report requested in French must be in French. This test used to
    # require "Rating" and "Combined jitter" in a French report: it thus
    # recorded the defect instead of exposing it, and about ten messages
    # did indeed remain in English.
    assert "Note" in text and "Jitter combiné" in text
    assert "Rating" not in text and "Combined jitter" not in text
    assert len(text) > 5000

    # And all three languages are written side by side.
    for language, marker in (("en", "Rating"), ("nl", "Beoordeling")):
        other_value = save_report(copy_path, language)
        assert other_value is not None and other_value.exists()
        assert marker in other_value.read_text(encoding="utf-8")


def test_save_report_never_raises(tmp_path):
    """Losing the report must not prevent the files from closing cleanly."""
    _require_qt()
    from src.gui.analysis_dialog import save_report

    assert save_report(tmp_path / "absent.dat", "fr") is None
    empty = tmp_path / "vide.dat"
    empty.write_text("")
    assert save_report(empty, "fr") is None
