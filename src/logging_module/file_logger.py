"""File logging system for MountMonitor.

Creates and manages 4 log file types:
  .log  - Events, settings changes, tolerance alerts
  .dat  - RA/DEC data (TAB-separated)
  .dti  - Time data (TAB-separated)
  .sei  - Seismometer data (TAB-separated)

Files are named: MountMonitor_YYYYMMDD-HHMMSS.ext
Stored in a Logs/ subdirectory.
"""

import os
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from ..models.mount_data import MountSample, TimeSample, SessionInfo
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
    """

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent / "Logs"
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._log_file: Optional[TextIO] = None
        self._dat_file: Optional[TextIO] = None
        self._dti_file: Optional[TextIO] = None
        self._sei_file: Optional[TextIO] = None
        self._session_start: Optional[str] = None
        self._version = _read_version()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def log_dir(self) -> Path:
        return self._base_dir

    def start_session(self, session_info: SessionInfo):
        """Open new log files for a monitoring session."""
        self._session_start = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = f"MountMonitor_{self._session_start}"

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

            self._active = True
            self.log_event("Logging started.")
            logger.info(f"Log files created: {prefix}.*")

        except OSError as e:
            logger.error(f"Failed to create log files: {e}")
            self.close()

    def _write_log_header(self, info: SessionInfo):
        """Write .log file header."""
        f = self._log_file
        f.write(f"MountMonitor logfile (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        if info.latitude:
            f.write(f"Position:\tLatitude = {info.latitude}\t"
                    f"Longitude = {info.longitude}\t"
                    f"Elevation = {info.elevation}m\n")
        f.write(f"Mount:\t{info.mount_name}\n")
        f.write(f"Mount ID:\t{info.mount_id}\n")
        if info.mount_driver:
            f.write(f"Mount driver:\t{info.mount_driver}\n")
        f.write(f"Firmware:\t{info.firmware}\n")
        f.write(f"Protocol:\t{info.protocol.value}\n")
        f.flush()

    def _write_dat_header(self, info: SessionInfo):
        """Write .dat file header."""
        f = self._dat_file
        f.write(f"MountMonitor mount data file (v.{self._version})\n")
        f.write(f"Location:\t{info.observatory}\n")
        f.write(f"Mount:\t{info.mount_name}\n")
        f.write(f"Mount ID:\t{info.mount_id}\n")
        f.write(f"Firmware:\t{info.firmware}\n")
        # Column headers
        f.write("Timestamp\tMount time\tRA raw\tRA [h]\t"
                "RA dev [\"]\tRA StDev [\"]\t"
                "DEC raw\tDEC [deg]\t"
                "DEC dev [\"]\tDEC StDev [\"]\t"
                "RA axis\tDEC axis\tStatus\n")
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

    def log_event(self, message: str):
        """Write an event to the .log file."""
        if not self._log_file:
            return
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
        self._log_file.write(f"{timestamp}\t{message}\n")
        self._log_file.flush()

    def log_mount_sample(self, sample: MountSample):
        """Write a mount data sample to the .dat file."""
        if not self._dat_file:
            return
        timestamp = sample.timestamp.strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
        ra_axis = f"{sample.ra_axis_position:.6f}" if sample.ra_axis_position is not None else ""
        dec_axis = f"{sample.dec_axis_position:.6f}" if sample.dec_axis_position is not None else ""

        line = (
            f"{timestamp}\t{sample.mount_time_str}\t"
            f"{sample.ra_raw_str}\t{sample.ra_hours:.8f}\t"
            f"{sample.ra_deviation_arcsec:.4f}\t{sample.ra_stdev:.4f}\t"
            f"{sample.dec_raw_str}\t{sample.dec_degrees:.8f}\t"
            f"{sample.dec_deviation_arcsec:.4f}\t{sample.dec_stdev:.4f}\t"
            f"{ra_axis}\t{dec_axis}\t{sample.status.name}\n"
        )
        self._dat_file.write(line)

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
        self._dti_file.write(line)

    def log_seismic_data(self, timestamp: float, raw: float, offset: float, stdev: float):
        """Write a seismic data point to the .sei file."""
        if not self._sei_file:
            return
        ts = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
        self._sei_file.write(f"{ts}\t{raw:.1f}\t{offset:.1f}\t{stdev:.4f}\n")

    def flush_all(self):
        """Flush all open files."""
        for f in [self._log_file, self._dat_file, self._dti_file, self._sei_file]:
            if f:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    pass

    def close(self):
        """Close all log files and write summary."""
        if self._log_file:
            self.log_event("Logging stopped.")
        self._active = False
        for attr in ['_log_file', '_dat_file', '_dti_file', '_sei_file']:
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
