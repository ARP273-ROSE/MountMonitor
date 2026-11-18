"""Circular data buffer for real-time graph data with running statistics."""

import threading

import numpy as np


def running_stdev(t: np.ndarray, v: np.ndarray, window_seconds: float) -> np.ndarray:
    """Sample standard deviation of v over the trailing `window_seconds`.

    Vectorised with cumulative sums: 1.3 ms for 50,000 points where the
    Python loop took 50 ms per buffer. That loop ran in the poller thread
    every second (RA + DEC = 170 ms) and made it miss a fifth of its
    samples at 10 Hz -- a third or more on a small PC.
    Values are centred first so that the sums of squares keep their precision.
    """
    n = len(v)
    out = np.zeros(n)
    if n < 2:
        return out
    x = v - np.mean(v)
    c1 = np.concatenate(([0.0], np.cumsum(x)))
    c2 = np.concatenate(([0.0], np.cumsum(x * x)))
    left = np.searchsorted(t, t - window_seconds, side='left')
    i = np.arange(n)
    left = np.minimum(left, i)
    k = (i - left + 1).astype(np.float64)
    s = c1[i + 1] - c1[left]
    s2 = c2[i + 1] - c2[left]
    with np.errstate(invalid='ignore', divide='ignore'):
        var = (s2 / k - (s / k) ** 2) * k / (k - 1)
    var[k < 2] = 0.0
    np.clip(var, 0.0, None, out=var)
    np.sqrt(var, out=out)
    out[~np.isfinite(out)] = 0.0
    return out


