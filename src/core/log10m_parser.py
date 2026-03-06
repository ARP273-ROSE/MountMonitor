"""Parser for 10micron mount .log10m files.

These files are zlib-compressed logs from the 10micron mount internal logger
(mountlogger). They contain:
- Mount identification (model, firmware, encoder steps)
- Network configuration (IP, MAC)
- Mount status polling (Gstat) with timestamps
- Time synchronization records (>t): mount clock JD vs PC clock JD
- Binary tracking data (>G, >H): proprietary format, not decoded
- GPS sync status and alignment info
- Session boundaries (###NEWLOG###, ###ENDLOG###)
"""

import zlib
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Julian Date epoch: JD 2451545.0 = 2000-01-01 12:00:00 UTC
_JD_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_JD_OFFSET = 2451545.0

# Gstat code descriptions
GSTAT_NAMES = {
    0: "Tracking",
    1: "Stopped",
    2: "Slewing to park",
    3: "Unparking",
    4: "Slewing to home",
    5: "Parked",
    6: "Slewing",
    7: "Not tracking (model OK)",
    8: "Tracking (outside limits)",
    9: "Outside limits",
    10: "Tracking (needs user)",
    11: "Needs update",
    98: "Unknown",
    99: "Error",
}

GSTAT_NAMES_FR = {
    0: "Suivi sidéral",
    1: "Arrêtée",
    2: "Parcage en cours",
    3: "Déparcage",
    4: "Retour position home",
    5: "Parquée",
    6: "Déplacement (GoTo)",
    7: "Pas de suivi (modèle OK)",
    8: "Suivi (hors limites)",
    9: "Hors limites",
    10: "Suivi (intervention requise)",
    11: "Mise à jour requise",
    98: "Inconnu",
    99: "Erreur",
}


def jd_to_datetime(jd: float) -> datetime:
    """Convert Julian Date to Python datetime (UTC)."""
    return _JD_EPOCH + timedelta(days=jd - _JD_OFFSET)


def datetime_to_jd(dt: datetime) -> float:
    """Convert Python datetime (UTC) to Julian Date."""
    delta = dt - _JD_EPOCH
    return _JD_OFFSET + delta.total_seconds() / 86400.0


@dataclass
class TimeSyncRecord:
    """A single time synchronization record (>t line)."""
    mount_jd: float
    pc_jd: float

    @property
    def mount_datetime(self) -> datetime:
        return jd_to_datetime(self.mount_jd)

    @property
    def pc_datetime(self) -> datetime:
        return jd_to_datetime(self.pc_jd)

    @property
    def diff_ms(self) -> float:
        """PC - Mount time difference in milliseconds."""
        return (self.pc_jd - self.mount_jd) * 86400.0 * 1000.0


