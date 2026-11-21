"""Spectrum of a tracking error: one implementation for the live window,
the replay, the .fft file and the night report.

What it corrects, each measured on a synthetic signal of known truth:

- amplitude: a Hann window divides the amplitude of a sine by two; the
  scaling is 2/sum(w), not 2/n (1.5" peak read as 0.67").
- drift: a slow drift is not periodic, but a finite window turns it into a
  huge low-frequency peak that hid the worm period (5000 s peak instead of
  the 480 s one). A straight line is removed.
- dithers: the signal is a STAIRCASE (the mount stays on each new step);
  the steps make phantom peaks (18.5 min, 10 min...). Jumps are removed
  before the transform.
- gaps: a session with a pause has no single sampling rate; counting
  samples over the whole span gave periods 20 % too long. The transform
  uses the longest stretch without a gap, on a uniform time grid.
"""
import numpy as np

MIN_POINTS = 64


def remove_jumps(v: np.ndarray, factor: float = 8.0) -> np.ndarray:
    """Remove instantaneous jumps (dithers, recentrings) from a staircase.

    A jump is a step between two samples larger than `factor` times the
    median NON-ZERO step. The median of all steps was zero on a quantised
    axis (declination read in 0.1" units moves on few samples): every move
    then counted as a jump and the whole signal was flattened to zero --
    the empty DEC spectrum reported by N. de Hilster."""
    if len(v) < 3:
        return v
    d = np.diff(v)
    moves = np.abs(d[d != 0])
    if len(moves) == 0:
        return v
    threshold = factor * float(np.median(moves))
    d = np.where(np.abs(d) > threshold, 0.0, d)
    return np.concatenate(([v[0]], v[0] + np.cumsum(d)))


def contiguous_block(t: np.ndarray, v: np.ndarray, gap_factor: float = 5.0):
    """Longest stretch without a gap (gap = step > facteur_trou x median step)."""
    if len(t) < 2:
        return t, v
    dt = np.diff(t)
    step = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.0
    if step <= 0:
        return t[:0], v[:0]
    breaks = np.where((dt > gap_factor * step) | (dt <= 0))[0]
    bounds = np.concatenate(([0], breaks + 1, [len(t)]))
    k = int(np.argmax(np.diff(bounds)))
    return t[bounds[k]:bounds[k + 1]], v[bounds[k]:bounds[k + 1]]


def spectrum(t, v, remove_steps: bool = True):
    """(frequencies Hz, amplitudes in the unit of v, PEAK), DC removed.

    t in seconds (any origin), v the deviation. Empty arrays when there is
    not enough data."""
    empty = (np.array([]), np.array([]))
    t = np.asarray(t, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    if len(t) != len(v) or len(t) < MIN_POINTS:
        return empty
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    t, v = contiguous_block(t, v)
    if len(t) < MIN_POINTS:
        return empty
    step = float(np.median(np.diff(t)))
    if step <= 0:
        return empty
    n = int((t[-1] - t[0]) / step) + 1
    if n < MIN_POINTS:
        return empty
    grid = t[0] + step * np.arange(n)
    x = np.interp(grid, t, v)
    if remove_steps:
        x = remove_jumps(x)
    # Drift: remove the best straight line.
    a, b = np.polyfit(grid - grid[0], x, 1)
    x = x - (a * (grid - grid[0]) + b)
    w = np.hanning(n)
    # Zero-padding x4: finer frequency grid, so a period between two bins
    # (480 s on an 8400 s stretch falls between 494 and 467 s) and its
    # amplitude (Hann scalloping, up to -15 %) are read correctly. The
    # amplitude scaling 2/sum(w) is unchanged by padding.
    npad = 1 << int(np.ceil(np.log2(4 * n)))
    amp = 2.0 * np.abs(np.fft.rfft(x * w, n=npad)) / w.sum()
    f = np.fft.rfftfreq(npad, d=step)
    return f[1:], amp[1:]


def regular_spectrum(v, frequency_hz: float, remove_steps: bool = False):
    """Spectrum of an evenly sampled series (seismometer)."""
    if frequency_hz <= 0 or len(v) < MIN_POINTS:
        return np.array([]), np.array([])
    t = np.arange(len(v)) / float(frequency_hz)
    return spectrum(t, v, remove_steps=remove_steps)


def find_peaks(freqs, amps, n: int = 3, exclusion: int = 12):
    """Indices of the n highest LOCAL maxima, `exclusion` bins apart.

    Sorting every bin returned the main peak and its two neighbours
    (8.0, 7.7, 8.3 min) and hid the real second line (harmonic)."""
    amps = np.asarray(amps)
    if len(amps) < 3:
        return list(np.argsort(amps)[::-1][:n])
    local_max = np.where((amps[1:-1] >= amps[:-2]) & (amps[1:-1] > amps[2:]))[0] + 1
    if amps[0] > amps[1]:
        local_max = np.concatenate(([0], local_max))
    order = local_max[np.argsort(amps[local_max])[::-1]]
    kept = []
    for i in order:
        if all(abs(int(i) - j) > exclusion for j in kept):
            kept.append(int(i))
            if len(kept) == n:
                break
    return kept
