"""File logging system for MountMonitor.

Creates and manages 6 log file types:
  .log  - Events, settings changes, tolerance alerts
  .dat  - RA/DEC data (TAB-separated, 27-column Java-compatible format)
  .dti  - Time data (TAB-separated)
  .sei  - Seismometer data (TAB-separated)
  .fft  - FFT analysis snapshots (TAB-separated)
  .env  - Environment/diagnostics data (temperature, pressure, alignment)

Files are named: MountMonitor_YYYYMMDD-HHMMSS.ext
Stored in a Logs/ subdirectory.
"""

import os
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from ..models.mount_data import MountSample, MountStatus, TimeSample, SessionInfo, EnvironmentSample, PierSide
from ..utils.coordinates import format_ra, format_dec

logger = logging.getLogger(__name__)

# Version string
_APP_VERSION = "1.0.0"


def _read_version() -> str:
    """Read version from VERSION file."""
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return _APP_VERSION


class FileLogger:
    """Manages the 4 log files for a monitoring session.

    Uses atomic writes via temp files for data files.
    Log file is flushed after each write for immediate visibility.
    The .dat file outputs 27 TAB-separated columns matching the Java original.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            # Les fichiers d'une nuit d'acquisition ne vivent pas dans le
            # dossier d'installation : il est efface a chaque mise a jour.
            from ..config.paths import dossier_journaux
            base_dir = dossier_journaux()
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._log_file: Optional[TextIO] = None
        self._dat_file: Optional[TextIO] = None
        self._dti_file: Optional[TextIO] = None
        self._sei_file: Optional[TextIO] = None
        self._fft_file: Optional[TextIO] = None
        self._env_file: Optional[TextIO] = None
        self._session_start: Optional[str] = None
        self._version = _read_version()
        self._active = False

        # Running min/max tracking for .dat 27-column format (ALL samples)
        self._sample_count: int = 0
        self._min_ra_hours: Optional[float] = None
        self._max_ra_hours: Optional[float] = None
        self._max_ra_stdev: float = 0.0
        self._min_dec_degrees: Optional[float] = None
        self._max_dec_degrees: Optional[float] = None
        self._max_dec_stdev: float = 0.0
        self._min_ra_axis: Optional[float] = None
        self._max_ra_axis: Optional[float] = None
        self._max_ra_axis_stdev: float = 0.0
        self._min_dec_axis: Optional[float] = None
        self._max_dec_axis: Optional[float] = None
        self._max_dec_axis_stdev: float = 0.0

        # Buffered flush: avoid flushing every single write (perf on NAS)
        self._write_count: int = 0
        self._flush_interval: int = 20  # Flush every N writes

        # Tracking-only statistics for session summary
        self._tracking_count: int = 0
        self._tracking_min_ra: Optional[float] = None
        self._tracking_max_ra: Optional[float] = None
        self._tracking_max_ra_stdev: float = 0.0
        self._tracking_min_dec: Optional[float] = None
        self._tracking_max_dec: Optional[float] = None
        self._tracking_max_dec_stdev: float = 0.0
        self._slewing_count: int = 0
        self._parked_count: int = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def log_dir(self) -> Path:
        return self._base_dir

    @staticmethod
    def _sanitize(text: str) -> str:
        """Sanitize user-supplied text for log file headers.

        Removes newlines, tabs and control characters to prevent log injection.
        """
        if not text:
            return ""
        return text.replace('\n', ' ').replace('\r', '').replace('\t', ' ').strip()

    def _safe_write(self, file_obj: Optional[TextIO], data: str) -> bool:
        """Write data to a file, handling transient I/O errors (NAS hiccups).

        Returns True on success, False on failure.
        Flushes periodically (every _flush_interval writes) to balance
        I/O performance vs data safety.
        """
        if not file_obj:
            return False
        try:
            file_obj.write(data)
            self._write_count += 1
            if self._write_count >= self._flush_interval:
                self._flush_all()
                self._write_count = 0
            return True
        except OSError as e:
            if not getattr(self, '_io_error_logged', False):
                logger.warning(f"I/O error writing log data: {e}")
                self._io_error_logged = True
            return False

    def _flush_all(self):
        """Flush all open log files to disk."""
        for f in [self._log_file, self._dat_file, self._dti_file,
                  self._sei_file, self._fft_file, self._env_file]:
            if f:
                try:
                    f.flush()
                except OSError:
                    pass

    def _reset_minmax(self):
        """Reset running min/max statistics."""
        self._sample_count = 0
        self._min_ra_hours = None
        self._max_ra_hours = None
        self._max_ra_stdev = 0.0
        self._min_dec_degrees = None
        self._max_dec_degrees = None
        self._max_dec_stdev = 0.0
        self._min_ra_axis = None
        self._max_ra_axis = None
        self._max_ra_axis_stdev = 0.0
        self._min_dec_axis = None
        self._max_dec_axis = None
        self._max_dec_axis_stdev = 0.0
        # Tracking-only
        self._tracking_count = 0
        self._tracking_min_ra = None
        self._tracking_max_ra = None
        self._tracking_max_ra_stdev = 0.0
        self._tracking_min_dec = None
        self._tracking_max_dec = None
        self._tracking_max_dec_stdev = 0.0
        self._slewing_count = 0
        self._parked_count = 0

    def _update_minmax(self, sample: MountSample):
        """Update running min/max from a mount sample."""
        self._sample_count += 1

        # RA min/max (decimal hours)
        if self._min_ra_hours is None or sample.ra_hours < self._min_ra_hours:
            self._min_ra_hours = sample.ra_hours
        if self._max_ra_hours is None or sample.ra_hours > self._max_ra_hours:
            self._max_ra_hours = sample.ra_hours

        # RA StDev max
        if sample.ra_stdev > self._max_ra_stdev:
            self._max_ra_stdev = sample.ra_stdev

        # DEC min/max (decimal degrees)
        if self._min_dec_degrees is None or sample.dec_degrees < self._min_dec_degrees:
            self._min_dec_degrees = sample.dec_degrees
        if self._max_dec_degrees is None or sample.dec_degrees > self._max_dec_degrees:
            self._max_dec_degrees = sample.dec_degrees

        # DEC StDev max
        if sample.dec_stdev > self._max_dec_stdev:
            self._max_dec_stdev = sample.dec_stdev

        # RA axis min/max
        if sample.ra_axis_position is not None:
            if self._min_ra_axis is None or sample.ra_axis_position < self._min_ra_axis:
                self._min_ra_axis = sample.ra_axis_position
            if self._max_ra_axis is None or sample.ra_axis_position > self._max_ra_axis:
                self._max_ra_axis = sample.ra_axis_position

        # DEC axis min/max
        if sample.dec_axis_position is not None:
            if self._min_dec_axis is None or sample.dec_axis_position < self._min_dec_axis:
                self._min_dec_axis = sample.dec_axis_position
            if self._max_dec_axis is None or sample.dec_axis_position > self._max_dec_axis:
                self._max_dec_axis = sample.dec_axis_position

    def _update_tracking_stats(self, sample: MountSample):
        """Update tracking-only statistics for session summary."""
        if sample.status == MountStatus.TRACKING:
            self._tracking_count += 1
            if self._tracking_min_ra is None or sample.ra_hours < self._tracking_min_ra:
                self._tracking_min_ra = sample.ra_hours
            if self._tracking_max_ra is None or sample.ra_hours > self._tracking_max_ra:
                self._tracking_max_ra = sample.ra_hours
            if sample.ra_stdev > self._tracking_max_ra_stdev:
                self._tracking_max_ra_stdev = sample.ra_stdev
            if self._tracking_min_dec is None or sample.dec_degrees < self._tracking_min_dec:
                self._tracking_min_dec = sample.dec_degrees
            if self._tracking_max_dec is None or sample.dec_degrees > self._tracking_max_dec:
                self._tracking_max_dec = sample.dec_degrees
            if sample.dec_stdev > self._tracking_max_dec_stdev:
                self._tracking_max_dec_stdev = sample.dec_stdev
        elif sample.status == MountStatus.SLEWING:
            self._slewing_count += 1
        elif sample.status == MountStatus.PARKED:
            self._parked_count += 1

    def start_session(self, session_info: SessionInfo):
        """Open new log files for a monitoring session."""
        self._session_start = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = f"MountMonitor_{self._session_start}"
        self._reset_minmax()
        self._session_info = session_info

        try:
            # .log file
            self._log_file = open(
                self._base_dir / f"{prefix}.log", 'w', encoding='utf-8'
            )
            self._write_log_header(session_info)

            # .dat file
            self._dat_file = open(
                self._base_dir / f"{prefix}.dat", 'w', encoding='utf-8'
            )
            self._write_dat_header(session_info)

            # .dti file
            self._dti_file = open(
                self._base_dir / f"{prefix}.dti", 'w', encoding='utf-8'
            )
            self._write_dti_header(session_info)

            # .sei file
            self._sei_file = open(
                self._base_dir / f"{prefix}.sei", 'w', encoding='utf-8'
            )
            self._write_sei_header(session_info)

            # .fft file
            self._fft_file = open(
                self._base_dir / f"{prefix}.fft", 'w', encoding='utf-8'
            )
            self._write_fft_header(session_info)

            # .env file (environment/diagnostics)
            self._env_file = open(
                self._base_dir / f"{prefix}.env", 'w', encoding='utf-8'
            )
            self._write_env_header(session_info)

            self._active = True
            self.log_event("Logging started.")
            logger.info(f"Log files created: {prefix}.*")

        except OSError as e:
            logger.error(f"Failed to create log files: {e}")
            self.close()

    def _write_log_header(self, info: SessionInfo):
        """Write .log file header. All user-supplied fields are sanitized."""
        f = self._log_file
        f.write(f"MountMonitor logfile (v.{self._version})\n")
        f.write(f"Location:\t{self._sanitize(info.observatory)}\n")
        if info.latitude:
            f.write(f"Position:\tLatitude = {self._sanitize(str(info.latitude))}\t"
                    f"Longitude = {self._sanitize(str(info.longitude))}\t"
                    f"Elevation = {info.elevation}m\n")
        f.write(f"Mount:\t{self._sanitize(info.mount_name)}\n")
        f.write(f"Mount ID:\t{self._sanitize(info.mount_id)}\n")
        if info.mount_driver:
            f.write(f"Mount driver:\t{self._sanitize(info.mount_driver)}\n")
        f.write(f"Firmware:\t{self._sanitize(info.firmware)}\n")
        f.write(f"Protocol:\t{info.protocol.value}\n")
        f.flush()

    def _write_dat_header(self, info: SessionInfo):
        """Write .dat file header with Java-compatible 27-column format.
        All user-supplied fields are sanitized."""
        f = self._dat_file
        f.write(f"MountMonitor mount data file (v.{self._version})\n")
        f.write(f"Location:\t{self._sanitize(info.observatory)}\n")
        f.write(f"Mount:\t{self._sanitize(info.mount_name)}\n")
        f.write(f"Mount ID:\t{self._sanitize(info.mount_id)}\n")
        f.write(f"Firmware:\t{self._sanitize(info.firmware)}\n")

        # Telescope pointing info (pier side, azimuth, altitude)
        pier_side_str = info.pier_side.value if info.pier_side else "Unknown"
        f.write(f"Telescopes are {pier_side_str} of the mount, "
                f"pointing at azimuth {info.azimuth:.1f}, "
                f"altitude {info.altitude:.1f}\n")

        # 27 column headers (TAB-separated) matching Java original
        headers = [
            "RAW Mount time [HH:MM:SS.dd]",      # 1
            "Mount time [HH:MM:SS.dd]",           # 2
            "RAW RA [hh:mm:ss.dd]",               # 3
            "RA [hh:mm:ss.dd]",                   # 4
            "RA StDev [\".ddd]",                   # 5
            "RAW DEC [dd:mm:ss.dd]",              # 6
            "DEC [dd:mm:ss.dd]",                  # 7
            "DEC StDev [\".ddd]",                  # 8
            "RAW DEC AXIS [dd.dddd]",             # 9
            "DEC AXIS [dd.dddd]",                 # 10
            "DEC AXIS StDev [\".ddd]",             # 11
            "RAW RA AXIS [dd.dddd]",              # 12
            "RA AXIS [dd.dddd]",                  # 13
            "RA AXIS StDev [\".ddd]",              # 14
            "Min RA Value [hh:mm:ss.dd]",         # 15
            "Max RA Value [hh:mm:ss.dd]",         # 16
            "Max RA StDev [\".ddd]",               # 17
            "Min DEC value [dd:mm:ss.dd]",        # 18
            "Max DEC value [dd:mm:ss.dd]",        # 19
            "Max DEC StDev [\".ddd]",              # 20
            "Min RA AXIS Value [dd.dddd]",        # 21
            "Max RA AXIS Value [dd.dddd]",        # 22
            "Max RA AXIS StDev [\".ddd]",          # 23
            "Min DEC AXIS Value [dd.dddd]",       # 24
            "Max DEC AXIS Value [dd.dddd]",       # 25
            "Max DEC AXIS StDev [\".ddd]",         # 26
            "Status",                              # 27
        ]
        f.write("\t".join(headers) + "\n")
        f.flush()

    def _write_dti_header(self, info: SessionInfo):
        """Write .dti file header."""
        f = self._dti_file
        f.write(f"MountMonitor time data file (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        f.write("Mount time\tPC-Mount diff [ms]\t"
                "PC loop time [ms]\tMount loop time [ms]\t"
                "PC-NTP diff [ms]\n")
        f.flush()

    def _write_sei_header(self, info: SessionInfo):
        """Write .sei file header."""
        f = self._sei_file
        f.write(f"MountMonitor seismometer data file (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        f.write("Timestamp\tRaw data\tOffset data\tStDev\n")
        f.flush()

    def _write_fft_header(self, info: SessionInfo):
        """Write .fft file header."""
        f = self._fft_file
        f.write(f"MountMonitor FFT data file (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        f.write(f"Mount:\t{info.mount_name}\n")
        f.write("Timestamp\tAxis\tSample Rate [Hz]\tNum Bins\t"
                "Peak1 Freq [Hz]\tPeak1 Period [s]\tPeak1 Amp\t"
                "Peak2 Freq [Hz]\tPeak2 Period [s]\tPeak2 Amp\t"
                "Peak3 Freq [Hz]\tPeak3 Period [s]\tPeak3 Amp\n")
        f.flush()

    def _write_env_header(self, info: SessionInfo):
        """Write .env file header."""
        f = self._env_file
        f.write(f"MountMonitor environment data file (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        f.write(f"Mount:\t{info.mount_name}\n")
        f.write("Timestamp\tTemp Ext [°C]\tPressure [mbar]\tTemp Int [°C]\t"
                "Status Code\tTracking Rate\tMeridian Flip [min]\tPier Side\t"
                "Align Stars\tAlign RMS [\"]\tPolar Error [°]\n")
        f.flush()

    def log_environment(self, sample: EnvironmentSample):
        """Write an environment data point to the .env file."""
        if not self._env_file:
            return
        ts = sample.timestamp.strftime("%H:%M:%S")
        temp_ext = f"{sample.temperature_ext:.1f}" if sample.temperature_ext is not None else ""
        pressure = f"{sample.pressure:.1f}" if sample.pressure is not None else ""
        temp_int = f"{sample.temperature_int:.1f}" if sample.temperature_int is not None else ""
        status = str(sample.mount_status_code) if sample.mount_status_code is not None else ""
        rate = f"{sample.tracking_rate:.1f}" if sample.tracking_rate is not None else ""
        flip = f"{sample.meridian_flip_minutes:.1f}" if sample.meridian_flip_minutes is not None else ""
        pier = sample.pier_side.value if sample.pier_side != PierSide.UNKNOWN else ""
        stars = str(sample.alignment_stars) if sample.alignment_stars is not None else ""
        rms = f"{sample.alignment_rms:.1f}" if sample.alignment_rms is not None else ""
        polar = f"{sample.polar_error_deg:.4f}" if sample.polar_error_deg is not None else ""

        line = f"{ts}\t{temp_ext}\t{pressure}\t{temp_int}\t{status}\t{rate}\t{flip}\t{pier}\t{stars}\t{rms}\t{polar}\n"
        self._safe_write(self._env_file, line)

    def log_event(self, message: str):
        """Write an event to the .log file.

        Sanitize message to prevent log injection (newlines, tabs).
        Flush is handled periodically by _safe_write.
        """
        if not self._log_file:
            return
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
        safe_msg = self._sanitize(message)
        self._safe_write(self._log_file, f"{timestamp}\t{safe_msg}\n")

    def log_tolerance_event(self, message: str):
        """Write a tolerance alert event to the .log file."""
        if not self._log_file:
            return
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
        safe_msg = self._sanitize(message)
        self._safe_write(self._log_file, f"{timestamp}\tTOLERANCE\t{safe_msg}\n")

    def log_mount_sample(self, sample: MountSample):
        """Write a mount data sample to the .dat file (27-column Java format).

        Columns:
         1  RAW Mount time       - mount_time_str (raw from mount)
         2  Mount time           - mount_time_str (same, no correction applied yet)
         3  RAW RA               - ra_raw_str
         4  RA                   - formatted from ra_hours
         5  RA StDev             - ra_stdev
         6  RAW DEC              - dec_raw_str
         7  DEC                  - formatted from dec_degrees
         8  DEC StDev            - dec_stdev
         9  RAW DEC AXIS         - dec_axis_position (raw)
        10  DEC AXIS             - dec_axis_position (same, no correction)
        11  DEC AXIS StDev       - empty (not computed per-sample)
        12  RAW RA AXIS          - ra_axis_position (raw)
        13  RA AXIS              - ra_axis_position (same, no correction)
        14  RA AXIS StDev        - empty (not computed per-sample)
        15  Min RA Value         - running min RA formatted
        16  Max RA Value         - running max RA formatted
        17  Max RA StDev         - running max of ra_stdev
        18  Min DEC value        - running min DEC formatted
        19  Max DEC value        - running max DEC formatted
        20  Max DEC StDev        - running max of dec_stdev
        21  Min RA AXIS Value    - running min ra_axis_position
        22  Max RA AXIS Value    - running max ra_axis_position
        23  Max RA AXIS StDev    - running max (0 since not computed per-sample)
        24  Min DEC AXIS Value   - running min dec_axis_position
        25  Max DEC AXIS Value   - running max dec_axis_position
        26  Max DEC AXIS StDev   - running max (0 since not computed per-sample)
        27  Status               - status name
        """
        if not self._dat_file:
            return

        # Update running min/max (all samples, for .dat columns 15-26)
        self._update_minmax(sample)

        # Update tracking-only stats (for session summary)
        self._update_tracking_stats(sample)

        # Column 1: RAW Mount time
        raw_mount_time = sample.mount_time_str

        # Column 2: Mount time (same as raw for now)
        mount_time = sample.mount_time_str

        # Column 3: RAW RA
        raw_ra = sample.ra_raw_str

        # Column 4: RA formatted from decimal hours
        ra_formatted = format_ra(sample.ra_hours, precision=2)

        # Column 5: RA StDev
        ra_stdev = f"{sample.ra_stdev:.3f}"

        # Column 6: RAW DEC
        raw_dec = sample.dec_raw_str

        # Column 7: DEC formatted from decimal degrees
        dec_formatted = format_dec(sample.dec_degrees, precision=2)

        # Column 8: DEC StDev
        dec_stdev = f"{sample.dec_stdev:.3f}"

        # Column 9: RAW DEC AXIS
        raw_dec_axis = f"{sample.dec_axis_position:.4f}" if sample.dec_axis_position is not None else ""

        # Column 10: DEC AXIS (same as raw)
        dec_axis = raw_dec_axis

        # Column 11: DEC AXIS StDev (not available per-sample)
        dec_axis_stdev = ""

        # Column 12: RAW RA AXIS
        raw_ra_axis = f"{sample.ra_axis_position:.4f}" if sample.ra_axis_position is not None else ""

        # Column 13: RA AXIS (same as raw)
        ra_axis = raw_ra_axis

        # Column 14: RA AXIS StDev (not available per-sample)
        ra_axis_stdev = ""

        # Column 15: Min RA Value
        min_ra_str = format_ra(self._min_ra_hours, precision=2) if self._min_ra_hours is not None else ""

        # Column 16: Max RA Value
        max_ra_str = format_ra(self._max_ra_hours, precision=2) if self._max_ra_hours is not None else ""

        # Column 17: Max RA StDev
        max_ra_stdev = f"{self._max_ra_stdev:.3f}"

        # Column 18: Min DEC value
        min_dec_str = format_dec(self._min_dec_degrees, precision=2) if self._min_dec_degrees is not None else ""

        # Column 19: Max DEC value
        max_dec_str = format_dec(self._max_dec_degrees, precision=2) if self._max_dec_degrees is not None else ""

        # Column 20: Max DEC StDev
        max_dec_stdev = f"{self._max_dec_stdev:.3f}"

        # Column 21: Min RA AXIS Value
        min_ra_axis_str = f"{self._min_ra_axis:.4f}" if self._min_ra_axis is not None else ""

        # Column 22: Max RA AXIS Value
        max_ra_axis_str = f"{self._max_ra_axis:.4f}" if self._max_ra_axis is not None else ""

        # Column 23: Max RA AXIS StDev
        max_ra_axis_stdev = f"{self._max_ra_axis_stdev:.3f}"

        # Column 24: Min DEC AXIS Value
        min_dec_axis_str = f"{self._min_dec_axis:.4f}" if self._min_dec_axis is not None else ""

        # Column 25: Max DEC AXIS Value
        max_dec_axis_str = f"{self._max_dec_axis:.4f}" if self._max_dec_axis is not None else ""

        # Column 26: Max DEC AXIS StDev
        max_dec_axis_stdev = f"{self._max_dec_axis_stdev:.3f}"

        # Column 27: Status
        status = sample.status.name

        columns = [
            raw_mount_time,      # 1
            mount_time,          # 2
            raw_ra,              # 3
            ra_formatted,        # 4
            ra_stdev,            # 5
            raw_dec,             # 6
            dec_formatted,       # 7
            dec_stdev,           # 8
            raw_dec_axis,        # 9
            dec_axis,            # 10
            dec_axis_stdev,      # 11
            raw_ra_axis,         # 12
            ra_axis,             # 13
            ra_axis_stdev,       # 14
            min_ra_str,          # 15
            max_ra_str,          # 16
            max_ra_stdev,        # 17
            min_dec_str,         # 18
            max_dec_str,         # 19
            max_dec_stdev,       # 20
            min_ra_axis_str,     # 21
            max_ra_axis_str,     # 22
            max_ra_axis_stdev,   # 23
            min_dec_axis_str,    # 24
            max_dec_axis_str,    # 25
            max_dec_axis_stdev,  # 26
            status,              # 27
        ]
        self._safe_write(self._dat_file, "\t".join(columns) + "\n")

    def log_time_sample(self, sample: TimeSample):
        """Write a time data sample to the .dti file."""
        if not self._dti_file:
            return
        ntp = f"{sample.pc_ntp_diff_ms:.1f}" if sample.pc_ntp_diff_ms is not None else ""
        line = (
            f"{sample.mount_time_str}\t{sample.pc_mount_diff_ms:.1f}\t"
            f"{sample.pc_loop_time_ms:.1f}\t{sample.mount_loop_time_ms:.1f}\t"
            f"{ntp}\n"
        )
        self._safe_write(self._dti_file, line)

    def log_seismic_data(self, timestamp: float, raw: float, offset: float, stdev: float):
        """Write a seismic data point to the .sei file."""
        if not self._sei_file:
            return
        ts = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
        self._safe_write(self._sei_file, f"{ts}\t{raw:.1f}\t{offset:.1f}\t{stdev:.4f}\n")

    def log_fft_snapshot(self, axis: str, sample_rate: float,
                         frequencies, magnitudes):
        """Write an FFT snapshot to the .fft file.

        Logs the top 3 peaks for the given axis (RA, DEC, or SEI).
        Called periodically by the FFT timer.
        """
        if not self._fft_file:
            return
        if frequencies is None or magnitudes is None:
            return
        if len(frequencies) == 0 or len(magnitudes) == 0:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        num_bins = len(frequencies)

        # Find top 3 peaks
        if len(magnitudes) > 3:
            peak_indices = magnitudes.argsort()[::-1][:3]
        else:
            peak_indices = list(range(len(magnitudes)))

        peaks = []
        for idx in peak_indices:
            freq = float(frequencies[idx])
            amp = float(magnitudes[idx])
            period = 1.0 / freq if freq > 0 else 0.0
            peaks.append((freq, period, amp))

        # Pad to 3 peaks
        while len(peaks) < 3:
            peaks.append((0.0, 0.0, 0.0))

        line = (
            f"{ts}\t{axis}\t{sample_rate:.2f}\t{num_bins}\t"
            f"{peaks[0][0]:.6f}\t{peaks[0][1]:.2f}\t{peaks[0][2]:.6f}\t"
            f"{peaks[1][0]:.6f}\t{peaks[1][1]:.2f}\t{peaks[1][2]:.6f}\t"
            f"{peaks[2][0]:.6f}\t{peaks[2][1]:.2f}\t{peaks[2][2]:.6f}\n"
        )
        self._safe_write(self._fft_file, line)

    def flush_all(self):
        """Flush all open files."""
        for f in [self._log_file, self._dat_file, self._dti_file,
                  self._sei_file, self._fft_file, self._env_file]:
            if f:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    pass

    def write_session_summary(self):
        """Write session summary to the .log file.

        Shows tracking-only statistics (not polluted by slewing/parked data).
        The Java original had this problem too — the Python version now
        separates tracking stats from total stats.
        """
        if not self._log_file:
            return

        w = self._log_file.write
        w("\n--- Session Summary ---\n")
        w(f"Total samples:\t{self._sample_count}\n")
        w(f"  Tracking:\t{self._tracking_count}\n")
        w(f"  Slewing:\t{self._slewing_count}\n")
        w(f"  Parked:\t{self._parked_count}\n")
        w(f"  Other:\t{self._sample_count - self._tracking_count - self._slewing_count - self._parked_count}\n")

        if self._tracking_count > 0:
            tracking_pct = self._tracking_count / self._sample_count * 100
            w(f"Tracking efficiency:\t{tracking_pct:.1f}%\n")

        w("\n--- Tracking Data (TRACKING samples only) ---\n")

        if self._tracking_count > 0:
            # RA range (tracking only)
            if self._tracking_min_ra is not None and self._tracking_max_ra is not None:
                min_ra_str = format_ra(self._tracking_min_ra, precision=2)
                max_ra_str = format_ra(self._tracking_max_ra, precision=2)
                w(f"RA range:\t{min_ra_str} - {max_ra_str}\n")

            w(f"Max RA StDev:\t{self._tracking_max_ra_stdev:.3f}\"\n")

            # DEC range (tracking only)
            if self._tracking_min_dec is not None and self._tracking_max_dec is not None:
                min_dec_str = format_dec(self._tracking_min_dec, precision=2)
                max_dec_str = format_dec(self._tracking_max_dec, precision=2)
                w(f"DEC range:\t{min_dec_str} - {max_dec_str}\n")

            w(f"Max DEC StDev:\t{self._tracking_max_dec_stdev:.3f}\"\n")
        else:
            w("No TRACKING samples recorded.\n")

        # RA axis range (all samples, same as .dat columns)
        if self._min_ra_axis is not None and self._max_ra_axis is not None:
            w(f"\n--- Axial Data (all samples) ---\n")
            w(f"RA AXIS range:\t{self._min_ra_axis:.4f} - {self._max_ra_axis:.4f}\n")
            w(f"Max RA AXIS StDev:\t{self._max_ra_axis_stdev:.3f}\"\n")
        if self._min_dec_axis is not None and self._max_dec_axis is not None:
            w(f"DEC AXIS range:\t{self._min_dec_axis:.4f} - {self._max_dec_axis:.4f}\n")
            w(f"Max DEC AXIS StDev:\t{self._max_dec_axis_stdev:.3f}\"\n")

        w("--- End Summary ---\n")
        self._log_file.flush()

    def close(self):
        """Close all log files and write summary. Flush before close."""
        if self._log_file:
            self.write_session_summary()
            self.log_event("Logging stopped.")
        self._flush_all()  # Final flush before closing
        self._active = False
        for attr in ['_log_file', '_dat_file', '_dti_file', '_sei_file', '_fft_file', '_env_file']:
            f = getattr(self, attr)
            if f:
                try:
                    f.close()
                except OSError:
                    pass
                setattr(self, attr, None)
        logger.info("Log files closed")

    def new_files(self, session_info: SessionInfo):
        """Close current files and open new ones."""
        self.close()
        self.start_session(session_info)
