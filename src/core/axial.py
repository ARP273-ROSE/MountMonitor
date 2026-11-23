"""Axial speeds from the raw axis angles (:GaXa# / :GaXb#), as MountMonitor 3
computes them.

Three series per axis, in arc seconds per second (degrees per hour, the same
number):
- raw: from two consecutive samples. The angle has 4 decimals of a degree
  (0.36"), so at 1 Hz this one is noisy by construction;
- avg: running mean of the last 6 raw speeds;
- reg: slope of a straight line fitted to the angle over the last running
  range (Processing, "Running range"): the steady axis speed, smooth but
  late by about half that range. Until the data cover one range, the fit
  uses everything since the start, and the first 10 values repeat the
  first good one (MM3 fills that gap the same way).

The reference is the median of reg: 15.04"/s on the RA axis of a mount
tracking at the sidereal rate, 0 on the DEC axis, polar error and
refraction set apart.
"""
from typing import Dict, Optional

import numpy as np

#: MM3 default before the first speed is known
RA_DEFAULT_SPEED = 15.02
#: running mean length of the "avg" series (MM3)
AVG_SAMPLES = 6
#: regression values before which the first good one is repeated
MIN_REG_SAMPLES = 10


def unwrap_deg(angle_deg) -> np.ndarray:
    """Angle in degrees with the 0/360 (or -180/180) steps removed."""
    a = np.asarray(angle_deg, dtype=float)
    if len(a) < 2:
        return a.copy()
    d = (np.diff(a) + 180.0) % 360.0 - 180.0
    return np.concatenate(([a[0]], a[0] + np.cumsum(d)))


def axial_speeds(t, angle_deg, range_s: float,
                 default: float = 0.0) -> Optional[Dict[str, np.ndarray]]:
    """raw, avg and reg speeds ("/s) of one axis, one value per sample.

    t in seconds (increasing), angle_deg the raw axis angle. Samples
    sharing a time stamp keep the previous raw speed (MM3)."""
    t = np.asarray(t, dtype=float)
    y = unwrap_deg(angle_deg) * 3600.0          # arcsec
    n = min(len(t), len(y))
    if n < 2:
        return None
    t, y = t[:n] - t[0], y[:n] - y[0]           # centred: no precision loss

    raw = np.empty(n)
    raw[0] = default
    dt = np.diff(t)
    dy = np.diff(y)
    for i in range(1, n):
        raw[i] = dy[i - 1] / dt[i - 1] if dt[i - 1] > 0 else raw[i - 1]
    if n > 1:
        raw[0] = raw[1]

    # running mean of the last AVG_SAMPLES raw speeds
    c = np.concatenate(([0.0], np.cumsum(raw)))
    k = np.arange(1, n + 1)
    lo = np.maximum(k - AVG_SAMPLES, 0)
    avg = (c[k] - c[lo]) / (k - lo)

    # least-squares slope over [start_i, i], start_i = the latest sample at
    # least range_s older than i (none yet: the first one)
    st = np.searchsorted(t, t - float(range_s), side="right") - 1
    st = np.maximum(st, 0)
    s1 = np.concatenate(([0.0], np.cumsum(t)))
    s2 = np.concatenate(([0.0], np.cumsum(t * t)))
    sy = np.concatenate(([0.0], np.cumsum(y)))
    sty = np.concatenate(([0.0], np.cumsum(t * y)))
    e = np.arange(1, n + 1)
    m = (e - st).astype(float)
    St, Stt = s1[e] - s1[st], s2[e] - s2[st]
    Sy, Sty = sy[e] - sy[st], sty[e] - sty[st]
    den = m * Stt - St * St
    with np.errstate(invalid="ignore", divide="ignore"):
        reg = np.where((m >= 3) & (den > 0), (m * Sty - St * Sy) / den, np.nan)
    good = np.flatnonzero(~np.isnan(reg))
    if len(good) > MIN_REG_SAMPLES:
        first = good[MIN_REG_SAMPLES]
        reg[:first] = reg[first]
    else:
        reg[:] = np.nan
    # fits that already span a whole running range (the earlier ones,
    # on a few samples, wander -- MM3 warns about the first range)
    full = (t - t[st]) >= float(range_s) * 0.999
    return {"t": t, "raw": raw, "avg": avg, "reg": reg, "full": full}


def median_speed(reg, full=None) -> Optional[float]:
    """Reference speed: median of the regression speeds, of the fits over
    a whole running range when there are any."""
    r = np.asarray(reg, dtype=float)
    ok = ~np.isnan(r)
    if full is not None and np.any(ok & np.asarray(full)):
        ok &= np.asarray(full)
    r = r[ok]
    return float(np.median(r)) if len(r) else None


def displacement(t, reg, ref: float, start: int = 0) -> np.ndarray:
    """Integral of (regression speed - reference) from index `start`, in
    arc seconds: how far the axis has run ahead of (or behind) a steady
    motion at the reference speed. NaN before `start` or where the speed is
    not known yet. MountMonitor 3's "axial displacement"."""
    t = np.asarray(t, dtype=float)
    v = np.asarray(reg, dtype=float) - float(ref)
    out = np.full(len(t), np.nan)
    ok = np.flatnonzero(~np.isnan(v))
    ok = ok[ok >= start]
    if len(ok) < 2:
        return out
    i0 = ok[0]
    tt, vv = t[i0:], np.nan_to_num(v[i0:])
    steps = np.diff(tt) * (vv[1:] + vv[:-1]) / 2.0
    out[i0:] = np.concatenate(([0.0], np.cumsum(steps)))
    return out
