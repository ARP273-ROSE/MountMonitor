"""Simulated seismometer for testing without hardware.

Generates realistic seismic data with background noise,
occasional events, and configurable characteristics.
"""

import time
import math
import random
import threading
from typing import Optional, Callable


class SimulatedSeismometer:
    """Simulated seismometer data source.

    Generates data at the configured frequency with:
    - Background microseismic noise
    - Occasional larger events (simulated traffic/wind)
    - Configurable amplitude and frequency content
    """

    def __init__(self, frequency_hz: float = 20.0,
                 offset: int = 300, data_range: int = 2000):
        self._frequency_hz = frequency_hz
        self._offset = offset
        self._range = data_range
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None

        # Simulation parameters
        self._background_amplitude = 50.0
        self._event_probability = 0.001  # Probability per sample of an event
        self._event_amplitude = 500.0
        self._event_decay = 0.95

    @property
    def actual_frequency(self) -> float:
        return self._frequency_hz

    def set_callback(self, callback: Callable):
        """Set callback: callback(timestamp, values_list)."""
        self._callback = callback

    def start(self) -> bool:
        self._running = True
        self._thread = threading.Thread(
            target=self._generate_loop, daemon=True, name="SimSeismometer"
        )
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _generate_loop(self):
        """Generate simulated seismic data."""
        interval = 1.0 / self._frequency_hz
        sample_num = 0
        event_active = False
        event_amp = 0.0
        batch = []
        batch_size = int(self._frequency_hz)  # Deliver one second at a time

        while self._running:
            t = sample_num / self._frequency_hz

            # Background noise: mix of frequencies
            value = (
                self._background_amplitude * 0.5 * math.sin(2 * math.pi * 0.15 * t)  # Microseismic ~0.15 Hz
                + self._background_amplitude * 0.3 * math.sin(2 * math.pi * 1.2 * t + 0.5)  # Cultural noise
                + self._background_amplitude * 0.2 * math.sin(2 * math.pi * 4.5 * t + 1.3)  # Higher freq
                + random.gauss(0, self._background_amplitude * 0.1)  # White noise
            )

            # Occasional events
            if not event_active and random.random() < self._event_probability:
                event_active = True
                event_amp = self._event_amplitude * random.uniform(0.3, 1.0)

            if event_active:
                value += event_amp * math.sin(2 * math.pi * 2.0 * t)
                event_amp *= self._event_decay
                if event_amp < 1.0:
                    event_active = False

            # Add offset (simulating raw AD converter output)
            raw_value = value + self._offset
            batch.append(value)  # Offset-corrected value

            sample_num += 1

            if len(batch) >= batch_size:
                if self._callback:
                    self._callback(time.time(), batch.copy())
                batch.clear()

            time.sleep(interval)
