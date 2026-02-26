"""NTP time synchronization client.

Replaces the original NIST raw protocol with standard NTP.
Provides PC-NTP time difference for display in the time graph.
"""

import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class NTPClient:
    """NTP client for time difference measurement.

    Runs a background thread that periodically queries an NTP server
    and reports the PC-NTP time difference in milliseconds.
    """

    def __init__(self, server: str = "time.nist.gov", interval_seconds: float = 30.0):
        self._server = server
        self._interval = interval_seconds
        self._offset_ms: Optional[float] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def offset_ms(self) -> Optional[float]:
        """Current PC-NTP time difference in milliseconds."""
        with self._lock:
            return self._offset_ms

    @property
    def server(self) -> str:
        return self._server

    def start(self):
        """Start the NTP polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="NTPClient")
        self._thread.start()
        logger.info(f"NTP client started, server: {self._server}, interval: {self._interval}s")

    def stop(self):
        """Stop the NTP polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("NTP client stopped")

    def _poll_loop(self):
        """Background polling loop."""
        while self._running:
            try:
                self._query_ntp()
            except Exception as e:
                logger.warning(f"NTP query failed: {e}")
                with self._lock:
                    self._offset_ms = None

            # Sleep in small increments to allow quick shutdown
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _query_ntp(self):
        """Query NTP server and compute offset."""
        try:
            import ntplib
            client = ntplib.NTPClient()
            response = client.request(self._server, version=3, timeout=5)
            offset = response.offset * 1000.0  # Convert to milliseconds
            with self._lock:
                self._offset_ms = offset
            logger.debug(f"NTP offset: {offset:.1f} ms")
        except ImportError:
            logger.warning("ntplib not installed, NTP sync unavailable")
            self._running = False
        except Exception as e:
            logger.debug(f"NTP query error: {e}")
            raise

    def query_once(self) -> Optional[float]:
        """Perform a single NTP query. Returns offset in ms or None."""
        try:
            self._query_ntp()
            return self.offset_ms
        except Exception:
            return None

    def set_server(self, server: str):
        """Change the NTP server address."""
        self._server = server

    def set_interval(self, interval_seconds: float):
        """Change the polling interval."""
        self._interval = max(10.0, interval_seconds)  # Minimum 10s
