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


def retirer_sauts(v: np.ndarray, facteur: float = 8.0) -> np.ndarray:
    """Remove instantaneous jumps (dithers, recentrings) from a staircase.

    A jump is a step between two samples larger than `facteur` times the
    median step: the same robust threshold as the night report's plateaus."""
    if len(v) < 3:
        return v
    d = np.diff(v)
    seuil = facteur * float(np.median(np.abs(d))) + 1e-12
    d = np.where(np.abs(d) > seuil, 0.0, d)
    return np.concatenate(([v[0]], v[0] + np.cumsum(d)))


def bloc_contigu(t: np.ndarray, v: np.ndarray, facteur_trou: float = 5.0):
    """Longest stretch without a gap (gap = step > facteur_trou x median step)."""
    if len(t) < 2:
        return t, v
    dt = np.diff(t)
    pas = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.0
    if pas <= 0:
        return t[:0], v[:0]
    coupures = np.where((dt > facteur_trou * pas) | (dt <= 0))[0]
    bornes = np.concatenate(([0], coupures + 1, [len(t)]))
    k = int(np.argmax(np.diff(bornes)))
    return t[bornes[k]:bornes[k + 1]], v[bornes[k]:bornes[k + 1]]


def spectre(t, v, enlever_sauts: bool = True):
    """(frequencies Hz, amplitudes in the unit of v, PEAK), DC removed.

    t in seconds (any origin), v the deviation. Empty arrays when there is
    not enough data."""
    vide = (np.array([]), np.array([]))
    t = np.asarray(t, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    if len(t) != len(v) or len(t) < MIN_POINTS:
        return vide
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    t, v = bloc_contigu(t, v)
    if len(t) < MIN_POINTS:
        return vide
    pas = float(np.median(np.diff(t)))
    if pas <= 0:
        return vide
    n = int((t[-1] - t[0]) / pas) + 1
    if n < MIN_POINTS:
        return vide
    grille = t[0] + pas * np.arange(n)
    x = np.interp(grille, t, v)
    if enlever_sauts:
        x = retirer_sauts(x)
    # Drift: remove the best straight line.
    a, b = np.polyfit(grille - grille[0], x, 1)
    x = x - (a * (grille - grille[0]) + b)
    w = np.hanning(n)
    # Zero-padding x4: finer frequency grid, so a period between two bins
    # (480 s on an 8400 s stretch falls between 494 and 467 s) and its
    # amplitude (Hann scalloping, up to -15 %) are read correctly. The
    # amplitude scaling 2/sum(w) is unchanged by padding.
    npad = 1 << int(np.ceil(np.log2(4 * n)))
    amp = 2.0 * np.abs(np.fft.rfft(x * w, n=npad)) / w.sum()
    f = np.fft.rfftfreq(npad, d=pas)
    return f[1:], amp[1:]


def spectre_regulier(v, frequence_hz: float, enlever_sauts: bool = False):
    """Spectrum of an evenly sampled series (seismometer)."""
    if frequence_hz <= 0 or len(v) < MIN_POINTS:
        return np.array([]), np.array([])
    t = np.arange(len(v)) / float(frequence_hz)
    return spectre(t, v, enlever_sauts=enlever_sauts)


def pics(freqs, amps, n: int = 3, exclusion: int = 12):
    """Indices of the n highest LOCAL maxima, `exclusion` bins apart.

    Sorting every bin returned the main peak and its two neighbours
    (8.0, 7.7, 8.3 min) and hid the real second line (harmonic)."""
    amps = np.asarray(amps)
    if len(amps) < 3:
        return list(np.argsort(amps)[::-1][:n])
    locaux = np.where((amps[1:-1] >= amps[:-2]) & (amps[1:-1] > amps[2:]))[0] + 1
    if amps[0] > amps[1]:
        locaux = np.concatenate(([0], locaux))
    ordre = locaux[np.argsort(amps[locaux])[::-1]]
    retenus = []
    for i in ordre:
        if all(abs(int(i) - j) > exclusion for j in retenus):
            retenus.append(int(i))
            if len(retenus) == n:
                break
    return retenus
