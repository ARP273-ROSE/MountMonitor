# -*- coding: utf-8 -*-
"""A slope, or nothing — but never an exception.

`numpy.polyfit` raises `LinAlgError: SVD did not converge` as soon as the fit
is degenerate: all instants equal, non-finite values, fewer than two distinct
points. It happens for real — a truncated session file, a session fitting
within one second — and it struck in the middle of building the night report,
whose opening is not guarded: the application vanished.

A report that cannot compute a drift must say so, not die.
"""

import logging

import numpy as np

log = logging.getLogger(__name__)


def fit_slope(times, values):
    """Slope of a fitted line, in units of `values` per unit of `times`.

    Returns ``None`` when the question has no answer rather than inventing
    one: it is up to the report text to say "not computable".
    """
    try:
        t = np.asarray(times, dtype=np.float64)
        y = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        return None

    if t.size < 2 or t.size != y.size:
        return None
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(y))):
        return None
    # With no time span, the line is undefined: infinitely many slopes pass
    # through the same instant.
    if float(np.ptp(t)) <= 0:
        return None

    try:
        coefficients = np.polyfit(t, y, 1)
    except (np.linalg.LinAlgError, ValueError, TypeError):
        log.debug("Fit impossible on %d points", t.size, exc_info=True)
        return None

    value = float(coefficients[0])
    return value if np.isfinite(value) else None
