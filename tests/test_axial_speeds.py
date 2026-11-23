"""Axial speeds as MountMonitor 3 computes them (linear regression over the
running range)."""
import numpy as np

from src.core.axial import axial_speeds, displacement, median_speed, unwrap_deg

SIDEREAL = 15.041067  # "/s


def _track(n=600, hz=2.0, speed=SIDEREAL, start=359.99, noise=True):
    t = np.arange(n) / hz
    a = start + speed * t / 3600.0
    a = (a + 180.0) % 360.0 - 180.0             # wraps like the mount
    if noise:
        a = np.round(a, 4)                      # :GaXa# has 4 decimals
    return t, a


def test_regression_recovers_sidereal_through_quantisation():
    t, a = _track()
    s = axial_speeds(t, a, range_s=60)
    # raw is noisy by 0.36" steps, the regression is not
    assert np.std(s["raw"][1:]) > 0.2
    assert abs(median_speed(s["reg"]) - SIDEREAL) < 0.01
    assert np.all(np.abs(s["reg"][200:] - SIDEREAL) < 0.02)


def test_wrap_does_not_spike():
    t, a = _track(noise=False)
    s = axial_speeds(t, a, range_s=60)
    assert np.all(np.abs(s["raw"] - SIDEREAL) < 1e-6)


def test_dec_axis_and_same_timestamps():
    t = np.array([0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14], float)
    a = np.zeros_like(t)
    s = axial_speeds(t, a, range_s=60)
    assert np.all(s["raw"] == 0)
    assert median_speed(s["reg"]) == 0


def test_too_short():
    assert axial_speeds([0.0], [1.0], 60) is None
    s = axial_speeds(np.arange(5.0), np.zeros(5), 60)
    assert median_speed(s["reg"]) is None


def test_unwrap():
    assert np.allclose(unwrap_deg([179.9, -179.9]), [179.9, 180.1])


def test_axial_graph_draws_both_axes_on_one_scale():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.gui.graph_widgets import AxialGraph
    t, a = _track()
    ra = axial_speeds(t, a, 60, 15.02)
    dec = axial_speeds(t, np.round(np.full_like(t, 45.0), 4), 60)
    ra["t"] = ra["t"] - ra["t"][-1]
    dec["t"] = dec["t"] - dec["t"][-1]
    g = AxialGraph()
    g.update_data(ra=ra, dec=dec, span_s=120)
    x, y = g._ra_reg_curve.getData()
    assert abs(np.nanmedian(y)) < 0.01           # drawn relative to its reference
    assert "RA 15.04" in g._reg_label.text and "median 15.04" in g._reg_label.text
    (x0, x1), (y0, y1) = g._plot.getViewBox().viewRange()
    assert (x0, x1) == (-120, 0) and y1 - y0 < 0.5  # scaled on the regression
    g.update_data(ra=ra, dec=dec, span_s=120, mode="displacement", dec_deg=60)
    assert "sky" in g._reg_label.text
    x, y = g._ra_reg_curve.getData()
    assert x[0] >= -120.5 and abs(np.mean(y)) < 1e-9   # integrated over the view, around its mean
    g.reset()


def test_displacement_is_the_integral_of_the_speed_excess():
    t = np.arange(0, 100.0)
    reg = np.full_like(t, 15.0)
    reg[50:] = 15.1                              # 0.1"/s faster for 50 s
    d = displacement(t, reg, 15.0)
    assert d[0] == 0 and abs(d[-1] - 0.1 * 49.5) < 1e-9
    reg[:10] = np.nan
    d = displacement(t, reg, 15.0, start=20)
    assert np.all(np.isnan(d[:20])) and d[20] == 0
