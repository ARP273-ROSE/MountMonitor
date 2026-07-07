"""Mount polling engine.

Runs in a QThread, periodically queries the mount for RA, DEC, time,
status, and axial data. Emits signals for the GUI to consume.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QMutex

from .mount_connection import MountConnection
from .data_processor import DataProcessor
from ..models.mount_data import MountSample, TimeSample, MountStatus, PierSide, EnvironmentSample
from ..utils.coordinates import parse_ra, parse_dec

logger = logging.getLogger(__name__)


class MountPoller(QThread):
    """Background thread that polls the mount at a configurable frequency.

    Signals:
        sample_ready: Emitted when a new mount sample is processed
        time_sample_ready: Emitted when new time data is available
        status_changed: Emitted when mount status changes
        connection_lost: Emitted when connection is lost
        connection_restored: Emitted when connection is restored
        error: Emitted on error with message string
        mount_info_ready: Emitted once at startup with session info
    """

    sample_ready = pyqtSignal(object)       # MountSample
    time_sample_ready = pyqtSignal(object)  # TimeSample
    status_changed = pyqtSignal(object)     # MountStatus
    environment_ready = pyqtSignal(object)  # EnvironmentSample
    connection_lost = pyqtSignal()
    connection_restored = pyqtSignal()
    error = pyqtSignal(str)
    mount_info_ready = pyqtSignal(dict)     # Session info dict
    log_message = pyqtSignal(str)           # Log message for status panel

    def __init__(self, connection: MountConnection, processor: DataProcessor,
                 frequency_hz: float = 2.0, parent=None):
        super().__init__(parent)
        self._connection = connection
        self._processor = processor
        self._frequency_hz = max(0.1, frequency_hz)
        self._running = False
        self._paused = False
        self._mutex = QMutex()

        self._last_status = MountStatus.UNKNOWN
        self._last_mount_time: Optional[str] = None
        self._last_mount_time_parsed: Optional[float] = None
        self._last_pc_time_for_loop: Optional[float] = None
        self._delay_after_slew = 0.0
        self._slew_delay_active = False
        self._slew_delay_start = 0.0
        self._log_tracking_only = False
        self._axial_enabled = False
        self._last_env_poll: float = 0.0
        self._env_poll_interval: float = 30.0  # Poll environment every 30 seconds

    def set_frequency(self, hz: float):
        """Set polling frequency in Hz."""
        self._frequency_hz = max(0.1, min(hz, 20.0))

    def set_delay_after_slew(self, seconds: float):
        """Set delay to wait after slewing before resuming logging."""
        self._delay_after_slew = seconds

    def set_log_tracking_only(self, tracking_only: bool):
        """Set whether to only log when tracking."""
        self._log_tracking_only = tracking_only

    def set_axial_enabled(self, enabled: bool):
        """Enable/disable axial position queries."""
        self._axial_enabled = enabled

    def run(self):
        """Main polling loop."""
        self._running = True
        logger.info(f"Poller started at {self._frequency_hz} Hz")

        # Initial mount info retrieval
        self._retrieve_mount_info()

        interval = 1.0 / self._frequency_hz
        last_stdev_compute = 0.0

        while self._running:
            loop_start = time.perf_counter()

            if self._paused:
                time.sleep(0.1)
                continue

            if not self._connection.connected:
                self.connection_lost.emit()
                # Try to reconnect
                if hasattr(self._connection, 'reconnect'):
                    if self._connection.reconnect():
                        self.connection_restored.emit()
                        self.log_message.emit("Connection restored")
                    else:
                        time.sleep(2.0)
                        continue
                else:
                    time.sleep(2.0)
                    continue

            try:
                # Poll sequence: status, time, RA, DEC (+ optional axial)
                sample = self._poll_sequence()

                if sample is not None:
                    # Check for slew delay
                    if self._slew_delay_active:
                        elapsed = time.time() - self._slew_delay_start
                        if elapsed < self._delay_after_slew:
                            # continue sauterait le sleep de cadencement en
                            # fin de boucle → polling à vitesse max contre la
                            # monture. Dormir le reliquat d'abord.
                            self._sleep_remainder(loop_start, interval)
                            continue
                        else:
                            self._slew_delay_active = False
                            # After slew: check mount settings (like Java)
                            self._check_mount_settings_after_slew()

                    # Skip if only logging tracking and mount isn't tracking
                    if self._log_tracking_only and sample.status != MountStatus.TRACKING:
                        self._sleep_remainder(loop_start, interval)
                        continue

                    # Process sample
                    processed = self._processor.process_mount_sample(sample)
                    self.sample_ready.emit(processed)

                    # Compute STDEVs periodically (every 10 samples)
                    if self._processor.sample_count % 10 == 0:
                        now = time.perf_counter()
                        if now - last_stdev_compute > 1.0:
                            self._processor.compute_stdevs()
                            last_stdev_compute = now

                    # Poll environment data at low frequency (every 30s)
                    now_env = time.perf_counter()
                    if now_env - self._last_env_poll > self._env_poll_interval:
                        self._last_env_poll = now_env
                        try:
                            env_sample = self._connection.get_environment()
                            self.environment_ready.emit(env_sample)
                        except Exception as e:
                            logger.debug(f"Environment poll error: {e}")

            except Exception as e:
                logger.error(f"Polling error: {e}")
                self.error.emit(str(e))

            # Precise timing
            elapsed = time.perf_counter() - loop_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info("Poller stopped")

    @staticmethod
    def _sleep_remainder(loop_start: float, interval: float) -> None:
        """Dort ce qui reste de l'intervalle de polling courant."""
        sleep_time = interval - (time.perf_counter() - loop_start)
        if sleep_time > 0:
            time.sleep(sleep_time)

    @staticmethod
    def _parse_mount_time_to_seconds(time_str: str) -> Optional[float]:
        """Parse HH:MM:SS or HH:MM:SS.dd to seconds since midnight."""
        try:
            parts = time_str.strip().split(':')
            if len(parts) < 3:
                return None
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h * 3600.0 + m * 60.0 + s
        except (ValueError, IndexError):
            return None

    def _poll_sequence(self) -> Optional[MountSample]:
        """Execute one full polling sequence.

        Sequence: status → time → RA → DEC (+ optional axial).
        Computes PC-mount time difference and loop times.
        """
        now = datetime.now()
        pc_time = time.time()
        # Use same timezone as the mount for time diff computation:
        # - ASCOM: UTCDate returns UTC → use PC UTC
        # - LX200: :GL# returns local time → use PC local time
        if self._connection.mount_time_is_utc:
            pc_ref = datetime.now(timezone.utc)
        else:
            pc_ref = now
        pc_seconds = pc_ref.hour * 3600.0 + pc_ref.minute * 60.0 + pc_ref.second + pc_ref.microsecond / 1e6

        # Get status
        status = self._connection.get_status()
        if status != self._last_status:
            self._last_status = status
            self.status_changed.emit(status)
            if status == MountStatus.SLEWING:
                self._slew_delay_active = True
                self._slew_delay_start = time.time()
                self.log_message.emit("Mount is slewing...")

        # Get mount time
        mount_time_str = self._connection.get_mount_time()

        # Compute time differences
        if mount_time_str:
            mount_seconds = self._parse_mount_time_to_seconds(mount_time_str)
            if mount_seconds is not None:
                # PC - Mount difference in milliseconds (same timezone)
                diff_ms = (pc_seconds - mount_seconds) * 1000.0
                # Handle day wrap-around
                if diff_ms > 43200000:
                    diff_ms -= 86400000
                elif diff_ms < -43200000:
                    diff_ms += 86400000

                # Compute loop times
                pc_loop_ms = 0.0
                mount_loop_ms = 0.0
                if self._last_pc_time_for_loop is not None:
                    pc_loop_ms = (pc_time - self._last_pc_time_for_loop) * 1000.0

                if self._last_mount_time_parsed is not None:
                    mount_dt = mount_seconds - self._last_mount_time_parsed
                    if mount_dt < -43200:
                        mount_dt += 86400
                    mount_loop_ms = mount_dt * 1000.0

                time_sample = TimeSample(
                    timestamp=now,
                    mount_time_str=mount_time_str,
                    pc_mount_diff_ms=diff_ms,
                    pc_loop_time_ms=pc_loop_ms,
                    mount_loop_time_ms=mount_loop_ms,
                )
                self.time_sample_ready.emit(time_sample)

                self._last_mount_time_parsed = mount_seconds

        self._last_pc_time_for_loop = pc_time
        self._last_mount_time = mount_time_str

        # Get RA
        ra_str = self._connection.get_ra()
        if ra_str is None:
            return None
        ra_hours = parse_ra(ra_str)
        if ra_hours is None:
            logger.warning(f"Failed to parse RA: {ra_str}")
            return None

        # Get DEC
        dec_str = self._connection.get_dec()
        if dec_str is None:
            return None
        dec_degrees = parse_dec(dec_str)
        if dec_degrees is None:
            logger.warning(f"Failed to parse DEC: {dec_str}")
            return None

        # Build sample
        sample = MountSample(
            timestamp=now,
            mount_time_str=mount_time_str or "",
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
            ra_raw_str=ra_str,
            dec_raw_str=dec_str,
            status=status,
        )

        # Optional axial data
        if self._axial_enabled:
            sample.ra_axis_position = self._connection.get_ra_axis_position()
            sample.dec_axis_position = self._connection.get_dec_axis_position()

        return sample

    def _retrieve_mount_info(self):
        """Retrieve initial mount information at startup."""
        if not self._connection.connected:
            return

        try:
            info = {
                'firmware': self._connection.get_firmware_version(),
                'product': self._connection.get_product_name(),
                'mount_id': self._connection.get_mount_id(),
                'pier_side': self._connection.get_pier_side(),
                'azimuth': self._connection.get_azimuth(),
                'altitude': self._connection.get_altitude(),
                'latitude': self._connection.get_latitude(),
                'longitude': self._connection.get_longitude(),
                'elevation': self._connection.get_elevation(),
            }
            self.mount_info_ready.emit(info)
            self.log_message.emit(
                f"Mount: {info['product']} | Firmware: {info['firmware']} | "
                f"Pier: {info['pier_side'].value}"
            )
        except Exception as e:
            logger.error(f"Failed to retrieve mount info: {e}")

    def _check_mount_settings_after_slew(self):
        """Check mount settings after slew ends (like Java checkMountSettings)."""
        try:
            warnings = self._connection.check_mount_settings()
            for warning in warnings:
                self.log_message.emit(f"WRONG SET-UP: {warning}")
                logger.warning(f"Mount settings issue: {warning}")
            if not warnings:
                self.log_message.emit("Logging started.")
        except Exception as e:
            logger.debug(f"Mount settings check failed: {e}")

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        self.wait(5000)

    def pause(self):
        """Pause polling."""
        self._paused = True

    def resume(self):
        """Resume polling."""
        self._paused = False
