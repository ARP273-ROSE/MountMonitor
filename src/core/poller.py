"""Mount polling engine.

Runs in a QThread, periodically queries the mount for RA, DEC, time,
status, and axial data. Emits signals for the GUI to consume.
"""

import queue
import threading
import time
from ..utils.i18n import T
import logging
from datetime import datetime, timezone
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QMutex

from .mount_connection import MountConnection
from .data_processor import DataProcessor
from ..models.mount_data import (MountSample, TimeSample, MountStatus, PierSide,
                                 EnvironmentSample, ConnectionProtocol)
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
    connect_result = pyqtSignal(bool)       # First connection attempt, made in this thread
    request_done = pyqtSignal(object, object)  # (callback, result) of a submit()
    slew_settled = pyqtSignal()             # slew over AND the delay after it elapsed

    # Reconnection: 2, 4, 8, 16, 32, then every 60 s, for as long as it takes.
    RECONNECT_MAX_S = 60.0

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
        # Last RA/DEC kept, to drop the repeats of an ASCOM driver's cache.
        self._last_radec = None
        self._last_radec_t = 0.0
        self._cache_noted = False
        self._last_mount_time: Optional[str] = None
        self._last_mount_time_parsed: Optional[float] = None
        self._last_pc_time_for_loop: Optional[float] = None
        self._delay_after_slew = 0.0
        # Samples are dropped while the mount slews and for
        # delay_after_slew seconds after the slew ENDS (as MountMonitor 3
        # does): the final approach and the settling are not tracking.
        self._slewing = False
        self._settle_until: Optional[float] = None
        self._log_tracking_only = False
        self._axial_enabled = False
        self._pending_time = None     # TimeSample of the cycle, sent by the loop
        self._last_env_poll: float = 0.0
        self._env_poll_interval: float = 30.0  # Poll environment every 30 seconds
        self._wake = threading.Event()         # interrupts every wait (stop)
        self._requests: "queue.Queue" = queue.Queue()
        self._connect_first = False

    def connect_in_thread(self):
        """Open the connection in this thread, then poll (GUI never blocks)."""
        self._connect_first = True

    def submit(self, fn, callback=None):
        """Run fn(connection) in the poller thread, between two polls.

        Every mount access from the GUI goes through here: one thread talks
        to the mount (a COM object must stay in the apartment that created
        it), and a slow mount never freezes the window. callback(result) is
        called back in the GUI thread through request_done."""
        self._requests.put((fn, callback))
        self._wake.set()

    def _run_requests(self):
        while True:
            try:
                fn, callback = self._requests.get_nowait()
            except queue.Empty:
                return
            try:
                result = fn(self._connection)
            except Exception as e:
                logger.warning(f"Mount request failed: {e}")
                result = None
            if callback is not None:
                self.request_done.emit(callback, result)

    def _wait(self, seconds: float) -> None:
        """Sleep that stop() and submit() interrupt."""
        if seconds > 0:
            self._wake.wait(seconds)
            self._wake.clear()

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
        """Main polling loop (owns the connection for its whole life)."""
        self._running = True
        try:
            self._connection.thread_enter()
            if self._connect_first:
                ok = False
                try:
                    ok = bool(self._connection.connect())
                except Exception as e:
                    logger.error(f"Connection failed: {e}")
                self.connect_result.emit(ok)
                if not ok:
                    return
            self._poll_loop()
        finally:
            try:
                self._connection.disconnect()
            except Exception as e:
                logger.debug(f"Disconnect error: {e}")
            try:
                self._connection.thread_exit()
            except Exception:
                pass
            logger.info("Poller stopped")

    def _poll_loop(self):
        logger.info(f"Poller started at {self._frequency_hz} Hz")

        # Initial mount info retrieval
        self._retrieve_mount_info()

        last_stdev_compute = 0.0
        failures = 0

        while self._running:
            interval = 1.0 / self._frequency_hz
            loop_start = time.perf_counter()
            self._run_requests()

            if self._paused:
                self._wait(0.1)
                continue

            if not self._connection.connected:
                if failures == 0:
                    # Once per loss, not every 2 s.
                    self.connection_lost.emit()
                if not self._running:
                    break
                if self._connection.reconnect():
                    failures = 0
                    self.connection_restored.emit()
                    self.log_message.emit("Connection restored")
                else:
                    failures += 1
                    self._wait(min(self.RECONNECT_MAX_S, 2.0 ** min(failures, 6)))
                    continue

            try:
                # Poll sequence: status, time, RA, DEC (+ optional axial)
                self._pending_time = None
                sample = self._poll_sequence()
                pending_time, self._pending_time = self._pending_time, None

                if sample is None:
                    # (a repeated RA answer from a cache): the clock is still
                    # shown, unless a slew or its settling delay is under way
                    if (pending_time is not None and not self._slewing
                            and self._settle_until is None):
                        self.time_sample_ready.emit(pending_time)
                else:
                    if self._skip_for_slew(sample.status):
                        # continue would skip the pacing sleep at the end
                        # of the loop -> polling the mount at full speed.
                        self._sleep_remainder(loop_start, interval)
                        continue

                    if pending_time is not None:
                        self.time_sample_ready.emit(pending_time)

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
            self._sleep_remainder(loop_start, interval)

    def _skip_for_slew(self, status, now: Optional[float] = None) -> bool:
        """True while the sample must be dropped: mount slewing, or slew
        ended less than delay_after_slew seconds ago. Emits slew_settled
        once, when the delay is over (the window then checks the mount
        settings and reads the target, as MountMonitor 3 does)."""
        # monotonic: a PC clock set back during the delay lengthened it
        # by the size of the jump
        now = time.monotonic() if now is None else now
        if status == MountStatus.SLEWING:
            self._slewing = True
            self._settle_until = None
            return True
        if self._slewing:
            self._slewing = False
            delay = float(self._delay_after_slew or 0.0)
            self._settle_until = now + delay
            if delay > 0:
                self.log_message.emit(T("poller_settling").format(s=f"{delay:g}"))
        if self._settle_until is not None:
            if now < self._settle_until:
                return True
            self._settle_until = None
            self.slew_settled.emit()
        return False

    def _sleep_remainder(self, loop_start: float, interval: float) -> None:
        """Sleep for what remains of the current polling interval."""
        self._wait(interval - (time.perf_counter() - loop_start))

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

    CACHE_REPEAT_MAX_S = 5.0

    def _poll_sequence(self) -> Optional[MountSample]:
        """Execute one full polling sequence.

        Sequence: status → time → RA → DEC (+ optional axial).
        Computes PC-mount time difference and loop times.
        """
        now = datetime.now()
        pc_time = time.time()

        # Get status
        status = self._connection.get_status()
        if status != self._last_status:
            self._last_status = status
            self.status_changed.emit(status)
            if status == MountStatus.SLEWING:
                self.log_message.emit(T("poller_slewing"))

        # Get mount time. The PC reference is taken in the MIDDLE of the
        # round trip: taken before the status query, it was early by a whole
        # exchange (tens of ms) and the offset carried that bias.
        t_before = time.time()
        mount_time_str = self._connection.get_mount_time()
        t_mid = (t_before + time.time()) / 2.0
        # Same time zone as the mount: ASCOM UTCDate is UTC, LX200 :GL# local.
        if self._connection.mount_time_is_utc:
            pc_ref = datetime.fromtimestamp(t_mid, timezone.utc)
        else:
            pc_ref = datetime.fromtimestamp(t_mid)
        pc_seconds = pc_ref.hour * 3600.0 + pc_ref.minute * 60.0 + pc_ref.second + pc_ref.microsecond / 1e6

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
                # PC loop = PC time at the :GL# answer minus the previous one,
                # as in MountMonitor 3 (pcNew - pcOld). It used the start of
                # the polling cycle, set by the timer: a flat line that hid
                # the latency jitter the mount loop shows.
                if self._last_pc_time_for_loop is not None:
                    pc_loop_ms = (t_mid - self._last_pc_time_for_loop) * 1000.0

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
                # Emitted by the loop, once it knows whether the sample is
                # dropped for a slew: the time graph waits like RA/DEC.
                self._pending_time = time_sample

                self._last_mount_time_parsed = mount_seconds

        self._last_pc_time_for_loop = t_mid
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

        # ASCOM drivers may serve RA/DEC from a cache: the 10Micron driver
        # 1.7.2 refreshes it about every 2 s, so at 2 Hz three samples out
        # of four repeated the previous position, stamped with a later time
        # -- a staircase that is not the mount's. Measured with NINA on the
        # same driver (22/11/2026). A repeat is dropped; a real mount never
        # gives the same high-precision RA and DEC twice in a row for long,
        # and a sample is kept at least every CACHE_REPEAT_MAX_S anyway.
        if self._connection.protocol == ConnectionProtocol.ASCOM:
            key = (ra_str, dec_str)
            t_now = time.time()
            if key == self._last_radec and t_now - self._last_radec_t < self.CACHE_REPEAT_MAX_S:
                if not self._cache_noted:
                    self._cache_noted = True
                    self.log_message.emit(T("poller_ascom_cache"))
                return None
            self._last_radec, self._last_radec_t = key, t_now

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
            # The window prints the same facts, translated, one per line;
            # this English summary only goes to the log file.
            logger.info(f"Mount: {info['product']} | Firmware: {info['firmware']} | "
                        f"Pier: {info['pier_side'].value}")
        except Exception as e:
            logger.error(f"Failed to retrieve mount info: {e}")

    def stop(self) -> bool:
        """Stop the polling loop; True once the thread has ended.

        Sleeps are interrupted at once; a read in progress is cut by
        abort() (socket shutdown) rather than waited for. The thread closes
        the connection itself on its way out."""
        self._running = False
        self._wake.set()
        if self.wait(1500):
            return True
        self._connection.abort()
        return self.wait(4000)

    def request_stop(self) -> None:
        """Ask the loop to end, without waiting (GUI thread): the caller
        keeps the thread until `finished`, and calls abort_read() if it is
        still in a read after a moment. stop() waited up to 5.5 s, window
        frozen, whenever a driver was busy."""
        self._running = False
        self._wake.set()

    def abort_read(self) -> None:
        if self.isRunning() and self._connection is not None:
            self._connection.abort()

    def pause(self):
        """Pause polling."""
        self._paused = True

    def resume(self):
        """Resume polling."""
        self._paused = False
