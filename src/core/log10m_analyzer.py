"""Analyzer for parsed 10micron mount .log10m data.

Takes parsed Log10mFile data and produces comprehensive analysis:
- Session overview and timeline
- Mount activity breakdown (tracking efficiency, slew analysis)
- Time synchronization drift analysis
- Model building detection (rapid Gstat 0<->6 transitions)
- Anomaly detection
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import numpy as np

from .log10m_parser import (
    Log10mFile, Log10mSession, GstatRecord, TimeSyncRecord,
    GSTAT_NAMES, GSTAT_NAMES_FR, jd_to_datetime,
)

logger = logging.getLogger(__name__)


@dataclass
class GstatSegment:
    """A continuous period in a single Gstat state."""
    gstat: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float

    @property
    def state_name(self) -> str:
        return GSTAT_NAMES.get(self.gstat, f"Unknown({self.gstat})")

    @property
    def state_name_fr(self) -> str:
        return GSTAT_NAMES_FR.get(self.gstat, f"Inconnu({self.gstat})")


@dataclass
class SlewEvent:
    """A detected slew (GoTo) event."""
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    is_model_building: bool = False  # Rapid 0<->6 pattern = alignment


@dataclass
class TimeSyncStats:
    """Statistics for time synchronization."""
    mean_diff_ms: float = 0.0
    median_diff_ms: float = 0.0
    stdev_diff_ms: float = 0.0
    min_diff_ms: float = 0.0
    max_diff_ms: float = 0.0
    drift_rate_ms_per_hour: float = 0.0
    num_samples: int = 0
    # Time series data for plotting
    timestamps: list[float] = field(default_factory=list)  # Unix timestamps
    diffs_ms: list[float] = field(default_factory=list)


@dataclass
class ActivitySummary:
    """Summary of mount activity."""
    total_duration_seconds: float = 0.0
    tracking_seconds: float = 0.0
    slewing_seconds: float = 0.0
    parked_seconds: float = 0.0
    other_seconds: float = 0.0
    tracking_efficiency_percent: float = 0.0
    num_slews: int = 0
    avg_slew_duration_seconds: float = 0.0
    max_slew_duration_seconds: float = 0.0
    num_model_building_slews: int = 0
    model_building_duration_seconds: float = 0.0
    gstat_segments: list[GstatSegment] = field(default_factory=list)
    slew_events: list[SlewEvent] = field(default_factory=list)


@dataclass
class SessionAnalysis:
    """Complete analysis of a single log session."""
    session_index: int = 0
    mount_model: str = ""
    mount_firmware: str = ""
    logger_version: str = ""
    ra_steps: float = 0.0
    dec_steps: float = 0.0
    ip_address: str = ""
    mac_address: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float = 0.0
    gstat_record_count: int = 0
    time_sync_count: int = 0
    g_record_count: int = 0
    h_record_count: int = 0
    gps_record_count: int = 0
    align_star_counts: list[int] = field(default_factory=list)
    sampling_rate_hz: float = 0.0
    activity: ActivitySummary = field(default_factory=ActivitySummary)
    time_sync: TimeSyncStats = field(default_factory=TimeSyncStats)


@dataclass
class Log10mAnalysis:
    """Complete analysis of one or more .log10m files."""
    file_count: int = 0
    total_file_size_mb: float = 0.0
    total_decompressed_mb: float = 0.0
    sessions: list[SessionAnalysis] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


def _analyze_gstat_segments(records: list[GstatRecord]) -> list[GstatSegment]:
    """Convert Gstat records into continuous segments."""
    if not records:
        return []

    segments = []
    current_gstat = records[0].gstat
    current_start = records[0].datetime_utc

    for i in range(1, len(records)):
        rec = records[i]
        if rec.gstat != current_gstat:
            segments.append(GstatSegment(
                gstat=current_gstat,
                start_time=current_start,
                end_time=rec.datetime_utc,
                duration_seconds=(rec.datetime_utc - current_start).total_seconds(),
            ))
            current_gstat = rec.gstat
            current_start = rec.datetime_utc

    # Close last segment using the last record time
    if records:
        segments.append(GstatSegment(
            gstat=current_gstat,
            start_time=current_start,
            end_time=records[-1].datetime_utc,
            duration_seconds=(records[-1].datetime_utc - current_start).total_seconds(),
        ))

    return segments


def _detect_slews(segments: list[GstatSegment]) -> list[SlewEvent]:
    """Detect slew events from Gstat segments."""
    slews = []
    for seg in segments:
        if seg.gstat == 6:  # Slewing
            slews.append(SlewEvent(
                start_time=seg.start_time,
                end_time=seg.end_time,
                duration_seconds=seg.duration_seconds,
            ))
    return slews


def _detect_model_building(slews: list[SlewEvent]) -> None:
    """Detect model building sessions (rapid consecutive short slews).

    Model building (e.g., ModelCreator) produces many rapid slews
    to alignment stars. Pattern: many short slews (5-20s) with
    short tracking periods (5-30s) between them.
    """
    if len(slews) < 3:
        return

    # Sliding window: if we see 3+ slews within 5 minutes, all with
    # duration < 30s, it's likely model building
    for i in range(len(slews)):
        if slews[i].is_model_building:
            continue

        window_slews = [slews[i]]
        for j in range(i + 1, len(slews)):
            gap = (slews[j].start_time - window_slews[-1].end_time).total_seconds()
            if gap > 120:  # More than 2min gap = different activity
                break
            if slews[j].duration_seconds > 60:  # Slew too long for model building
                break
            window_slews.append(slews[j])

        if len(window_slews) >= 3:
            # All slews in the window are short = model building
            for s in window_slews:
                if s.duration_seconds <= 60:
                    s.is_model_building = True


def _analyze_activity(records: list[GstatRecord]) -> ActivitySummary:
    """Analyze mount activity from Gstat records."""
    if not records:
        return ActivitySummary()

    segments = _analyze_gstat_segments(records)
    slews = _detect_slews(segments)
    _detect_model_building(slews)

    # Calculate time in each state
    tracking = sum(s.duration_seconds for s in segments if s.gstat == 0)
    slewing = sum(s.duration_seconds for s in segments if s.gstat == 6)
    parked = sum(s.duration_seconds for s in segments if s.gstat == 5)
    parking = sum(s.duration_seconds for s in segments if s.gstat == 2)
    total = sum(s.duration_seconds for s in segments)
    other = total - tracking - slewing - parked - parking

    # Slew stats
    normal_slews = [s for s in slews if not s.is_model_building]
    model_slews = [s for s in slews if s.is_model_building]
    slew_durations = [s.duration_seconds for s in normal_slews]

    # Tracking efficiency: tracking time / (total - parked)
    active_time = total - parked - parking
    efficiency = (tracking / active_time * 100.0) if active_time > 0 else 0.0

    return ActivitySummary(
        total_duration_seconds=total,
        tracking_seconds=tracking,
        slewing_seconds=slewing,
        parked_seconds=parked + parking,
        other_seconds=other,
        tracking_efficiency_percent=efficiency,
        num_slews=len(normal_slews),
        avg_slew_duration_seconds=(
            statistics.mean(slew_durations) if slew_durations else 0.0
        ),
        max_slew_duration_seconds=max(slew_durations) if slew_durations else 0.0,
        num_model_building_slews=len(model_slews),
        model_building_duration_seconds=sum(
            s.duration_seconds for s in model_slews
        ),
        gstat_segments=segments,
        slew_events=slews,
    )


def _analyze_time_sync(records: list[TimeSyncRecord]) -> TimeSyncStats:
    """Analyze time synchronization data."""
    if not records:
        return TimeSyncStats()

    diffs = [r.diff_ms for r in records]
    timestamps = [r.mount_jd for r in records]

    # Convert JD timestamps to Unix timestamps for plotting
    unix_ts = [
        (jd_to_datetime(jd) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
        for jd in timestamps
    ]

    stats = TimeSyncStats(
        mean_diff_ms=statistics.mean(diffs),
        median_diff_ms=statistics.median(diffs),
        stdev_diff_ms=statistics.stdev(diffs) if len(diffs) > 1 else 0.0,
        min_diff_ms=min(diffs),
        max_diff_ms=max(diffs),
        num_samples=len(diffs),
        timestamps=unix_ts,
        diffs_ms=diffs,
    )

    # Calculate drift rate using linear regression
    if len(diffs) > 10:
        # Use hours as x-axis for drift rate
        t0 = unix_ts[0]
        x = np.array([(t - t0) / 3600.0 for t in unix_ts])
        y = np.array(diffs)

        # Simple linear regression
        n = len(x)
        sx = np.sum(x)
        sy = np.sum(y)
        sxx = np.sum(x * x)
        sxy = np.sum(x * y)

        denom = n * sxx - sx * sx
        if abs(denom) > 1e-10:
            stats.drift_rate_ms_per_hour = (n * sxy - sx * sy) / denom

    return stats


def analyze_session(session: Log10mSession, index: int = 0) -> SessionAnalysis:
    """Analyze a single parsed session."""
    info = session.mount_info

    analysis = SessionAnalysis(
        session_index=index,
        mount_model=info.model,
        mount_firmware=info.firmware,
        logger_version=info.logger_version,
        ra_steps=info.ra_steps,
        dec_steps=info.dec_steps,
        ip_address=info.ip_ethernet,
        mac_address=info.mac_ethernet,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        gstat_record_count=len(session.gstat_records),
        time_sync_count=len(session.time_sync_records),
        g_record_count=session.g_record_count,
        h_record_count=session.h_record_count,
        gps_record_count=len(session.gps_records),
        align_star_counts=[a.num_stars for a in session.align_records],
    )

    # Sampling rate from time sync records
    if len(session.time_sync_records) > 1:
        t0 = session.time_sync_records[0].mount_jd
        t1 = session.time_sync_records[-1].mount_jd
        duration_s = (t1 - t0) * 86400.0
        if duration_s > 0:
            analysis.sampling_rate_hz = (len(session.time_sync_records) - 1) / duration_s

    # Activity analysis from Gstat
    analysis.activity = _analyze_activity(session.gstat_records)

    # Time sync analysis
    analysis.time_sync = _analyze_time_sync(session.time_sync_records)

    return analysis


def analyze_log10m_files(files: list[Log10mFile]) -> Log10mAnalysis:
    """Analyze one or more parsed .log10m files."""
    result = Log10mAnalysis(file_count=len(files))

    for f in files:
        result.total_file_size_mb += f.file_size_bytes / (1024 * 1024)
        result.total_decompressed_mb += f.decompressed_size_bytes / (1024 * 1024)
        result.parse_errors.extend(f.parse_errors)

        for idx, session in enumerate(f.sessions):
            analysis = analyze_session(session, index=len(result.sessions))
            result.sessions.append(analysis)

    return result
