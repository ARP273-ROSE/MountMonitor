"""Seismometer serial port interface.

Reads data from USB seismometer AD-converters (e.g., Mindsets SEP-064)
at a configurable sampling rate (default 20 Hz).
"""

import re
import time
import logging
import threading
from typing import Optional, Callable
from collections import deque

logger = logging.getLogger(__name__)

_FIN = re.compile(rb'\r\n|\r|\n')
_NOMBRE = re.compile(r'[-+]?\d+(?:[.,]\d+)?')


def valeur_de_ligne(ligne: bytes):
    """First number of a line from the AD converter, or None."""
    m = _NOMBRE.search(ligne.decode('ascii', errors='ignore'))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', '.'))
    except ValueError:
        return None


class Seismometer:
    """Seismometer data acquisition via serial port.

    Reads numeric values separated by CR+LF at the configured
    sampling frequency.
    """

    def __init__(self, port: str = "", frequency_hz: float = 20.0,
                 offset: int = 300, data_range: int = 2000, baudrate: int = 9600):
        self._port = port
        self._baudrate = int(baudrate or 9600)
        self.erreur: str = ""            # why start() failed, for the window
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
                baudrate=self._baudrate,
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
            self.erreur = "pyserial not installed"
            logger.error(self.erreur)
            return False
        except Exception as e:
            self.erreur = str(e)
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
        derniere_livraison = time.time()

        while self._running and self._serial:
            try:
                data = self._serial.read(self._serial.in_waiting or 1)
                if not data:
                    continue

                buffer += data
                if len(buffer) > 4096 and not _FIN.search(buffer):
                    # Wrong port or baud rate: no line ever ends. Unbounded,
                    # the buffer grew all night and every search in it
                    # cost more than the last.
                    buffer = b''
                    continue
                # One value per line. Lines may end in CR+LF, LF or CR alone
                # (only CR+LF was accepted: any other device gave nothing at
                # all, without a word); the first number on the line is taken.
                *lignes, buffer = _FIN.split(buffer)
                for line in lignes:
                    raw_val = valeur_de_ligne(line)
                    if raw_val is None:
                        continue
                    offset_val = raw_val - self._offset
                    values.append(offset_val)
                    freq_count += 1
                    with self._lock:
                        self._data_buffer.append(offset_val)

                # Deliver about once a second: at the expected count, or
                # after a second whatever the count (a device slower than
                # the setting used to deliver nothing for 20 s at a time).
                now = time.time()
                if values and (len(values) >= self._frequency_hz
                               or now - derniere_livraison >= 1.0):
                    derniere_livraison = now
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