@dataclass
class GstatRecord:
    """A single Gstat (mount status) record."""
    timestamp: float  # Unix timestamp from mount logger
    gstat: int

    @property
    def datetime_utc(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @property
    def state_name(self) -> str:
        return GSTAT_NAMES.get(self.gstat, f"Unknown({self.gstat})")

    @property
    def state_name_fr(self) -> str:
        return GSTAT_NAMES_FR.get(self.gstat, f"Inconnu({self.gstat})")


@dataclass
class GpsRecord:
    """A GPS sync status record."""
    timestamp: float
    status: str  # Raw status string


@dataclass
class AlignRecord:
    """An alignment status record."""
    timestamp: float
    num_stars: int  # Number of alignment stars (from the value after Align:)


@dataclass
class MountInfo:
    """Mount identification and configuration."""
    model: str = ""
    firmware: str = ""
    ra_steps: float = 0.0
    dec_steps: float = 0.0
    ip_ethernet: str = ""
    ip_wireless: str = ""
    mac_ethernet: str = ""
    mac_wireless: str = ""
    serial_number: str = ""
    assembly_number: str = ""
    logger_version: str = ""


@dataclass
class Log10mSession:
    """A single logging session within a .log10m file."""
    mount_info: MountInfo = field(default_factory=MountInfo)
    gstat_records: list[GstatRecord] = field(default_factory=list)
    time_sync_records: list[TimeSyncRecord] = field(default_factory=list)
    gps_records: list[GpsRecord] = field(default_factory=list)
    align_records: list[AlignRecord] = field(default_factory=list)
    g_record_count: int = 0  # >G binary records (not decoded)
    h_record_count: int = 0  # >H binary records (not decoded)
    sampling_started: float = 0.0  # Unix timestamp

    @property
    def start_time(self) -> datetime | None:
        """Session start time (UTC)."""
        if self.time_sync_records:
            return self.time_sync_records[0].mount_datetime
        if self.gstat_records:
            return self.gstat_records[0].datetime_utc
        return None

    @property
    def end_time(self) -> datetime | None:
        """Session end time (UTC)."""
        if self.time_sync_records:
            return self.time_sync_records[-1].mount_datetime
        if self.gstat_records:
            return self.gstat_records[-1].datetime_utc
        return None

    @property
    def duration_seconds(self) -> float:
        """Session duration in seconds."""
        start = self.start_time
        end = self.end_time
        if start and end:
            return (end - start).total_seconds()
        return 0.0


@dataclass
class Log10mFile:
    """A parsed .log10m file, possibly containing multiple sessions."""
    filepath: Path
    file_size_bytes: int = 0
    decompressed_size_bytes: int = 0
    sessions: list[Log10mSession] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


# Regex patterns for parsing
_RE_MOUNT_INFO = re.compile(
    r'^(\d+\.\d+)\s+Mount:\s+(.+?)\s+\((.+?)\)\s*$'
)
_RE_AR_STEPS = re.compile(
    r'^(\d+\.\d+)\s+ar_steps:\s+(\d+\.?\d*)\s*$'
)
_RE_DEC_STEPS = re.compile(
    r'^(\d+\.\d+)\s+dec_steps:\s+(\d+\.?\d*)\s*$'
)
_RE_IP_ETH = re.compile(
    r'^(\d+\.\d+)\s+IP address Ethernet:\s+(.+)\s*$'
)
_RE_IP_WIFI = re.compile(
    r'^(\d+\.\d+)\s+IP address Wireless:\s+(.+)\s*$'
)
_RE_MAC_ETH = re.compile(
    r'^(\d+\.\d+)\s+MAC address Ethernet:\s+(.+)\s*$'
)
_RE_MAC_WIFI = re.compile(
    r'^(\d+\.\d+)\s+MAC address Wireless:\s+(.+)\s*$'
)
_RE_SERIAL = re.compile(
    r'^(\d+\.\d+)\s+Mount serial number from Rowe:\s*(.*)\s*$'
)
_RE_ASSEMBLY = re.compile(
    r'^(\d+\.\d+)\s+Mount assembly number from Rowe:\s*(.*)\s*$'
)
_RE_GSTAT = re.compile(
    r'^(\d+\.\d+)\s+Gstat\s+(\d+)#\s*$'
)
_RE_GPS = re.compile(
    r'^(\d+\.\d+)\s+Last GPS\s+\[(.*)#\]\s*$'
)
_RE_ALIGN = re.compile(
    r'^(\d+\.\d+)\s+Align:\s*$'
)
_RE_SAMPLING = re.compile(
    r'^(\d+\.\d+)\s+Sampling started\s*$'
)
_RE_TIME_SYNC = re.compile(
    r'^>t\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$'
)
_RE_LOGGER_VERSION = re.compile(
    r'^mountlogger version\s+(.+)\s*$'
)
_RE_WIRELESS_CONFIG = re.compile(
    r'^(\d+\.\d+)\s+Wireless config:\s*(.*)\s*$'
)


def parse_log10m(filepath: str | Path, progress_callback=None) -> Log10mFile:
    """Parse a .log10m file.

    Args:
        filepath: Path to the .log10m file.
        progress_callback: Optional callable(percent: int) for progress updates.

    Returns:
        Parsed Log10mFile with all extracted data.
    """
    filepath = Path(filepath)
    result = Log10mFile(filepath=filepath)

    if not filepath.exists():
        result.parse_errors.append(f"File not found: {filepath}")
        return result

    result.file_size_bytes = filepath.stat().st_size

    # Decompress
    try:
        with open(filepath, 'rb') as f:
            compressed = f.read()
        decompressed = zlib.decompress(compressed)
        result.decompressed_size_bytes = len(decompressed)
        del compressed  # Free memory
    except zlib.error as e:
        result.parse_errors.append(f"Decompression failed: {e}")
        return result
    except OSError as e:
        result.parse_errors.append(f"Read error: {e}")
        return result

    if progress_callback:
        progress_callback(10)

    # Decode as latin-1 (binary-safe, preserves all bytes)
    text = decompressed.decode('latin-1')
    del decompressed  # Free memory

    if progress_callback:
        progress_callback(20)

    # Split into lines and parse
    lines = text.split('\n')
    total_lines = len(lines)
    del text  # Free memory

    current_session = None
    align_pending_ts = None  # Timestamp for pending align record

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        # Progress updates every 5%
        if progress_callback and i % max(1, total_lines // 20) == 0:
            pct = 20 + int(70 * i / total_lines)
            progress_callback(min(pct, 90))

        # Session boundaries
        if line == '###NEWLOG###':
            current_session = Log10mSession()
            result.sessions.append(current_session)
            continue
        if line == '###ENDLOG###':
            current_session = None
            continue

        # Ensure we have a session
        if current_session is None:
            current_session = Log10mSession()
            result.sessions.append(current_session)

        # Logger version
        m = _RE_LOGGER_VERSION.match(line)
        if m:
            current_session.mount_info.logger_version = m.group(1)
            continue

        # Time sync records (most frequent - check first for performance)
        if line.startswith('>t'):
            m = _RE_TIME_SYNC.match(line)
            if m:
                current_session.time_sync_records.append(
                    TimeSyncRecord(
                        mount_jd=float(m.group(1)),
                        pc_jd=float(m.group(2)),
                    )
                )
            continue

        # Binary records (count only)
        if line.startswith('>H'):
            current_session.h_record_count += 1
            continue
        if line.startswith('>G'):
            current_session.g_record_count += 1
            continue

        # Skip error messages
        if line.startswith('>>>'):
            continue

        # Timestamp-prefixed lines (metadata)
        if line[0].isdigit():
            # Mount info
            m = _RE_MOUNT_INFO.match(line)
            if m:
                current_session.mount_info.model = m.group(2)
                current_session.mount_info.firmware = m.group(3)
                continue

            m = _RE_AR_STEPS.match(line)
            if m:
                current_session.mount_info.ra_steps = float(m.group(2))
                continue

            m = _RE_DEC_STEPS.match(line)
            if m:
                current_session.mount_info.dec_steps = float(m.group(2))
                continue

            m = _RE_IP_ETH.match(line)
            if m:
                current_session.mount_info.ip_ethernet = m.group(2).strip()
                continue

            m = _RE_IP_WIFI.match(line)
            if m:
                current_session.mount_info.ip_wireless = m.group(2).strip()
                continue

            m = _RE_MAC_ETH.match(line)
            if m:
                current_session.mount_info.mac_ethernet = m.group(2).strip()
                continue

            m = _RE_MAC_WIFI.match(line)
            if m:
                current_session.mount_info.mac_wireless = m.group(2).strip()
                continue

            m = _RE_SERIAL.match(line)
            if m:
                current_session.mount_info.serial_number = m.group(2).strip()
                continue

            m = _RE_ASSEMBLY.match(line)
            if m:
                current_session.mount_info.assembly_number = m.group(2).strip()
                continue

            # Gstat
            m = _RE_GSTAT.match(line)
            if m:
                current_session.gstat_records.append(
                    GstatRecord(
                        timestamp=float(m.group(1)),
                        gstat=int(m.group(2)),
                    )
                )
                continue

            # GPS
            m = _RE_GPS.match(line)
            if m:
                current_session.gps_records.append(
                    GpsRecord(
                        timestamp=float(m.group(1)),
                        status=m.group(2).strip(),
                    )
                )
                continue

            # Alignment
            m = _RE_ALIGN.match(line)
            if m:
                align_pending_ts = float(m.group(1))
                continue

            # Sampling started
            m = _RE_SAMPLING.match(line)
            if m:
                current_session.sampling_started = float(m.group(1))
                continue

        # Align value (line after "Align:")
        if align_pending_ts is not None:
            try:
                # The align value is typically a number followed by #
                val = line.rstrip('#').strip()
                num_stars = int(val) if val else 0
                current_session.align_records.append(
                    AlignRecord(
                        timestamp=align_pending_ts,
                        num_stars=num_stars,
                    )
                )
            except (ValueError, TypeError):
                pass
            align_pending_ts = None

    if progress_callback:
        progress_callback(100)

    # Filter out empty sessions (artifacts from ###ENDLOG### boundaries)
    result.sessions = [
        s for s in result.sessions
        if s.mount_info.model or s.gstat_records or s.time_sync_records
    ]

    # Log summary
    for idx, session in enumerate(result.sessions):
        logger.info(
            f"Session {idx}: {session.mount_info.model} "
            f"FW {session.mount_info.firmware}, "
            f"{len(session.gstat_records)} Gstat records, "
            f"{len(session.time_sync_records)} time sync records, "
            f"{session.g_record_count} >G, {session.h_record_count} >H"
        )

    return result
