"""Log file parser for MountMonitor.

Parses .dat (27-column mount data) and .dti (time data) files
to reconstruct session data for replay and analysis.

Filters TRACKING-only data and segments by target for accurate analysis.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Thresholds for detecting a target change (slew between objects)
_RA_JUMP_THRESHOLD_HOURS = 0.25   # 15 arcmin in RA = new target
_DEC_JUMP_THRESHOLD_DEG = 2.0     # 2 degrees in DEC = new target
_MIN_SEGMENT_SAMPLES = 20         # Minimum samples to consider a segment valid


@dataclass
class TargetSegment:
    """A segment of tracking data on a single target."""
    start_index: int = 0
    end_index: int = 0
    ra_median_hours: float = 0.0
    dec_median_degrees: float = 0.0
    sample_count: int = 0
    ra_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))


@dataclass
class ParsedSession:
    """Parsed session data from log files."""
    # Metadata
    file_path: str = ""
    version: str = ""
    observatory: str = ""
    mount_name: str = ""
    mount_id: str = ""
    mount_driver: str = ""
    firmware: str = ""
    start_time: Optional[datetime] = None

    # Mount data arrays (from .dat) — ALL samples (raw)
    mount_times: list[str] = field(default_factory=list)
    ra_raw_strs: list[str] = field(default_factory=list)
    ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_raw_strs: list[str] = field(default_factory=list)
    dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    ra_axis: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_axis: np.ndarray = field(default_factory=lambda: np.array([]))
    statuses: list[str] = field(default_factory=list)
    timestamps: np.ndarray = field(default_factory=lambda: np.array([]))

    # Computed deviation arrays — TRACKING only, per-segment combined
    ra_deviations: np.ndarray = field(default_factory=lambda: np.array([]))
    dec_deviations: np.ndarray = field(default_factory=lambda: np.array([]))

    # TRACKING-only filtered arrays (for analysis)
    tracking_mask: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    tracking_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_ra_hours: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_dec_degrees: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_ra_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))
    tracking_dec_stdevs: np.ndarray = field(default_factory=lambda: np.array([]))

    # Target segments (each segment = one target in TRACKING mode)
    target_segments: list[TargetSegment] = field(default_factory=list)

    # Time data arrays (from .dti)
    time_mount_times: list[str] = field(default_factory=list)
    time_pc_mount_diff: np.ndarray = field(default_factory=lambda: np.array([]))
    time_pc_loop: np.ndarray = field(default_factory=lambda: np.array([]))
    time_mount_loop: np.ndarray = field(default_factory=lambda: np.array([]))
    time_ntp_diff: np.ndarray = field(default_factory=lambda: np.array([]))
    time_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))

    # Events (from .log)
    events: list[tuple[str, str]] = field(default_factory=list)

    # Environment data arrays (from .env)
    env_timestamps: np.ndarray = field(default_factory=lambda: np.array([]))
    env_temperature_ext: np.ndarray = field(default_factory=lambda: np.array([]))
    env_pressure: np.ndarray = field(default_factory=lambda: np.array([]))
    env_temperature_int: np.ndarray = field(default_factory=lambda: np.array([]))
    env_status_codes: list[int] = field(default_factory=list)
    env_tracking_rates: np.ndarray = field(default_factory=lambda: np.array([]))
    env_meridian_flip: np.ndarray = field(default_factory=lambda: np.array([]))
    env_alignment_stars: list[int] = field(default_factory=list)
    env_alignment_rms: np.ndarray = field(default_factory=lambda: np.array([]))
    env_polar_error: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def sample_count(self) -> int:
        return len(self.mount_times)

    @property
    def tracking_sample_count(self) -> int:
        return int(np.sum(self.tracking_mask)) if len(self.tracking_mask) > 0 else 0

    @property
    def duration_seconds(self) -> float:
        if len(self.timestamps) < 2:
            return 0.0
        return float(self.timestamps[-1] - self.timestamps[0])

    @property
    def duration_str(self) -> str:
        s = self.duration_seconds
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"

    @property
    def effective_frequency(self) -> float:
        """Cadence reelle des echantillons, en hertz.

        La duree peut valoir zero alors qu'il y a des echantillons : une
        session tenant dans la meme seconde, un fichier tronque dont toutes
        les lignes portent la meme heure. La division levait alors une
        exception au beau milieu de la construction du rapport — et l'ouverture
        d'un fichier .dat n'est pas protegee : l'application tombait.
        """
        if len(self.timestamps) < 2:
            return 0.0
        duree = self.duration_seconds
        if duree <= 0:
            return 0.0
        return (len(self.timestamps) - 1) / duree


def _parse_time_to_seconds(t_str: str) -> float:
    """Parse HH:MM:SS.dd to seconds since midnight."""
    try:
        parts = t_str.strip().split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _parse_ra_to_hours(ra_str: str) -> float:
    """Parse RA string hh:mm:ss.dd to decimal hours."""
    try:
        parts = ra_str.strip().split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = float(parts[2])
            return h + m / 60.0 + s / 3600.0
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _parse_dec_to_degrees(dec_str: str) -> float:
    """Parse DEC string dd:mm:ss.dd to decimal degrees."""
    try:
        s = dec_str.strip()
        sign = -1 if s.startswith('-') else 1
        s = s.lstrip('+-')
        parts = s.split(':')
        if len(parts) == 3:
            d = int(parts[0])
            m = int(parts[1])
            sec = float(parts[2])
            return sign * (d + m / 60.0 + sec / 3600.0)
        return 0.0
    except (ValueError, IndexError):
        return 0.0


def _ra_diff_hours(ra1: float, ra2: float) -> float:
    """Compute RA difference in hours, handling 24h wrap."""
    diff = ra1 - ra2
    if diff > 12.0:
        diff -= 24.0
    elif diff < -12.0:
        diff += 24.0
    return diff


def _segment_tracking_data(
    ra_hours: np.ndarray, dec_degrees: np.ndarray,
    timestamps: np.ndarray, ra_stdevs: np.ndarray, dec_stdevs: np.ndarray,
) -> list[TargetSegment]:
    """Segment TRACKING data into target groups.

    Detects target changes by finding large jumps in RA or DEC.
    Computes per-segment deviations from each segment's own median.
    """
    n = len(ra_hours)
    if n < _MIN_SEGMENT_SAMPLES:
        return []

    # Find segment boundaries: indices where RA or DEC jump significantly
    boundaries = [0]
    for i in range(1, n):
        ra_jump = abs(_ra_diff_hours(ra_hours[i], ra_hours[i - 1]))
        dec_jump = abs(dec_degrees[i] - dec_degrees[i - 1])
        if ra_jump > _RA_JUMP_THRESHOLD_HOURS or dec_jump > _DEC_JUMP_THRESHOLD_DEG:
            boundaries.append(i)
    boundaries.append(n)

    segments = []
    for b in range(len(boundaries) - 1):
        start = boundaries[b]
        end = boundaries[b + 1]
        count = end - start
        if count < _MIN_SEGMENT_SAMPLES:
            continue

        seg_ra = ra_hours[start:end]
        seg_dec = dec_degrees[start:end]
        seg_ts = timestamps[start:end]
        seg_ra_stdev = ra_stdevs[start:end]
        seg_dec_stdev = dec_stdevs[start:end]

        ra_median = float(np.median(seg_ra))
        dec_median = float(np.median(seg_dec))
        cos_dec = np.cos(np.radians(dec_median))

        # RA deviations in true arcseconds on the sky
        ra_dev = np.array([_ra_diff_hours(r, ra_median) for r in seg_ra]) * 15.0 * 3600.0 * cos_dec
        # DEC deviations in arcseconds
        dec_dev = (seg_dec - dec_median) * 3600.0

        seg = TargetSegment(
            start_index=start,
            end_index=end,
            ra_median_hours=ra_median,
            dec_median_degrees=dec_median,
            sample_count=count,
            ra_deviations=ra_dev,
            dec_deviations=dec_dev,
            timestamps=seg_ts,
            ra_hours=seg_ra,
            dec_degrees=seg_dec,
            ra_stdevs=seg_ra_stdev,
            dec_stdevs=seg_dec_stdev,
        )
        segments.append(seg)

    return segments


def parse_dat_file(dat_path: Path) -> ParsedSession:
    """Parse a .dat file (27-column TAB-separated mount data).

    Filters TRACKING samples, segments by target, computes per-segment deviations.
    Returns a ParsedSession with all mount data arrays populated.
    """
    session = ParsedSession(file_path=str(dat_path))

    if not dat_path.exists():
        logger.error(f"File not found: {dat_path}")
        return session

    mount_times = []
    ra_raw_strs = []
    ra_hours_list = []
    ra_stdev_list = []
    dec_raw_strs = []
    dec_deg_list = []
    dec_stdev_list = []
    ra_axis_list = []
    dec_axis_list = []
    statuses = []
    time_seconds = []

    in_header = True

    try:
        with open(dat_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')

                # Detect end of header: column header line starts with "RAW"
                if in_header:
                    if line.startswith("MountMonitor"):
                        ver_match = re.search(r'v\.(.+?)\)', line)
                        if ver_match:
                            session.version = ver_match.group(1)
                    elif line.startswith("Location:"):
                        session.observatory = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount:") and not line.startswith("Mount ID"):
                        session.mount_name = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount ID:"):
                        session.mount_id = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Mount driver:"):
                        session.mount_driver = line.split('\t', 1)[1].strip() if '\t' in line else ""
                    elif line.startswith("Firmware:"):
                        session.firmware = line.split('\t', 1)[1].strip() if '\t' in line else ""

                    # Column header line (last header line)
                    if line.startswith("RAW Mount time"):
                        in_header = False
                    continue

                # Data line: 27 TAB-separated columns
                cols = line.split('\t')
                if len(cols) < 27:
                    continue

                try:
                    # Column 1: Mount time
                    mt = cols[0].strip()
                    mount_times.append(mt)
                    ts = _parse_time_to_seconds(mt) if mt else 0.0
                    time_seconds.append(ts)

                    # Column 3: RAW RA
                    ra_raw_strs.append(cols[2].strip())

                    # Column 4: RA (formatted)
                    ra_h = _parse_ra_to_hours(cols[3])
                    ra_hours_list.append(ra_h)

                    # Column 5: RA StDev
                    ra_stdev_list.append(float(cols[4]) if cols[4].strip() else 0.0)

                    # Column 6: RAW DEC
                    dec_raw_strs.append(cols[5].strip())

                    # Column 7: DEC (formatted)
                    dec_d = _parse_dec_to_degrees(cols[6])
                    dec_deg_list.append(dec_d)

                    # Column 8: DEC StDev
                    dec_stdev_list.append(float(cols[7]) if cols[7].strip() else 0.0)

                    # Column 9: RAW DEC AXIS
                    dec_axis_list.append(float(cols[8]) if cols[8].strip() else 0.0)

                    # Column 12: RAW RA AXIS
                    ra_axis_list.append(float(cols[11]) if cols[11].strip() else 0.0)

                    # Column 27: Status
                    statuses.append(cols[26].strip())

                except (ValueError, IndexError) as e:
                    logger.debug(f"Skipping malformed line: {e}")
                    continue

    except OSError as e:
        logger.error(f"Failed to read {dat_path}: {e}")
        return session

    if not mount_times:
        return session

    # Handle timestamps: if mount times are empty, generate from index + assumed 2Hz
    all_empty = all(t == 0.0 for t in time_seconds)
    if all_empty:
        # Generate synthetic timestamps at 2Hz (0.5s interval)
        assumed_rate = 2.0
        time_seconds = [i / assumed_rate for i in range(len(mount_times))]

    # Handle midnight wrap: if time decreases, add 24h offset
    corrected_times = []
    offset = 0.0
    prev_t = 0.0
    for i, t in enumerate(time_seconds):
        if i > 0 and t < prev_t - 3600:  # big backward jump = midnight
            offset += 86400.0
        corrected_times.append(t + offset)
        prev_t = t

    # Convert to numpy arrays (ALL samples — raw)
    session.mount_times = mount_times
    session.ra_raw_strs = ra_raw_strs
    session.ra_hours = np.array(ra_hours_list)
    session.ra_stdevs = np.array(ra_stdev_list)
    session.dec_raw_strs = dec_raw_strs
    session.dec_degrees = np.array(dec_deg_list)
    session.dec_stdevs = np.array(dec_stdev_list)
    session.ra_axis = np.array(ra_axis_list)
    session.dec_axis = np.array(dec_axis_list)
    session.statuses = statuses
    session.timestamps = np.array(corrected_times)

    # ── Filter TRACKING-only samples ──
    tracking_mask = np.array([s == "TRACKING" for s in statuses], dtype=bool)
    session.tracking_mask = tracking_mask

    if np.any(tracking_mask):
        session.tracking_timestamps = session.timestamps[tracking_mask]
        session.tracking_ra_hours = session.ra_hours[tracking_mask]
        session.tracking_dec_degrees = session.dec_degrees[tracking_mask]
        session.tracking_ra_stdevs = session.ra_stdevs[tracking_mask]
        session.tracking_dec_stdevs = session.dec_stdevs[tracking_mask]

        # ── Segment tracking data by target ──
        segments = _segment_tracking_data(
            session.tracking_ra_hours,
            session.tracking_dec_degrees,
            session.tracking_timestamps,
            session.tracking_ra_stdevs,
            session.tracking_dec_stdevs,
        )
        session.target_segments = segments

        # ── Combine per-segment deviations into session-level arrays ──
        if segments:
            all_ra_dev = np.concatenate([seg.ra_deviations for seg in segments])
            all_dec_dev = np.concatenate([seg.dec_deviations for seg in segments])
            session.ra_deviations = all_ra_dev
            session.dec_deviations = all_dec_dev
        else:
            # Fallback: single segment from all tracking data
            ra_med = float(np.median(session.tracking_ra_hours))
            dec_med = float(np.median(session.tracking_dec_degrees))
            cos_dec = np.cos(np.radians(dec_med))
            ra_diffs = np.array([_ra_diff_hours(r, ra_med) for r in session.tracking_ra_hours])
            session.ra_deviations = ra_diffs * 15.0 * 3600.0 * cos_dec
            session.dec_deviations = (session.tracking_dec_degrees - dec_med) * 3600.0

        logger.info(f"Segmented into {len(segments)} target(s) from "
                     f"{int(np.sum(tracking_mask))} tracking samples")
    else:
        logger.warning("No TRACKING samples found in session")

    # Extract date from filename
    fname = dat_path.stem  # MountMonitor_YYYYMMDD-HHMMSS
    date_match = re.search(r'(\d{8})-(\d{6})', fname)
    if date_match:
        try:
            session.start_time = datetime.strptime(
                f"{date_match.group(1)}{date_match.group(2)}", "%Y%m%d%H%M%S"
            )
        except ValueError:
            pass

    logger.info(f"Parsed {len(mount_times)} samples from {dat_path.name} "
                f"({int(np.sum(tracking_mask))} tracking, "
                f"duration: {session.duration_str})")
    return session


def parse_dti_file(dti_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .dti file (time data) and add to session."""
    if not dti_path.exists():
        return session

    mount_times = []
    pc_mount_diff = []
    pc_loop = []
    mount_loop = []
    ntp_diff = []
    time_seconds = []

    header_lines = 0

    try:
        with open(dti_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                if header_lines < 3:
                    header_lines += 1
                    continue

                cols = line.split('\t')
                if len(cols) < 4:
                    continue

                try:
                    mt = cols[0].strip()
                    mount_times.append(mt)
                    time_seconds.append(_parse_time_to_seconds(mt))
                    pc_mount_diff.append(float(cols[1]))
                    pc_loop.append(float(cols[2]))
                    mount_loop.append(float(cols[3]))
                    ntp_diff.append(float(cols[4]) if len(cols) > 4 and cols[4].strip() else 0.0)
                except (ValueError, IndexError):
                    continue

    except OSError as e:
        logger.error(f"Failed to read {dti_path}: {e}")
        return session

    if time_seconds:
        # Handle midnight wrap
        corrected = []
        offset = 0.0
        prev_t = 0.0
        for i, t in enumerate(time_seconds):
            if i > 0 and t < prev_t - 3600:
                offset += 86400.0
            corrected.append(t + offset)
            prev_t = t

        session.time_mount_times = mount_times
        session.time_pc_mount_diff = np.array(pc_mount_diff)
        session.time_pc_loop = np.array(pc_loop)
        session.time_mount_loop = np.array(mount_loop)
        session.time_ntp_diff = np.array(ntp_diff)
        session.time_timestamps = np.array(corrected)

    return session


def parse_log_file(log_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .log file (events) and add to session."""
    if not log_path.exists():
        return session

    events = []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                # Skip header (non-timestamped lines)
                if '\t' in line:
                    parts = line.split('\t', 1)
                    if len(parts) == 2 and '/' in parts[0]:
                        events.append((parts[0].strip(), parts[1].strip()))
    except OSError:
        pass

    session.events = events
    return session


def parse_env_file(env_path: Path, session: ParsedSession) -> ParsedSession:
    """Parse a .env file (environment/diagnostics data) and add to session."""
    if not env_path.exists():
        return session

    timestamps = []
    temp_ext = []
    pressure = []
    temp_int = []
    status_codes = []
    tracking_rates = []
    meridian_flip = []
    alignment_stars = []
    alignment_rms = []
    polar_error = []

    header_lines = 0

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                if header_lines < 3:
                    header_lines += 1
                    continue

                cols = line.split('\t')
                if len(cols) < 4:
                    continue

                try:
                    mt = cols[0].strip()
                    timestamps.append(_parse_time_to_seconds(mt))
                    temp_ext.append(float(cols[1]) if cols[1].strip() else float('nan'))
                    pressure.append(float(cols[2]) if cols[2].strip() else float('nan'))
                    temp_int.append(float(cols[3]) if cols[3].strip() else float('nan'))

                    if len(cols) > 4 and cols[4].strip():
                        status_codes.append(int(cols[4]))
                    else:
                        status_codes.append(-1)

                    tracking_rates.append(float(cols[5]) if len(cols) > 5 and cols[5].strip() else float('nan'))
                    meridian_flip.append(float(cols[6]) if len(cols) > 6 and cols[6].strip() else float('nan'))

                    # cols[7] = pier side (text, skip for now)

                    if len(cols) > 8 and cols[8].strip():
                        alignment_stars.append(int(cols[8]))
                    else:
                        alignment_stars.append(0)

                    alignment_rms.append(float(cols[9]) if len(cols) > 9 and cols[9].strip() else float('nan'))
                    polar_error.append(float(cols[10]) if len(cols) > 10 and cols[10].strip() else float('nan'))

                except (ValueError, IndexError):
                    continue

    except OSError as e:
        logger.error(f"Failed to read {env_path}: {e}")
        return session

    if timestamps:
        session.env_timestamps = np.array(timestamps)
        session.env_temperature_ext = np.array(temp_ext)
        session.env_pressure = np.array(pressure)
        session.env_temperature_int = np.array(temp_int)
        session.env_status_codes = status_codes
        session.env_tracking_rates = np.array(tracking_rates)
        session.env_meridian_flip = np.array(meridian_flip)
        session.env_alignment_stars = alignment_stars
        session.env_alignment_rms = np.array(alignment_rms)
        session.env_polar_error = np.array(polar_error)

    return session


def parse_session(dat_path: Path) -> ParsedSession:
    """Parse a complete session from a .dat file and its siblings.

    Automatically finds and parses .dti, .log, and .env files with the same prefix.
    """
    session = parse_dat_file(dat_path)

    # Find sibling files
    stem = dat_path.stem
    parent = dat_path.parent

    dti_path = parent / f"{stem}.dti"
    log_path = parent / f"{stem}.log"
    env_path = parent / f"{stem}.env"

    if dti_path.exists():
        parse_dti_file(dti_path, session)

    if log_path.exists():
        parse_log_file(log_path, session)

    if env_path.exists():
        parse_env_file(env_path, session)

    return session


def list_log_sessions(log_dir: Path) -> list[dict]:
    """List available log sessions in a directory.

    Returns list of dicts with: path, filename, date, size_kb
    """
    sessions = []
    if not log_dir.exists():
        return sessions

    for dat_file in sorted(log_dir.glob("MountMonitor_*.dat"), reverse=True):
        info = {
            'path': dat_file,
            'filename': dat_file.name,
            'size_kb': dat_file.stat().st_size / 1024,
        }
        # Extract date from filename
        date_match = re.search(r'(\d{8})-(\d{6})', dat_file.stem)
        if date_match:
            try:
                dt = datetime.strptime(
                    f"{date_match.group(1)}{date_match.group(2)}", "%Y%m%d%H%M%S"
                )
                info['date'] = dt
                info['date_str'] = dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                info['date'] = None
                info['date_str'] = "?"
        sessions.append(info)

    return sessions
