"""Data processing engine for MountMonitor.

Handles statistics computation, tolerance checking, FFT analysis,
and axial velocity/displacement calculations.
"""

import numpy as np
import logging
import time as time_module
from collections import deque
from typing import Optional
from datetime import datetime

from ..models.mount_data import MountSample, TimeSample, MountStatus, ToleranceState
from ..models.data_buffer import DataBuffer
from ..utils.coordinates import (
    parse_ra, parse_dec, ra_diff_arcsec, dec_diff_arcsec,
    ra_arcsec_to_time_seconds, spherical_displacement
)

logger = logging.getLogger(__name__)


class DataProcessor:
    """Central data processing engine.

    Receives raw mount data, computes deviations, statistics,
    and manages data buffers for graphing.
    """

    def __init__(self, buffer_size: int = 50000):
        # Raw value buffers for reference/median computation
        self._ra_raw_buffer = DataBuffer(buffer_size)
        self._dec_raw_buffer = DataBuffer(buffer_size)

        # Data buffers for graphs (deviation from reference in arcseconds)
        self.ra_buffer = DataBuffer(buffer_size)
        self.dec_buffer = DataBuffer(buffer_size)
        self.ra_stdev_buffer = DataBuffer(buffer_size)
        self.dec_stdev_buffer = DataBuffer(buffer_size)
        self.time_diff_buffer = DataBuffer(buffer_size)
        self.pc_loop_buffer = DataBuffer(buffer_size)
        self.mount_loop_buffer = DataBuffer(buffer_size)
        self.ntp_buffer = DataBuffer(buffer_size)
        self.seismic_buffer = DataBuffer(buffer_size)
        self.seismic_stdev_buffer = DataBuffer(buffer_size)

        # Axial data buffers
        self.ra_axis_buffer = DataBuffer(buffer_size)
        self.dec_axis_buffer = DataBuffer(buffer_size)
        self.ra_speed_raw_buffer = DataBuffer(buffer_size)
        self.dec_speed_raw_buffer = DataBuffer(buffer_size)
        self.ra_speed_avg_buffer = DataBuffer(buffer_size)
        self.dec_speed_avg_buffer = DataBuffer(buffer_size)

        # Reference values
        self._ra_reference: Optional[float] = None  # In decimal hours
        self._dec_reference: Optional[float] = None  # In decimal degrees
        self._target_ra: Optional[float] = None
        self._target_dec: Optional[float] = None
        self._reference_mode = "median"  # "median" or "target"
        self._declination_deg: float = 0.0  # Current declination for HA conversion

        # Target change detection
        self._last_ra_for_slew: Optional[float] = None
        self._last_dec_for_slew: Optional[float] = None
        self._slew_ra_threshold: float = 0.25  # hours (15 arcmin)
        self._slew_dec_threshold: float = 2.0  # degrees

        # Tolerance state
        self.tolerance_state = ToleranceState()
        self._tolerance_ra_arcsec: float = 1.5
        self._tolerance_dec_arcsec: float = 1.5
        self._tolerance_seismic_percent: float = 5.0

        # Running range
        self._running_range_seconds: float = 60.0

        # Timing
        self._last_pc_time: Optional[float] = None
        self._last_mount_time_str: Optional[str] = None
        self._sample_count: int = 0
        self._actual_frequency: float = 0.0
        self._freq_timestamps: deque[float] = deque(maxlen=100)

        # Previous axis positions for speed calculation
        self._prev_ra_axis: Optional[float] = None
        self._prev_dec_axis: Optional[float] = None
        self._prev_axis_time: Optional[float] = None
        self._ra_speed_history: deque[float] = deque(maxlen=6)
        self._dec_speed_history: deque[float] = deque(maxlen=6)

        # Running StDev window for per-sample StDev computation (like Java getStDev)
        # Window = 60 * polling_frequency samples (default 120 at 2Hz = 60s)
        self._ra_dev_window: deque[float] = deque(maxlen=200)
        self._dec_dev_window: deque[float] = deque(maxlen=200)

    def set_reference_mode(self, mode: str):
        """Set reference mode: 'median' or 'target'."""
        self._reference_mode = mode

    def set_target_coordinates(self, ra_hours: float, dec_degrees: float):
        """Set target coordinates for reference mode."""
        self._target_ra = ra_hours
        self._target_dec = dec_degrees

    def set_tolerances(self, ra_arcsec: float, dec_arcsec: float, seismic_percent: float = 5.0):
        """Set tolerance thresholds."""
        self._tolerance_ra_arcsec = ra_arcsec
        self._tolerance_dec_arcsec = dec_arcsec
        self._tolerance_seismic_percent = seismic_percent

    def set_running_range(self, seconds: float):
        """Set running range for STDEV calculation."""
        self._running_range_seconds = seconds

    def process_mount_sample(self, sample: MountSample) -> MountSample:
        """Process a raw mount sample: compute deviations, update buffers.

        Returns the sample with computed fields filled in.
        """
        now = sample.timestamp.timestamp()
        self._sample_count += 1

        # Update frequency calculation
        self._freq_timestamps.append(now)
        if len(self._freq_timestamps) > 1:
            dt = self._freq_timestamps[-1] - self._freq_timestamps[0]
            if dt > 0:
                self._actual_frequency = (len(self._freq_timestamps) - 1) / dt

        # Update declination for HA calculation
        self._declination_deg = sample.dec_degrees

        # Detect target change (large position jump) and reset raw buffers
        if self._last_ra_for_slew is not None:
            ra_jump = abs(sample.ra_hours - self._last_ra_for_slew)
            if ra_jump > 12.0:
                ra_jump = 24.0 - ra_jump
            dec_jump = abs(sample.dec_degrees - self._last_dec_for_slew)
            if ra_jump > self._slew_ra_threshold or dec_jump > self._slew_dec_threshold:
                logger.info(f"Target change detected (dRA={ra_jump:.3f}h, dDEC={dec_jump:.2f}°), resetting reference buffers")
                self._ra_raw_buffer.reset()
                self._dec_raw_buffer.reset()
                self._ra_dev_window.clear()
                self._dec_dev_window.clear()
        self._last_ra_for_slew = sample.ra_hours
        self._last_dec_for_slew = sample.dec_degrees

        # Store raw values for reference computation
        self._ra_raw_buffer.append(now, sample.ra_hours)
        self._dec_raw_buffer.append(now, sample.dec_degrees)

        # Compute reference
        if self._reference_mode == "target" and self._target_ra is not None:
            ra_ref = self._target_ra
            dec_ref = self._target_dec or 0.0
        else:
            # Median of raw RA/DEC values (not deviations)
            ra_ref = self._ra_raw_buffer.get_median() if self._ra_raw_buffer.size > 0 else sample.ra_hours
            dec_ref = self._dec_raw_buffer.get_median() if self._dec_raw_buffer.size > 0 else sample.dec_degrees

        self._ra_reference = ra_ref
        self._dec_reference = dec_ref

        # Compute deviations in true arcseconds on sky (with cos(dec) correction)
        ra_dev = ra_diff_arcsec(sample.ra_hours, ra_ref, self._declination_deg)
        dec_dev = dec_diff_arcsec(sample.dec_degrees, dec_ref)
        sample.ra_deviation_arcsec = ra_dev
        sample.dec_deviation_arcsec = dec_dev

        # Store in buffers
        self.ra_buffer.append(now, ra_dev)
        self.dec_buffer.append(now, dec_dev)

        # Compute per-sample running StDev (like Java getStDev/getStDevOld)
        # Uses a sliding window of recent deviation values
        if sample.status == MountStatus.TRACKING:
            self._ra_dev_window.append(ra_dev)
            self._dec_dev_window.append(dec_dev)
            if len(self._ra_dev_window) >= 5:
                arr = np.array(self._ra_dev_window)
                sample.ra_stdev = float(np.std(arr))
            if len(self._dec_dev_window) >= 5:
                arr = np.array(self._dec_dev_window)
                sample.dec_stdev = float(np.std(arr))

        # Process axial data if available
        if sample.ra_axis_position is not None:
            self._process_axial_data(now, sample)

        # Check tolerances
        self._check_tolerances(sample)

        return sample

    def process_time_sample(self, sample: TimeSample):
        """Process a time comparison sample.

        Stores PC-mount diff, PC loop time, mount loop time, and NTP diff.
        """
        now = sample.timestamp.timestamp()
        self.time_diff_buffer.append(now, sample.pc_mount_diff_ms)
        if sample.pc_loop_time_ms > 0:
            self.pc_loop_buffer.append(now, sample.pc_loop_time_ms)
        if sample.mount_loop_time_ms > 0:
            self.mount_loop_buffer.append(now, sample.mount_loop_time_ms)
        if sample.pc_ntp_diff_ms is not None:
            self.ntp_buffer.append(now, sample.pc_ntp_diff_ms)

    def process_seismic_data(self, timestamp: float, values: list[float]):
        """Process seismometer data."""
        if not values:
            return
        for v in values:
            self.seismic_buffer.append(timestamp, v)

    def _process_axial_data(self, now: float, sample: MountSample):
        """Process axial position data: compute speeds and displacements."""
        ra_pos = sample.ra_axis_position
        dec_pos = sample.dec_axis_position

        if ra_pos is not None:
            self.ra_axis_buffer.append(now, ra_pos)
        if dec_pos is not None:
            self.dec_axis_buffer.append(now, dec_pos)

        # Compute raw speed (arcsec/s) from consecutive positions
        if self._prev_ra_axis is not None and self._prev_axis_time is not None:
            dt = now - self._prev_axis_time
            if dt > 0:
                if ra_pos is not None:
                    ra_speed = (ra_pos - self._prev_ra_axis) / dt
                    sample.ra_axis_speed = ra_speed
                    self.ra_speed_raw_buffer.append(now, ra_speed)
                    self._ra_speed_history.append(ra_speed)

                if dec_pos is not None:
                    dec_speed = (dec_pos - self._prev_dec_axis) / dt
                    sample.dec_axis_speed = dec_speed
                    self.dec_speed_raw_buffer.append(now, dec_speed)
                    self._dec_speed_history.append(dec_speed)

                # 6-sample running average
                # Les deques sont bornées à maxlen=6 : pas de slice (une deque
                # ne se slice pas — TypeError), np.mean sur l'itérable suffit.
                if len(self._ra_speed_history) >= 6:
                    avg_ra = np.mean(self._ra_speed_history)
                    self.ra_speed_avg_buffer.append(now, float(avg_ra))
                if len(self._dec_speed_history) >= 6:
                    avg_dec = np.mean(self._dec_speed_history)
                    self.dec_speed_avg_buffer.append(now, float(avg_dec))

        self._prev_ra_axis = ra_pos
        self._prev_dec_axis = dec_pos
        self._prev_axis_time = now

    def _check_tolerances(self, sample: MountSample):
        """Check if current values and running StDev exceed tolerances.

        Like Java original, checks both:
        - VALUE: absolute deviation exceeds tolerance
        - STDEV: running standard deviation exceeds tolerance
        """
        now = sample.timestamp

        # RA value tolerance
        ra_exceeded = abs(sample.ra_deviation_arcsec) > self._tolerance_ra_arcsec
        if ra_exceeded and not self.tolerance_state.ra_exceeded:
            self.tolerance_state.ra_exceeded = True
            self.tolerance_state.ra_exceeded_since = now
            logger.warning(f"RA tolerance exceeded: {sample.ra_deviation_arcsec:.2f}\"")
        elif not ra_exceeded and self.tolerance_state.ra_exceeded:
            self.tolerance_state.ra_exceeded = False
            logger.info("RA back within tolerance")

        # DEC value tolerance
        dec_exceeded = abs(sample.dec_deviation_arcsec) > self._tolerance_dec_arcsec
        if dec_exceeded and not self.tolerance_state.dec_exceeded:
            self.tolerance_state.dec_exceeded = True
            self.tolerance_state.dec_exceeded_since = now
            logger.warning(f"DEC tolerance exceeded: {sample.dec_deviation_arcsec:.2f}\"")
        elif not dec_exceeded and self.tolerance_state.dec_exceeded:
            self.tolerance_state.dec_exceeded = False
            logger.info("DEC back within tolerance")

        # RA StDev tolerance (like Java: STDEV EXCEEDED tolerance level)
        if sample.ra_stdev > 0:
            ra_stdev_exceeded = sample.ra_stdev > self._tolerance_ra_arcsec
            if ra_stdev_exceeded and not self.tolerance_state.ra_stdev_exceeded:
                self.tolerance_state.ra_stdev_exceeded = True
                logger.warning(f"RA STDEV exceeded tolerance: {sample.ra_stdev:.3f}\"")
            elif not ra_stdev_exceeded and self.tolerance_state.ra_stdev_exceeded:
                self.tolerance_state.ra_stdev_exceeded = False
                logger.info("RA STDEV back within tolerance")

        # DEC StDev tolerance
        if sample.dec_stdev > 0:
            dec_stdev_exceeded = sample.dec_stdev > self._tolerance_dec_arcsec
            if dec_stdev_exceeded and not self.tolerance_state.dec_stdev_exceeded:
                self.tolerance_state.dec_stdev_exceeded = True
                logger.warning(f"DEC STDEV exceeded tolerance: {sample.dec_stdev:.3f}\"")
            elif not dec_stdev_exceeded and self.tolerance_state.dec_stdev_exceeded:
                self.tolerance_state.dec_stdev_exceeded = False
                logger.info("DEC STDEV back within tolerance")

    def compute_stdevs(self):
        """Compute running standard deviations for all buffers.

        Should be called periodically (e.g., every N samples).
        """
        self.ra_buffer.compute_running_stdev(self._running_range_seconds)
        self.dec_buffer.compute_running_stdev(self._running_range_seconds)
        if self.seismic_buffer.size > 0:
            self.seismic_buffer.compute_running_stdev(self._running_range_seconds)

    def compute_fft(self, data: np.ndarray, sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
        """Compute FFT of data array.

        Returns (frequencies, magnitudes) arrays.
        """
        if len(data) < 4:
            return np.array([]), np.array([])

        # Remove DC component (subtract mean)
        data = data - np.mean(data)

        # Apply Hanning window to reduce spectral leakage
        window = np.hanning(len(data))
        windowed = data * window

        # Compute FFT
        n = len(windowed)
        fft_result = np.fft.rfft(windowed)
        magnitudes = 2.0 / n * np.abs(fft_result)
        frequencies = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        # Skip DC component
        return frequencies[1:], magnitudes[1:]

    @property
    def actual_frequency(self) -> float:
        """Actual polling frequency in Hz."""
        return self._actual_frequency

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def ra_reference(self) -> Optional[float]:
        return self._ra_reference

    @property
    def dec_reference(self) -> Optional[float]:
        return self._dec_reference

    def reset_buffers(self):
        """Reset all graph buffers."""
        for buf in [self._ra_raw_buffer, self._dec_raw_buffer,
                    self.ra_buffer, self.dec_buffer, self.ra_stdev_buffer,
                    self.dec_stdev_buffer, self.time_diff_buffer, self.pc_loop_buffer,
                    self.mount_loop_buffer, self.ntp_buffer, self.seismic_buffer,
                    self.seismic_stdev_buffer, self.ra_axis_buffer, self.dec_axis_buffer,
                    self.ra_speed_raw_buffer, self.dec_speed_raw_buffer,
                    self.ra_speed_avg_buffer, self.dec_speed_avg_buffer]:
            buf.reset()
        self._sample_count = 0
        self._freq_timestamps.clear()
        self._ra_dev_window.clear()
        self._dec_dev_window.clear()

    def reset_minmax(self):
        """Reset min/max values only."""
        self.ra_buffer.reset_minmax()
        self.dec_buffer.reset_minmax()
        self.seismic_buffer.reset_minmax()
