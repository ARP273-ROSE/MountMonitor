"""Circular data buffer for real-time graph data with running statistics."""

import numpy as np
from collections import deque
from typing import Optional
import threading


class DataBuffer:
    """Thread-safe circular buffer for time-series data with running statistics.

    Stores up to `max_size` samples. Provides efficient running STDEV,
    min/max tracking, and median computation.
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

    def get_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Get timestamps and values as numpy arrays. Thread-safe copy."""
        with self._lock:
            return (
                np.array(self._timestamps, dtype=np.float64),
                np.array(self._values, dtype=np.float64),
            )

    def get_stdev_array(self) -> np.ndarray:
        """Get running STDEV values as numpy array."""
        with self._lock:
            return np.array(self._running_stdevs, dtype=np.float64)

    def compute_running_stdev(self, window_seconds: float):
        """Compute running standard deviation over a time window.

        Uses an O(n) sliding window approach instead of O(n²) per-sample masking.
        This should be called periodically from the processing thread.
        """
        with self._lock:
            n = len(self._values)
            if n < 2:
                self._running_stdevs.clear()
                return

            timestamps = np.array(self._timestamps)
            values = np.array(self._values)
            stdevs = np.zeros(n)

            # Sliding window with two pointers
            left = 0
            win_sum = 0.0
            win_sum2 = 0.0
            win_count = 0

            for right in range(n):
                # Expand window: add current sample
                v = values[right]
                win_sum += v
                win_sum2 += v * v
                win_count += 1

                # Shrink window: remove samples outside the time window
                while left < right and timestamps[left] < timestamps[right] - window_seconds:
                    vl = values[left]
                    win_sum -= vl
                    win_sum2 -= vl * vl
                    win_count -= 1
                    left += 1

                if win_count > 1:
                    # Welford-style variance from running sums
                    mean = win_sum / win_count
                    variance = (win_sum2 / win_count) - (mean * mean)
                    # Bessel correction: multiply by n/(n-1)
                    variance = variance * win_count / (win_count - 1)
                    sd = float(np.sqrt(max(0.0, variance)))
                    stdevs[right] = sd
                    if sd > self._max_stdev:
                        self._max_stdev = sd

            self._running_stdevs = deque(stdevs, maxlen=self._max_size)

    def get_median(self) -> float:
        """Get the median of all values in the buffer."""
        with self._lock:
            if not self._values:
                return 0.0
            return float(np.median(list(self._values)))

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

    def get_last_n(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        """Get the last N samples."""
        with self._lock:
            timestamps = list(self._timestamps)[-n:]
            values = list(self._values)[-n:]
            return np.array(timestamps), np.array(values)
