"""Circular data buffer for real-time graph data with running statistics."""

import numpy as np
from collections import deque
from typing import Optional
import threading


class DataBuffer:
    """Thread-safe circular buffer for time-series data with running statistics.

    Stores up to `max_size` samples. Provides efficient running STDEV,
    min/max tracking, and median computation.

    Performance: numpy array copies are cached and only rebuilt when data changes.
    """

    def __init__(self, max_size: int = 50000):
        self._max_size = max_size
        self._lock = threading.Lock()

        # Core data arrays
        self._timestamps: deque[float] = deque(maxlen=max_size)
        self._values: deque[float] = deque(maxlen=max_size)

        # Statistics
        self._min_value = float('inf')
        self._max_value = float('-inf')
        self._max_stdev = 0.0
        self._running_stdevs: deque[float] = deque(maxlen=max_size)

        # Cached numpy arrays — rebuilt only when dirty
        self._cached_t: np.ndarray = np.array([], dtype=np.float64)
        self._cached_v: np.ndarray = np.array([], dtype=np.float64)
        self._cached_stdev: np.ndarray = np.array([], dtype=np.float64)
        self._arrays_dirty: bool = True
        self._stdev_dirty: bool = True

        # Cached median (recomputed periodically, not on every call)
        self._cached_median: float = 0.0
        self._median_valid: bool = False
        self._median_sample_count: int = 0
        self._MEDIAN_RECOMPUTE_INTERVAL: int = 50  # Recompute every N appends

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._values)

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
        with self._lock:
            self._timestamps.append(timestamp)
            self._values.append(value)
            if value < self._min_value:
                self._min_value = value
            if value > self._max_value:
                self._max_value = value
            self._median_sample_count += 1
            if self._median_sample_count >= self._MEDIAN_RECOMPUTE_INTERVAL:
                self._median_valid = False
            self._arrays_dirty = True

    def get_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Get timestamps and values as numpy arrays. Thread-safe, cached."""
        with self._lock:
            if self._arrays_dirty:
                self._cached_t = np.array(self._timestamps, dtype=np.float64)
                self._cached_v = np.array(self._values, dtype=np.float64)
                self._arrays_dirty = False
            return self._cached_t, self._cached_v

    def get_downsampled_arrays(self, max_points: int = 5000) -> tuple[np.ndarray, np.ndarray]:
        """Get arrays downsampled for graph display. Avoids plotting 50K points."""
        t, v = self.get_arrays()
        n = len(t)
        if n <= max_points:
            return t, v
        # Decimate: keep every Nth point, always include last point
        step = n // max_points
        indices = np.arange(0, n, step)
        if indices[-1] != n - 1:
            indices = np.append(indices, n - 1)
        return t[indices], v[indices]

    def get_stdev_array(self) -> np.ndarray:
        """Get running STDEV values as numpy array. Cached."""
        with self._lock:
            if self._stdev_dirty:
                self._cached_stdev = np.array(self._running_stdevs, dtype=np.float64)
                self._stdev_dirty = False
            return self._cached_stdev

    def compute_running_stdev(self, window_seconds: float):
        """Compute running standard deviation over a time window.

        Uses an O(n) sliding window approach instead of O(n²) per-sample masking.
        This should be called periodically from the processing thread.
        Copies data under lock, then computes outside the lock to minimize blocking.
        """
        # Step 1: copy data under lock
        with self._lock:
            n = len(self._values)
            if n < 2:
                self._running_stdevs.clear()
                self._stdev_dirty = True
                return
            timestamps = np.array(self._timestamps)
            values = np.array(self._values)

        # Step 2: compute outside lock (no blocking)
        stdevs = np.zeros(n)
        max_sd = 0.0
        left = 0
        win_sum = 0.0
        win_sum2 = 0.0
        win_count = 0

        for right in range(n):
            v = values[right]
            win_sum += v
            win_sum2 += v * v
            win_count += 1

            while left < right and timestamps[left] < timestamps[right] - window_seconds:
                vl = values[left]
                win_sum -= vl
                win_sum2 -= vl * vl
                win_count -= 1
                left += 1

            if win_count > 1:
                mean = win_sum / win_count
                variance = (win_sum2 / win_count) - (mean * mean)
                variance = variance * win_count / (win_count - 1)
                sd = float(np.sqrt(max(0.0, variance)))
                stdevs[right] = sd
                if sd > max_sd:
                    max_sd = sd

        # Step 3: store result under lock
        with self._lock:
            self._running_stdevs = deque(stdevs, maxlen=self._max_size)
            self._max_stdev = max(self._max_stdev, max_sd)
            self._stdev_dirty = True

    def get_median(self) -> float:
        """Get the median of all values in the buffer (cached for performance)."""
        with self._lock:
            if not self._values:
                return 0.0
            if not self._median_valid:
                self._cached_median = float(np.median(np.array(self._values)))
                self._median_valid = True
                self._median_sample_count = 0
            return self._cached_median

    def get_visible_data(self, visible_seconds: float) -> tuple[np.ndarray, np.ndarray]:
        """Get only the data visible in the current time window."""
        with self._lock:
            if not self._timestamps:
                return np.array([]), np.array([])
            timestamps = np.array(self._timestamps)
            values = np.array(self._values)
            cutoff = timestamps[-1] - visible_seconds
            mask = timestamps >= cutoff
            return timestamps[mask], values[mask]

    def reset_minmax(self):
        """Reset min/max tracking."""
        with self._lock:
            if self._values:
                arr = np.array(self._values)
                self._min_value = float(np.min(arr))
                self._max_value = float(np.max(arr))
            else:
                self._min_value = float('inf')
                self._max_value = float('-inf')
            self._max_stdev = 0.0

    def reset(self):
        """Reset all data."""
        with self._lock:
            self._timestamps.clear()
            self._values.clear()
            self._running_stdevs.clear()
            self._min_value = float('inf')
            self._max_value = float('-inf')
            self._max_stdev = 0.0
            self._cached_median = 0.0
            self._median_valid = False
            self._median_sample_count = 0

    def get_last_n(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        """Get the last N samples."""
        with self._lock:
            timestamps = list(self._timestamps)[-n:]
            values = list(self._values)[-n:]
            return np.array(timestamps), np.array(values)
