"""Seismometer serial port interface.

Reads data from USB seismometer AD-converters (e.g., Mindsets SEP-064)
at a configurable sampling rate (default 20 Hz).
"""

import time
import logging
import threading
from typing import Optional, Callable
from collections import deque

logger = logging.getLogger(__name__)


class Seismometer:
    """Seismometer data acquisition via serial port.

    Reads numeric values separated by CR+LF at the configured
    sampling frequency.
    """

    def __init__(self, port: str = "", frequency_hz: float = 20.0,
                 offset: int = 300, data_range: int = 2000):
        self._port = port
        self._frequency_hz = frequency_hz
        self._offset = offset
        self._range = data_range
        self._serial = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None
        self._data_buffer: deque[float] = deque(maxlen=int(frequency_hz * 60))
        self._lock = threading.Lock()
        self._actual_frequency: float = 0.0

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def range(self) -> int:
        return self._range

    @property
    def actual_frequency(self) -> float:
        return self._actual_frequency

    def set_callback(self, callback: Callable):
        """Set callback function for new data: callback(timestamp, values_list)."""
        self._callback = callback

    def start(self) -> bool:
        """Start reading from serial port."""
        try:
            import serial
            self._serial = serial.Serial(
                port=self._port,
                baudrate=9600,
                timeout=1.0,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            self._running = True
            self._thread = threading.Thread(
                target=self._read_loop, daemon=True, name="Seismometer"
            )
            self._thread.start()
            logger.info(f"Seismometer started on {self._port} at {self._frequency_hz} Hz")
            return True
        except ImportError:
            logger.error("pyserial not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to open serial port {self._port}: {e}")
            return False

    def stop(self):
        """Stop reading from serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        logger.info("Seismometer stopped")

    def _read_loop(self):
        """Background read loop."""
        buffer = b''
        values = []
        freq_start = time.time()
        freq_count = 0

        while self._running and self._serial:
            try:
                data = self._serial.read(self._serial.in_waiting or 1)
                if not data:
                    continue

                buffer += data
                # Parse values separated by CR+LF
                while b'\r\n' in buffer:
                    line, buffer = buffer.split(b'\r\n', 1)
                    line_str = line.decode('ascii', errors='ignore').strip()
                    if line_str:
                        try:
                            raw_val = float(line_str)
                            offset_val = raw_val - self._offset
                            values.append(offset_val)
                            freq_count += 1

                            with self._lock:
                                self._data_buffer.append(offset_val)
                        except ValueError:
                            pass

                # Deliver values at the expected frequency
                if len(values) >= self._frequency_hz:
                    now = time.time()
                    if self._callback:
                        self._callback(now, values.copy())
                    values.clear()

                    # Update actual frequency
                    elapsed = now - freq_start
                    if elapsed > 0:
                        self._actual_frequency = freq_count / elapsed
                    if elapsed > 10:
                        freq_start = now
                        freq_count = 0

            except Exception as e:
                logger.error(f"Seismometer read error: {e}")
                time.sleep(0.1)

    def get_recent_data(self, n: int = 100) -> list[float]:
        """Get the last N data points."""
        with self._lock:
            return list(self._data_buffer)[-n:]

    @staticmethod
    def list_ports() -> list[str]:
        """List available serial ports."""
        try:
            import serial.tools.list_ports
            return [p.device for p in serial.tools.list_ports.comports()]
        except ImportError:
            return []
