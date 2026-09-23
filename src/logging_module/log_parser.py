"""Log file parser for MountMonitor.

Parses .dat (27-column mount data) and .dti (time data) files
to reconstruct session data for replay and analysis.

Filters TRACKING-only data and segments by target for accurate analysis.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Target-change detection ────────────────────────────────────────────────
# A target change is detected on the angular separation from the CURRENT target
# position, never on the jump between two consecutive samples: a slew is a
# continuous motion, so consecutive samples differ by a fraction of a degree
# and no jump is ever large enough to be seen. Before this was fixed, a whole
# night on two targets was parsed as ONE segment whose median fell between them,
# giving deviations of several degrees and a meaningless RMS.
_TARGET_CHANGE_ARCSEC = 300.0     # 5 arcmin from the target = new target
_MIN_SEGMENT_SAMPLES = 20         # Minimum samples to consider a segment valid
_REF_WINDOW = 256                 # samples used to refresh the reference position
_STDEV_SETTLE_S = 60.0            # running-STDEV window: see _settled_stdevs()
_FUSION_S = 10.0                  # crossings closer than this are one move
_FENETRE_APRES = 60               # samples examined after a move
_MARGE_MOUVEMENT = 2              # samples dropped after a move, see jitter()
_DELAI_APRES_SLEW = 5.0           # seconds ignored when tracking resumes

# ── Excursion rejection inside a segment ──────────────────────────────────
# Dithers, re-centering slews and autofocus moves happen WHILE the mount still
# reports TRACKING. They are real mount motion, but they are commanded, not
# tracking error: including them makes the RMS describe the sequencer, not the
# mount. They are excluded from the statistics and counted separately.
_EXCURSION_ARCSEC = 30.0


@dataclass
class TargetSegment:
    """A segment of tracking data on a single target."""
    start_index: int = 0
    end_index: int = 0
    ra_median_hours: float = 0.0
    dec_median_degrees: float = 0.0
    sample_count: int = 0
    ra_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    # Deviation from the position the mount is actually holding (drift and
    # repositioning steps taken out). This -- not the raw deviation -- is what
    # blurs a frame, and it is the basis the jitter and the rating use.
    ra_residual: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_residual: np.ndarray = field(default_factory=lambda: np.array([]))
    # Observing site, read back from the header: decimal degrees, longitude
    # positive east. Needed on replay, when the mount is long gone.
    mouvements: list = field(default_factory=list)
    site_lat: float | None = None
    site_lon: float | None = None
    site_elev: float | None = None
    start_iso: object = None
    excursions_removed: int = 0       # dithers / re-centering excluded from stats
    excursion_max_arcsec: float = 0.0 # largest excursion seen, for the report
    mouvements: list = field(default_factory=list)   # see _mouvements()

    def _paliers(self, dev: np.ndarray) -> np.ndarray:
        """Indices where the mount was repositioned (dither, re-centering).

        Between two exposures the sequencer moves the mount and it STAYS there:
        the deviation is a staircase, not a noisy line. Removing a straight line
        does not remove a staircase, so the step heights end up counted as
        tracking error — on a real session they reached 9.7" while the mount was
        actually holding each step to 0.09".
        """
        if len(dev) < 8:
            return np.array([], dtype=int)
        d = np.abs(np.diff(np.asarray(dev, dtype=np.float64)))
        # Robust noise scale: most samples are inside a step, so the median
        # absolute difference describes the noise, not the steps.
        ech = float(np.median(d))
        seuil = max(8.0 * ech, 0.5)
        return np.flatnonzero(d > seuil) + 1

    def jitter(self, dev: np.ndarray) -> float:
        """Tracking jitter: the spread the mount shows WHILE it holds a position.

        This is the only figure that blurs an exposure. Anything slower — drift,
        dithers, re-centering — either does not move the star during the frame or
        is cancelled between frames.
        """
        dev = np.asarray(dev, dtype=np.float64)
        if len(dev) < 8:
            return float(np.std(dev)) if len(dev) else 0.0
        bords = np.concatenate(([0], self._paliers(dev), [len(dev)]))
        # Drop a couple of samples after each step: the move itself is not
        # tracking error and must not count as one. Measured on the
        # 2026-09-22 session the effect is small -- RA unchanged, DEC 5%
        # lower at most -- which is the point: the figure must not depend on
        # how often the sequencer dithers.
        morceaux = [dev[a + _MARGE_MOUVEMENT:b] if a > 0 else dev[a:b]
                    for a, b in zip(bords[:-1], bords[1:])
                    if b - a - (_MARGE_MOUVEMENT if a > 0 else 0) >= 8]
        if not morceaux:
            return float(np.std(dev))
        # Median of the per-step spreads: robust to the few steps that contain
        # the tail of a move.
        return float(np.median([np.std(m) for m in morceaux]))

    @property
    def ra_jitter(self) -> float:
        return self.jitter(self.ra_deviations)

    @property
    def dec_jitter(self) -> float:
        return self.jitter(self.dec_deviations)

    @property
    def repositionnements(self) -> int:
        """How many times the sequencer moved the mount during this segment."""
        ra = set(self._paliers(self.ra_deviations).tolist())
        dec = set(self._paliers(self.dec_deviations).tolist())
        # a dither moves both axes: merge indices closer than 3 samples
        tous = sorted(ra | dec)
        n = 0
        prec = -10
        for i in tous:
            if i - prec > 3:
                n += 1
            prec = i
        return n

    @property
    def amplitude_repositionnement(self) -> float:
        """Median size of those moves, in arcsec."""
        idx = sorted(set(self._paliers(self.ra_deviations).tolist())
                     | set(self._paliers(self.dec_deviations).tolist()))
        if not idx:
            return 0.0
        sauts = []
        for i in idx:
            if 0 < i < len(self.ra_deviations):
                sauts.append(float(np.hypot(
                    self.ra_deviations[i] - self.ra_deviations[i - 1],
                    self.dec_deviations[i] - self.dec_deviations[i - 1])))
        return float(np.median(sauts)) if sauts else 0.0

    def _detrended(self, dev: np.ndarray) -> tuple[np.ndarray, float]:
        """Deviations with the linear drift removed, and that drift in "/h.

        Slow drift and short-term jitter do not have the same consequence: a
        drift of 5"/h moves a star by 0.25" during a 3-minute exposure and is
        cancelled by every dither, while jitter blurs each exposure directly.
        Reporting a single RMS mixing the two describes neither.
        """
        if len(dev) < 2 or len(self.timestamps) != len(dev):
            return dev, 0.0
        t = np.asarray(self.timestamps, dtype=np.float64)
        t = t - t[0]
        if float(np.ptp(t)) <= 0:
            return dev, 0.0
        try:
            a, b = np.polyfit(t, np.asarray(dev, dtype=np.float64), 1)
        except (np.linalg.LinAlgError, ValueError):
            return dev, 0.0
        return dev - (a * t + b), float(a) * 3600.0

    @property
    def ra_detrended(self) -> np.ndarray:
        return self._detrended(self.ra_deviations)[0]

    @property
    def dec_detrended(self) -> np.ndarray:
        return self._detrended(self.dec_deviations)[0]

    @property
    def ra_drift_arcsec_per_hour(self) -> float:
        return self._detrended(self.ra_deviations)[1]

    @property
    def dec_drift_arcsec_per_hour(self) -> float:
        return self._detrended(self.dec_deviations)[1]


@dataclass
class ParsedSession:
    """Parsed session data from log files."""
    # Metadata
    file_path: str = ""
    version: str = ""
    observatory: str = ""
    mount_name: str = ""
    mount_id: str = ""
    mount_driver: str = ""
    firmware: str = ""
    start_time: Optional[datetime] = None

    # Mount data arrays (from .dat) — ALL samples (raw)
    mount_times: list[str] = field(default_factory=list)
    ra_raw_strs: list[str] = field(default_factory=list)
    ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_raw_strs: list[str] = field(default_factory=list)
    dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_axis: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_axis: np.ndarray = field(default_factory=lambda: np.array([]))
    statuses: list[str] = field(default_factory=list)
    timestamps: np.ndarray = field(default_factory=lambda: np.array([]))

    # Computed deviation arrays — TRACKING only, per-segment combined
    ra_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_detrended: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_detrended: np.ndarray = field(default_factory=lambda: np.array([]))
    excursions_removed: int = 0
    samples_in_segments: int = 0
    ra_jitter: float = 0.0
    dec_jitter: float = 0.0
    repositionnements: int = 0
    # Timestamps ALIGNED with ra_deviations / dec_deviations. The plain
    # `timestamps` array holds every sample of the file, while the deviations
    # only hold the samples kept in the segments: plotting one against the
    # other silently draws nothing.
    deviation_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    deviation_ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    deviation_dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_residual: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_residual: np.ndarray = field(default_factory=lambda: np.array([]))

    # TRACKING-only filtered arrays (for analysis)
    tracking_mask: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    tracking_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))

    # Target segments (each segment = one target in TRACKING mode)
    target_segments: list[TargetSegment] = field(default_factory=list)

    # Time data arrays (from .dti)
    time_mount_times: list[str] = field(default_factory=list)
    time_pc_mount_diff: np.ndarray = field(default_factory=lambda: np.array([]))
    time_pc_loop: np.ndarray = field(default_factory=lambda: np.array([]))
    time_mount_loop: np.ndarray = field(default_factory=lambda: np.array([]))
    time_ntp_diff: np.ndarray = field(default_factory=lambda: np.array([]))
    time_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))

    # Events (from .log)
    events: list[tuple[str, str]] = field(default_factory=list)

    # Environment data arrays (from .env)
    env_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    env_temperature_ext: np.ndarray = field(default_factory=lambda: np.array([]))
    env_pressure: np.ndarray = field(default_factory=lambda: np.array([]))
    env_temperature_int: np.ndarray = field(default_factory=lambda: np.array([]))
    env_status_codes: list[int] = field(default_factory=list)
    env_tracking_rates: np.ndarray = field(default_factory=lambda: np.array([]))
    env_meridian_flip: np.ndarray = field(default_factory=lambda: np.array([]))
    env_alignment_stars: list[int] = field(default_factory=list)
    env_alignment_rms: np.ndarray = field(default_factory=lambda: np.array([]))
    env_polar_error: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def sample_count(self) -> int:
        return len(self.mount_times)

    @property
    def tracking_sample_count(self) -> int:
        return int(np.sum(self.tracking_mask)) if len(self.tracking_mask) > 0 else 0

    @property
    def duration_seconds(self) -> float:
        if len(self.timestamps) < 2:
            return 0.0
        return float(self.timestamps[-1] - self.timestamps[0])

    @property
    def duration_str(self) -> str:
        s = self.duration_seconds
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"

    @property
    def effective_frequency(self) -> float:
        """Cadence reelle des echantillons, en hertz.

        La duree peut valoir zero alors qu'il y a des echantillons : une
        session tenant dans la meme seconde, un fichier tronque dont toutes
        les lignes portent la meme heure. La division levait alors une
        exception au beau milieu de la construction du rapport — et l'ouverture
        d'un fichier .dat n'est pas protegee : l'application tombait.
        """
        if len(self.timestamps) < 2:
            return 0.0
        duree = self.duration_seconds
        if duree <= 0:
            return 0.0
        return (len(self.timestamps) - 1) / duree


def _parse_time_to_seconds(t_str: str) -> float:
    """Parse HH:MM:SS.dd to seconds since midnight."""
    try:
        parts = t_str.strip().split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _parse_ra_to_hours(ra_str: str) -> float:
    """Parse RA string hh:mm:ss.dd to decimal hours."""
    try:
        parts = ra_str.strip().split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h + m / 60.0 + s / 3600.0
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _parse_dec_to_degrees(dec_str: str) -> float:
    """Parse DEC string dd:mm:ss.dd to decimal degrees."""
    try:
        s = dec_str.strip()
        sign = -1 if s.startswith('-') else 1
        s = s.lstrip('+-')
        parts = s.split(':')
        if len(parts) == 3:
            d = int(parts[0])
            m = int(parts[1])
            sec = float(parts[2])
            return sign * (d + m / 60.0 + sec / 3600.0)
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _ra_diff_hours(ra1: float, ra2: float) -> float:
    """Compute RA difference in hours, handling 24h wrap."""
    diff = ra1 - ra2
    if diff > 12.0:
        diff -= 24.0
    elif diff < -12.0:
        diff += 24.0
    return diff


def _sep_arcsec(ra1_h, dec1_d, ra2_h, dec2_d) -> float:
    """Angular separation in arcseconds (small-angle, ample here)."""
    dra = _ra_diff_hours(ra1_h, ra2_h) * 15.0 * 3600.0 * np.cos(np.radians(dec2_d))
    ddec = (dec1_d - dec2_d) * 3600.0
    return float(np.hypot(dra, ddec))


def _settled_stdevs(t: np.ndarray, stdevs: np.ndarray,
                    dev: np.ndarray | None = None) -> np.ndarray:
    """Blank the running STDEV values that still contain the previous slew.

    The running STDEV is computed live over a sliding window (60 s by
    default). For the first window-length after a target change, that window
    still straddles the slew, so the value describes the slew and not the
    tracking. On a short target the contamination is total: on the
    2026-09-22 session, target #2 lasted 33 s and reported a mean running
    STDEV of 69.9" while its whole peak-to-peak was 0.64".

    Contaminated samples are set to 0, which is the value the report already
    treats as "no data".
    """
    out = np.asarray(stdevs, dtype=np.float64).copy()
    if len(out) == 0 or len(t) != len(out):
        return out
    out[t < t[0] + _STDEV_SETTLE_S] = 0.0
    # Same problem inside a segment: an autofocus run or a filter change
    # interrupts acquisition, and the window straddles the gap afterwards.
    if len(t) > 2:
        dt = np.diff(t)
        pas = float(np.median(dt))
        if pas > 0:
            for i in np.flatnonzero(dt > 5.0 * pas):
                out[(t > t[i]) & (t < t[i + 1] + _STDEV_SETTLE_S)] = 0.0
    # And around every repositioning: the mount is MOVED between exposures,
    # so for one window length afterwards the running STDEV measures the step
    # height, not how well the mount holds. This is the same reasoning the
    # jitter already applies by splitting on steps.
    if dev is not None and len(dev) == len(t) > 8:
        d = np.abs(np.diff(np.asarray(dev, dtype=np.float64)))
        ech = float(np.median(d))
        seuil = max(8.0 * ech, 0.5)
        for i in np.flatnonzero(d > seuil):
            out[(t >= t[i]) & (t < t[i] + _STDEV_SETTLE_S)] = 0.0
    return out


@dataclass
class Mouvement:
    """One commanded move: a dither, a re-centering, or something else.

    Raw threshold crossings are NOT movements. A single re-centering of 70"
    takes several samples to complete and trips the threshold at each one:
    on the 2026-09-22 session, 98 crossings on the first target were 37
    actual moves. Counting crossings made the reported median amplitude
    0.79" when the real median move was 7.9" -- an order of magnitude, and
    in the flattering direction.
    """
    debut: int = 0
    fin: int = 0
    instant: float = 0.0
    amplitude: float = 0.0        # arcsec, end to end
    duree: float = 0.0            # seconds
    classe: str = "dither"        # dither | recentrage | anomalie
    jitter_apres: float = 0.0


def _mouvements(ra_dev, dec_dev, t, seuil_recentrage=25.0) -> list:
    """Group threshold crossings into movements and label them.

    Crossings closer together than ``_FUSION_S`` belong to one move. The
    label is deliberately crude, because the log cannot tell a commanded
    move from an uncommanded one -- there is no command channel in the
    file. What it CAN see is the size, and whether the mount settled
    afterwards; a move that does not settle is the one worth flagging.
    """
    n = len(ra_dev)
    if n < 8 or len(t) != n:
        return []
    d = np.hypot(np.diff(ra_dev), np.diff(dec_dev))
    ech = float(np.median(d))
    seuil = max(8.0 * ech, 0.5)
    idx = np.flatnonzero(d > seuil) + 1
    if not len(idx):
        return []
    groupes = [[int(idx[0])]]
    for i in idx[1:]:
        if t[i] - t[groupes[-1][-1]] <= _FUSION_S:
            groupes[-1].append(int(i))
        else:
            groupes.append([int(i)])

    # Reference spread: how tight the mount is between moves. A move is an
    # anomaly when what follows it is markedly worse than that.
    bords = np.concatenate(([0], idx, [n]))
    calmes = [np.hypot(np.std(ra_dev[a:b]), np.std(dec_dev[a:b]))
              for a, b in zip(bords[:-1], bords[1:]) if b - a >= 8]
    calme = float(np.median(calmes)) if calmes else 0.0

    out = []
    for g in groupes:
        a = max(0, g[0] - 1)
        b = min(g[-1], n - 1)
        m = Mouvement(
            debut=a, fin=b, instant=float(t[a]),
            amplitude=float(np.hypot(ra_dev[b] - ra_dev[a], dec_dev[b] - dec_dev[a])),
            duree=float(t[b] - t[a]),
        )
        fin_fenetre = min(n, b + 1 + _FENETRE_APRES)
        if fin_fenetre - (b + 1) >= 8:
            m.jitter_apres = float(np.hypot(np.std(ra_dev[b + 1:fin_fenetre]),
                                            np.std(dec_dev[b + 1:fin_fenetre])))
        if calme > 0 and m.jitter_apres > max(5.0 * calme, 1.0):
            m.classe = "anomalie"
        elif m.amplitude >= seuil_recentrage:
            m.classe = "recentrage"
        else:
            m.classe = "dither"
        out.append(m)
    return out


def _baseline(t: np.ndarray, v: np.ndarray, block_s: float = 180.0) -> np.ndarray:
    """Slowly varying baseline of ``v``: the position the mount is holding.

    Median over ``block_s`` blocks, linearly interpolated back onto ``t``.
    A median is used rather than a mean so that a dither sitting inside a
    block cannot pull the baseline towards itself, and blocks rather than a
    polynomial so that a re-centering step is followed instead of smeared
    across the whole segment.
    """
    n = len(v)
    if n < 8 or t[-1] <= t[0]:
        return np.full(n, float(np.median(v)) if n else 0.0)
    edges = np.arange(t[0], t[-1] + block_s, block_s)
    if len(edges) < 2:
        return np.full(n, float(np.median(v)))
    idx = np.clip(np.searchsorted(edges, t, side='right') - 1, 0, len(edges) - 2)
    centres, meds = [], []
    for b in range(len(edges) - 1):
        m = idx == b
        if int(np.sum(m)) >= 3:
            centres.append(float(np.mean(t[m])))
            meds.append(float(np.median(v[m])))
    if len(centres) < 2:
        return np.full(n, float(np.median(v)))
    return np.interp(t, np.array(centres), np.array(meds))


def _segment_tracking_data(
    ra_hours: np.ndarray, dec_degrees: np.ndarray,
    timestamps: np.ndarray, ra_stdevs: np.ndarray, dec_stdevs: np.ndarray,
) -> list[TargetSegment]:
    """Segment TRACKING data into target groups.

    A new target is detected when a sample lies further than
    ``_TARGET_CHANGE_ARCSEC`` from the CURRENT target position — not when two
    consecutive samples differ, which never happens during a continuous slew.

    Samples taken while the mount is moving between targets form runs shorter
    than ``_MIN_SEGMENT_SAMPLES`` and are therefore dropped, which is what we
    want: they are travel, not tracking.

    Within a segment, excursions beyond ``_EXCURSION_ARCSEC`` (dither,
    re-centering, autofocus moves) are excluded from the deviations and counted
    in ``excursions_removed``.
    """
    n = len(ra_hours)
    if n < _MIN_SEGMENT_SAMPLES:
        return []

    # ── 1. boundaries, from the separation to the current reference ────────
    boundaries = [0]
    ref_ra = float(ra_hours[0])
    ref_dec = float(dec_degrees[0])
    buf_start = 0
    for i in range(1, n):
        if _sep_arcsec(ra_hours[i], dec_degrees[i], ref_ra, ref_dec) > _TARGET_CHANGE_ARCSEC:
            boundaries.append(i)
            ref_ra = float(ra_hours[i])
            ref_dec = float(dec_degrees[i])
            buf_start = i
        elif i - buf_start >= _REF_WINDOW:
            # refresh the reference so a slow drift does not end up splitting
            # a segment after a few hours
            lo = max(buf_start, i - _REF_WINDOW)
            ref_ra = float(np.median(ra_hours[lo:i + 1]))
            ref_dec = float(np.median(dec_degrees[lo:i + 1]))
            buf_start = i
    boundaries.append(n)

    segments = []
    for b in range(len(boundaries) - 1):
        start = boundaries[b]
        end = boundaries[b + 1]
        if end - start < _MIN_SEGMENT_SAMPLES:
            continue

        seg_ra = ra_hours[start:end]
        seg_dec = dec_degrees[start:end]

        ra_median = float(np.median(seg_ra))
        dec_median = float(np.median(seg_dec))
        cos_dec = np.cos(np.radians(dec_median))

        ra_dev = np.array([_ra_diff_hours(r, ra_median) for r in seg_ra]) * 15.0 * 3600.0 * cos_dec
        dec_dev = (seg_dec - dec_median) * 3600.0

        # ── 2. drop commanded excursions (dither, re-centering, AF) ────────
        #
        # The threshold must be applied to the deviation AFTER the slow drift
        # has been taken out, never to the raw distance from the segment
        # median. An unguided mount left on one target for hours drifts far
        # beyond _EXCURSION_ARCSEC without anything being commanded: on the
        # 2026-09-22 session, target #1 held 8 h with a DEC drift of
        # -16.8"/h, i.e. ~134" end to end. Thresholding the raw separation
        # threw away 36,336 of its 54,388 samples -- 59% of the whole night --
        # and labelled pure tracking as "commanded excursions".
        #
        # The fit is done twice: once on everything to get a first drift
        # estimate, then again on the samples that survived, so that a real
        # dither cannot drag the slope towards itself.
        seg_t = timestamps[start:end]

        # The baseline is a block median, not a straight line. Over 8 h the
        # drift of an unguided mount CURVES (it depends on hour angle), and a
        # re-centering leaves a permanent step; a linear fit follows neither.
        # A median over ~3 min blocks follows both, while a dither -- a few
        # seconds at most -- cannot move it.
        ra_res = ra_dev - _baseline(seg_t, ra_dev)
        dec_res = dec_dev - _baseline(seg_t, dec_dev)
        sep = np.hypot(ra_res, dec_res)
        keep = sep <= _EXCURSION_ARCSEC
        sep_max = float(sep.max()) if len(sep) else 0.0
        n_out = int(np.sum(~keep))
        if n_out and int(np.sum(keep)) >= _MIN_SEGMENT_SAMPLES:
            # recompute the median on the clean samples, then the deviations
            ra_median = float(np.median(seg_ra[keep]))
            dec_median = float(np.median(seg_dec[keep]))
            cos_dec = np.cos(np.radians(dec_median))
            ra_dev = np.array([_ra_diff_hours(r, ra_median) for r in seg_ra]) * 15.0 * 3600.0 * cos_dec
            dec_dev = (seg_dec - dec_median) * 3600.0
        else:
            keep = np.ones(len(seg_ra), dtype=bool)
            n_out = 0

        idx = np.arange(start, end)[keep]
        seg = TargetSegment(
            start_index=start,
            end_index=end,
            ra_median_hours=ra_median,
            dec_median_degrees=dec_median,
            sample_count=int(np.sum(keep)),
            ra_deviations=ra_dev[keep],
            dec_deviations=dec_dev[keep],
            timestamps=timestamps[idx],
            ra_hours=seg_ra[keep],
            dec_degrees=seg_dec[keep],
            ra_stdevs=_settled_stdevs(timestamps[idx], ra_stdevs[idx], ra_dev[keep]),
            dec_stdevs=_settled_stdevs(timestamps[idx], dec_stdevs[idx], dec_dev[keep]),
            ra_residual=ra_res[keep],
            dec_residual=dec_res[keep],
            mouvements=_mouvements(ra_dev[keep], dec_dev[keep], timestamps[idx]),
            excursions_removed=n_out,
            excursion_max_arcsec=sep_max,
        )
        segments.append(seg)

    return segments


def parse_dat_file(dat_path: Path) -> ParsedSession:
    """Parse a .dat file (27-column TAB-separated mount data).

    Filters TRACKING samples, segments by target, computes per-segment deviations.
    Returns a ParsedSession with all mount data arrays populated.
    """
    session = ParsedSession(file_path=str(dat_path))

    if not dat_path.exists():
        logger.error(f"File not found: {dat_path}")
        return session

    mount_times = []
    ra_raw_strs = []
    ra_hours_list = []
    ra_stdev_list = []
    dec_raw_strs = []
    dec_deg_list = []
    dec_stdev_list = []
    ra_axis_list = []
    dec_axis_list = []
    statuses = []
    time_seconds = []

    in_header = True

    try:
        with open(dat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')

                # Detect end of header: column header line starts with "RAW"
                if in_header:
                    if line.startswith("MountMonitor"):
                        ver_match = re.search(r'v\.(.+?)\)', line)
                        if ver_match:
                            session.version = ver_match.group(1)
                    elif line.startswith("Location:"):
                        session.observatory = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount:") and not line.startswith("Mount ID"):
                        session.mount_name = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount ID:"):
                        session.mount_id = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount driver:"):
                        session.mount_driver = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Firmware:"):
                        session.firmware = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Site:"):
                        # Decimal degrees, longitude positive EAST -- the
                        # writer normalises both the mount's sexagesimal
                        # LX200 (positive west) and the preferences.
                        champs = line.split('\t')[1:]
                        try:
                            session.site_lat = float(champs[0])
                            session.site_lon = float(champs[1])
                            if len(champs) > 2 and champs[2].strip():
                                session.site_elev = float(champs[2])
                        except (IndexError, ValueError):
                            session.site_lat = session.site_lon = None
                    elif line.startswith("Start:"):
                        from datetime import datetime as _dt
                        try:
                            session.start_iso = _dt.fromisoformat(
                                line.split('\t', 1)[1].strip())
                        except (IndexError, ValueError):
                            session.start_iso = None

                    # Column header line (last header line)
                    if line.startswith("RAW Mount time"):
                        in_header = False
                    continue

                # Data line: 27 TAB-separated columns
                cols = line.split('\t')
                if len(cols) < 27:
                    continue

                try:
                    # Column 1: Mount time
                    mt = cols[0].strip()
                    mount_times.append(mt)
                    ts = _parse_time_to_seconds(mt) if mt else 0.0
                    time_seconds.append(ts)

                    # Column 3: RAW RA
                    ra_raw_strs.append(cols[2].strip())

                    # Column 4: RA (formatted)
                    ra_h = _parse_ra_to_hours(cols[3])
                    ra_hours_list.append(ra_h)

                    # Column 5: RA StDev
                    ra_stdev_list.append(float(cols[4]) if cols[4].strip() else 0.0)

                    # Column 6: RAW DEC
                    dec_raw_strs.append(cols[5].strip())

                    # Column 7: DEC (formatted)
                    dec_d = _parse_dec_to_degrees(cols[6])
                    dec_deg_list.append(dec_d)

                    # Column 8: DEC StDev
                    dec_stdev_list.append(float(cols[7]) if cols[7].strip() else 0.0)

                    # Column 9: RAW DEC AXIS
                    dec_axis_list.append(float(cols[8]) if cols[8].strip() else 0.0)

                    # Column 12: RAW RA AXIS
                    ra_axis_list.append(float(cols[11]) if cols[11].strip() else 0.0)

                    # Column 27: Status
                    statuses.append(cols[26].strip())

                except (ValueError, IndexError) as e:
                    logger.debug(f"Skipping malformed line: {e}")
                    continue

    except OSError as e:
        logger.error(f"Failed to read {dat_path}: {e}")
        return session

    if not mount_times:
        return session

    # Handle timestamps: if mount times are empty, generate from index + assumed 2Hz
    all_empty = all(t == 0.0 for t in time_seconds)
    if all_empty:
        # Generate synthetic timestamps at 2Hz (0.5s interval)
        assumed_rate = 2.0
        time_seconds = [i / assumed_rate for i in range(len(mount_times))]

    # Handle midnight wrap: if time decreases, add 24h offset
    corrected_times = []
    offset = 0.0
    prev_t = 0.0
    for i, t in enumerate(time_seconds):
        if i > 0 and t < prev_t - 3600:  # big backward jump = midnight
            offset += 86400.0
        corrected_times.append(t + offset)
        prev_t = t

    # Convert to numpy arrays (ALL samples — raw)
    session.mount_times = mount_times
    session.ra_raw_strs = ra_raw_strs
    session.ra_hours = np.array(ra_hours_list)
    session.ra_stdevs = np.array(ra_stdev_list)
    session.dec_raw_strs = dec_raw_strs
    session.dec_degrees = np.array(dec_deg_list)
    session.dec_stdevs = np.array(dec_stdev_list)
    session.ra_axis = np.array(ra_axis_list)
    session.dec_axis = np.array(dec_axis_list)
    session.statuses = statuses
    session.timestamps = np.array(corrected_times)

    # ── Filter TRACKING-only samples ──
    tracking_mask = np.array([s == "TRACKING" for s in statuses], dtype=bool)

    # Drop the first seconds of every return to tracking. The mount reports
    # TRACKING as soon as the slew command ends, while the axes are still
    # settling; those samples are the tail of a move, not tracking error.
    # The live logger has a delay_after_slew setting for the same reason,
    # but it defaults to 0 and does nothing on replay -- a file already
    # written carries every sample.
    if len(tracking_mask) > 1 and _DELAI_APRES_SLEW > 0:
        reprises = np.flatnonzero(tracking_mask[1:] & ~tracking_mask[:-1]) + 1
        for i in reprises:
            fin = session.timestamps[i] + _DELAI_APRES_SLEW
            j = i
            while j < len(tracking_mask) and session.timestamps[j] < fin:
                tracking_mask[j] = False
                j += 1
    session.tracking_mask = tracking_mask

    if np.any(tracking_mask):
        session.tracking_timestamps = session.timestamps[tracking_mask]
        session.tracking_ra_hours = session.ra_hours[tracking_mask]
        session.tracking_dec_degrees = session.dec_degrees[tracking_mask]
        session.tracking_ra_stdevs = session.ra_stdevs[tracking_mask]
        session.tracking_dec_stdevs = session.dec_stdevs[tracking_mask]

        # ── Segment tracking data by target ──
        segments = _segment_tracking_data(
            session.tracking_ra_hours,
            session.tracking_dec_degrees,
            session.tracking_timestamps,
            session.tracking_ra_stdevs,
            session.tracking_dec_stdevs,
        )
        session.target_segments = segments

        # ── Combine per-segment deviations into session-level arrays ──
        if segments:
            all_ra_dev = np.concatenate([seg.ra_deviations for seg in segments])
            all_dec_dev = np.concatenate([seg.dec_deviations for seg in segments])
            session.ra_deviations = all_ra_dev
            session.dec_deviations = all_dec_dev
            # Drift-free deviations: this is what actually blurs an exposure.
            session.ra_detrended = np.concatenate([seg.ra_detrended for seg in segments])
            session.dec_detrended = np.concatenate([seg.dec_detrended for seg in segments])
            session.ra_residual = np.concatenate([seg.ra_residual for seg in segments])
            session.dec_residual = np.concatenate([seg.dec_residual for seg in segments])
            # Jitter weighted by sample count: the figure the rating is based on.
            _w = float(sum(g.sample_count for g in segments)) or 1.0
            session.ra_jitter = sum(g.ra_jitter * g.sample_count for g in segments) / _w
            session.dec_jitter = sum(g.dec_jitter * g.sample_count for g in segments) / _w
            session.repositionnements = sum(g.repositionnements for g in segments)
            session.mouvements = [m for g in segments for m in g.mouvements]
            session.deviation_timestamps = np.concatenate([g.timestamps for g in segments])
            session.deviation_ra_stdevs = np.concatenate([g.ra_stdevs for g in segments])
            session.deviation_dec_stdevs = np.concatenate([g.dec_stdevs for g in segments])
            session.excursions_removed = sum(seg.excursions_removed for seg in segments)
            session.samples_in_segments = int(sum(seg.sample_count for seg in segments))
        else:
            # Fallback: single segment from all tracking data
            ra_med = float(np.median(session.tracking_ra_hours))
            dec_med = float(np.median(session.tracking_dec_degrees))
            cos_dec = np.cos(np.radians(dec_med))
            ra_diffs = np.array([_ra_diff_hours(r, ra_med) for r in session.tracking_ra_hours])
            session.ra_deviations = ra_diffs * 15.0 * 3600.0 * cos_dec
            session.dec_deviations = (session.tracking_dec_degrees - dec_med) * 3600.0
            session.deviation_timestamps = session.tracking_timestamps
            session.deviation_ra_stdevs = session.tracking_ra_stdevs
            session.deviation_dec_stdevs = session.tracking_dec_stdevs

        logger.info(f"Segmented into {len(segments)} target(s) from "
                     f"{int(np.sum(tracking_mask))} tracking samples")
    else:
        logger.warning("No TRACKING samples found in session")

    # Extract date from filename
    fname = dat_path.stem  # MountMonitor_YYYYMMDD-HHMMSS
    date_match = re.search(r'(\d{8})-(\d{6})', fname)
    if date_match:
        try:
            session.start_time = datetime.strptime(
                f"{date_match.group(1)}{date_match.group(2)}", "%Y%m%d%H%M%S"
            )
        except ValueError:
            pass

    # Files written before the header carried a "Start:" line have no stored
    # offset. The name is local time, so attaching the reader's own offset is
    # the only thing available -- right whenever the file is read where it was
    # written, which is the normal case.
    if getattr(session, 'start_iso', None) is None and session.start_time is not None:
        session.start_iso = session.start_time.astimezone()

    logger.info(f"Parsed {len(mount_times)} samples from {dat_path.name} "
                f"({int(np.sum(tracking_mask))} tracking, "
                f"duration: {session.duration_str})")
    return session


def parse_dti_file(dti_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .dti file (time data) and add to session."""
    if not dti_path.exists():
        return session

    mount_times = []
    pc_mount_diff = []
    pc_loop = []
    mount_loop = []
    ntp_diff = []
    time_seconds = []

    header_lines = 0

    try:
        with open(dti_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                if header_lines < 3:
                    header_lines += 1
                    continue

                cols = line.split('\t')
                if len(cols) < 4:
                    continue

                try:
                    mt = cols[0].strip()
                    mount_times.append(mt)
                    time_seconds.append(_parse_time_to_seconds(mt))
                    pc_mount_diff.append(float(cols[1]))
                    pc_loop.append(float(cols[2]))
                    mount_loop.append(float(cols[3]))
                    ntp_diff.append(float(cols[4]) if len(cols) > 4 and cols[4].strip() else 0.0)
                except (ValueError, IndexError):
                    continue

    except OSError as e:
        logger.error(f"Failed to read {dti_path}: {e}")
        return session

    if time_seconds:
        # Handle midnight wrap
        corrected = []
        offset = 0.0
        prev_t = 0.0
        for i, t in enumerate(time_seconds):
            if i > 0 and t < prev_t - 3600:
                offset += 86400.0
            corrected.append(t + offset)
            prev_t = t

        session.time_mount_times = mount_times
        session.time_pc_mount_diff = np.array(pc_mount_diff)
        session.time_pc_loop = np.array(pc_loop)
        session.time_mount_loop = np.array(mount_loop)
        session.time_ntp_diff = np.array(ntp_diff)
        session.time_timestamps = np.array(corrected)

    return session


def parse_log_file(log_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .log file (events) and add to session."""
    if not log_path.exists():
        return session

    events = []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                # Skip header (non-timestamped lines)
                if '\t' in line:
                    parts = line.split('\t', 1)
                    if len(parts) == 2 and '/' in parts[0]:
                        events.append((parts[0].strip(), parts[1].strip()))
    except OSError:
        pass

    session.events = events
    return session


def parse_env_file(env_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .env file (environment/diagnostics data) and add to session."""
    if not env_path.exists():
        return session

    timestamps = []
    temp_ext = []
    pressure = []
    temp_int = []
    status_codes = []
    tracking_rates = []
    meridian_flip = []
    alignment_stars = []
    alignment_rms = []
    polar_error = []

    header_lines = 0

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                if header_lines < 3:
                    header_lines += 1
                    continue

                cols = line.split('\t')
                if len(cols) < 4:
                    continue

                try:
                    mt = cols[0].strip()
                    timestamps.append(_parse_time_to_seconds(mt))
                    temp_ext.append(float(cols[1]) if cols[1].strip() else float('nan'))
                    pressure.append(float(cols[2]) if cols[2].strip() else float('nan'))
                    temp_int.append(float(cols[3]) if cols[3].strip() else float('nan'))

                    if len(cols) > 4 and cols[4].strip():
                        status_codes.append(int(cols[4]))
                    else:
                        status_codes.append(-1)

                    tracking_rates.append(float(cols[5]) if len(cols) > 5 and cols[5].strip() else float('nan'))
                    meridian_flip.append(float(cols[6]) if len(cols) > 6 and cols[6].strip() else float('nan'))

                    # cols[7] = pier side (text, skip for now)

                    if len(cols) > 8 and cols[8].strip():
                        alignment_stars.append(int(cols[8]))
                    else:
                        alignment_stars.append(0)

                    alignment_rms.append(float(cols[9]) if len(cols) > 9 and cols[9].strip() else float('nan'))
                    polar_error.append(float(cols[10]) if len(cols) > 10 and cols[10].strip() else float('nan'))

                except (ValueError, IndexError):
                    continue

    except OSError as e:
        logger.error(f"Failed to read {env_path}: {e}")
        return session

    if timestamps:
        session.env_timestamps = np.array(timestamps)
        session.env_temperature_ext = np.array(temp_ext)
        session.env_pressure = np.array(pressure)
        session.env_temperature_int = np.array(temp_int)
        session.env_status_codes = status_codes
        session.env_tracking_rates = np.array(tracking_rates)
        session.env_meridian_flip = np.array(meridian_flip)
        session.env_alignment_stars = alignment_stars
        session.env_alignment_rms = np.array(alignment_rms)
        session.env_polar_error = np.array(polar_error)

    return session


def parse_session(dat_path: Path) -> ParsedSession:
    """Parse a complete session from a .dat file and its siblings.

    Automatically finds and parses .dti, .log, and .env files with the same prefix.
    """
    session = parse_dat_file(dat_path)

    # Find sibling files
    stem = dat_path.stem
    parent = dat_path.parent

    dti_path = parent / f"{stem}.dti"
    log_path = parent / f"{stem}.log"
    env_path = parent / f"{stem}.env"

    if dti_path.exists():
        parse_dti_file(dti_path, session)

    if log_path.exists():
        parse_log_file(log_path, session)

    if env_path.exists():
        parse_env_file(env_path, session)

    return session


def list_log_sessions(log_dir: Path) -> list[dict]:
    """List available log sessions in a directory.

    Returns list of dicts with: path, filename, date, size_kb
    """
    sessions = []
    if not log_dir.exists():
        return sessions

    for dat_file in sorted(log_dir.glob("MountMonitor_*.dat"), reverse=True):
        info = {
            'path': dat_file,
            'filename': dat_file.name,
            'size_kb': dat_file.stat().st_size / 1024,
        }
        # Extract date from filename
        date_match = re.search(r'(\d{8})-(\d{6})', dat_file.stem)
        if date_match:
            try:
                dt = datetime.strptime(
                    f"{date_match.group(1)}{date_match.group(2)}", "%Y%m%d%H%M%S"
                )
                info['date'] = dt
                info['date_str'] = dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                info['date'] = None
                info['date_str'] = "?"
        sessions.append(info)

    return sessions