class DataBuffer:
    """Thread-safe circular buffer for time-series data with running statistics.

    Stores up to `max_size` samples in numpy storage twice that size: appends
    are O(1) and the live data is always one contiguous slice, so reading the
    last two minutes for the graphs costs a few microseconds instead of
    rebuilding 50,000-element arrays from deques four times a second.
    """

    def __init__(self, max_size: int = 50000):
        self._max_size = max_size
        self._lock = threading.Lock()
        self._t = np.empty(2 * max_size, dtype=np.float64)
        self._v = np.empty(2 * max_size, dtype=np.float64)
        self._start = 0
        self._end = 0

        self._min_value = float('inf')
        self._max_value = float('-inf')
        self._max_stdev = 0.0

        # Running STDEV, with the timestamps it was computed on: between two
        # computations new samples arrive, and the two series must not be
        # paired index by index.
        self._sd = np.array([], dtype=np.float64)
        self._sd_t = np.array([], dtype=np.float64)

        self._cached_t = np.array([], dtype=np.float64)
        self._cached_v = np.array([], dtype=np.float64)
        self._arrays_dirty = True

        self._cached_median = 0.0
        self._median_valid = False
        self._median_sample_count = 0
        self._MEDIAN_RECOMPUTE_INTERVAL = 50

    # ── storage ──────────────────────────────────────────────────

    def _live(self):
        return self._t[self._start:self._end], self._v[self._start:self._end]

    @property
    def size(self) -> int:
        with self._lock:
            return self._end - self._start

    @property
    def min_value(self) -> float:
        with self._lock:
            return self._min_value

    @property
    def max_value(self) -> float:
        with self._lock:
            return self._max_value

    @property
    def max_stdev(self) -> float:
        with self._lock:
            return self._max_stdev

    def append(self, timestamp: float, value: float):
        """Add a sample to the buffer."""
        timestamp = float(timestamp)
        value = float(value)
        with self._lock:
            if self._end == len(self._t):
                # Slide the newest max_size-1 samples to the front (amortised O(1)).
                keep = self._max_size - 1
                self._t[:keep] = self._t[self._end - keep:self._end]
                self._v[:keep] = self._v[self._end - keep:self._end]
                self._start, self._end = 0, keep
            elif self._end - self._start >= self._max_size:
                self._start += 1
            self._t[self._end] = timestamp
            self._v[self._end] = value
            self._end += 1
            if value == value:          # NaN never becomes a min or max
                if value < self._min_value:
                    self._min_value = value
                if value > self._max_value:
                    self._max_value = value
            self._median_sample_count += 1
            if self._median_sample_count >= self._MEDIAN_RECOMPUTE_INTERVAL:
                self._median_valid = False
            self._arrays_dirty = True

    def get_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Get timestamps and values as numpy arrays (copies). Thread-safe, cached."""
        with self._lock:
            if self._arrays_dirty:
                t, v = self._live()
                self._cached_t = t.copy()
                self._cached_v = v.copy()
                self._arrays_dirty = False
            return self._cached_t, self._cached_v

    def get_tail(self, seconds: float, t_end: float | None = None):
        """The last `seconds` of data, as (t, v, stdev_t, stdev) copies.

        Only the visible part is copied. stdev_t/stdev cover the same span,
        on the timestamps the running STDEV was computed on."""
        with self._lock:
            t, v = self._live()
            if len(t) == 0:
                vide = np.array([], dtype=np.float64)
                return vide, vide, vide, vide
            fin = float(t[-1]) if t_end is None else float(t_end)
            i = max(0, int(np.searchsorted(t, fin - seconds, side='left')) - 1)
            j = max(0, int(np.searchsorted(self._sd_t, fin - seconds, side='left')) - 1)
            return t[i:].copy(), v[i:].copy(), self._sd_t[j:].copy(), self._sd[j:].copy()

    def get_downsampled_arrays(self, max_points: int = 5000) -> tuple[np.ndarray, np.ndarray]:
        """Get arrays downsampled for graph display. Avoids plotting 50K points."""
        t, v = self.get_arrays()
        n = len(t)
        if n <= max_points:
            return t, v
        step = n // max_points
        indices = np.arange(0, n, step)
        if indices[-1] != n - 1:
            indices = np.append(indices, n - 1)
        return t[indices], v[indices]

    # ── statistics ───────────────────────────────────────────────

    def get_stdev_array(self) -> np.ndarray:
        """Running STDEV of the last computation (see get_stdev_times)."""
        with self._lock:
            return self._sd

    def get_stdev_times(self) -> np.ndarray:
        with self._lock:
            return self._sd_t

    def compute_running_stdev(self, window_seconds: float):
        """Compute the running standard deviation over a time window.

        Copies under the lock, computes outside it."""
        with self._lock:
            t, v = self._live()
            if len(v) < 2:
                self._sd = np.array([], dtype=np.float64)
                self._sd_t = np.array([], dtype=np.float64)
                return
            t = t.copy()
            v = v.copy()
        sd = running_stdev(t, v, window_seconds)
        max_sd = float(sd.max()) if len(sd) else 0.0
        with self._lock:
            self._sd = sd
            self._sd_t = t
            self._max_stdev = max(self._max_stdev, max_sd)

    def get_median(self) -> float:
        """Get the median of all values in the buffer (cached for performance)."""
        with self._lock:
            if self._end == self._start:
                return 0.0
            if not self._median_valid:
                _, v = self._live()
                self._cached_median = float(np.nanmedian(v))
                self._median_valid = True
                self._median_sample_count = 0
            return self._cached_median

    def get_visible_data(self, visible_seconds: float) -> tuple[np.ndarray, np.ndarray]:
        """Get only the data visible in the current time window."""
        t, v, _, _ = self.get_tail(visible_seconds)
        if len(t) and t[0] < t[-1] - visible_seconds:
            return t[1:], v[1:]
        return t, v

    def reset_minmax(self):
        """Reset min/max tracking."""
        with self._lock:
            _, v = self._live()
            if len(v) and np.isfinite(v).any():
                self._min_value = float(np.nanmin(v))
                self._max_value = float(np.nanmax(v))
            else:
                self._min_value = float('inf')
                self._max_value = float('-inf')
            self._max_stdev = 0.0

    def reset(self):
        """Reset all data."""
        with self._lock:
            self._start = self._end = 0
            self._sd = np.array([], dtype=np.float64)
            self._sd_t = np.array([], dtype=np.float64)
            self._min_value = float('inf')
            self._max_value = float('-inf')
            self._max_stdev = 0.0
            self._cached_median = 0.0
            self._median_valid = False
            self._median_sample_count = 0
            self._arrays_dirty = True

    def get_last_n(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        """Get the last N samples."""
        with self._lock:
            t, v = self._live()
            return t[-n:].copy(), v[-n:].copy()
