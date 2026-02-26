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

        This should be called periodically from the processing thread.
        """
        with self._lock:
            if len(self._values) < 2:
                self._running_stdevs.clear()
                return

            timestamps = np.array(self._timestamps)
            values = np.array(self._values)
            stdevs = []

            for i in range(len(values)):
                t = timestamps[i]
                # Find samples within the window
                mask = (timestamps >= t - window_seconds) & (timestamps <= t)
                window_data = values[mask]
                if len(window_data) > 1:
                    sd = float(np.std(window_data, ddof=1))
                    stdevs.append(sd)
                    if sd > self._max_stdev:
                        self._max_stdev = sd
                else:
                    stdevs.append(0.0)

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
