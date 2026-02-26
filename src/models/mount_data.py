"""Data models for MountMonitor."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class MountStatus(Enum):
    """Mount tracking status."""
    UNKNOWN = auto()
    TRACKING = auto()
    SLEWING = auto()
    PARKED = auto()
    IDLE = auto()
    ERROR = auto()


class PierSide(Enum):
    """Side of pier."""
    EAST = "East"
    WEST = "West"
    UNKNOWN = "Unknown"


class ConnectionProtocol(Enum):
    """Communication protocol."""
    LX200 = "lx200"
    ASCOM = "ascom"
    ALPACA = "alpaca"
    SIMULATION = "simulation"


@dataclass
class MountSample:
    """A single mount data sample (RA, DEC, time, axial data)."""
    timestamp: datetime
    mount_time_str: str = ""
    ra_hours: float = 0.0
    dec_degrees: float = 0.0
    ra_raw_str: str = ""
    dec_raw_str: str = ""
    ra_deviation_arcsec: float = 0.0
    dec_deviation_arcsec: float = 0.0
    ra_stdev: float = 0.0
    dec_stdev: float = 0.0
    ra_axis_position: Optional[float] = None
    dec_axis_position: Optional[float] = None
    ra_axis_speed: Optional[float] = None
    dec_axis_speed: Optional[float] = None
    status: MountStatus = MountStatus.UNKNOWN
    pier_side: PierSide = PierSide.UNKNOWN


@dataclass
class TimeSample:
    """Time comparison data sample."""
    timestamp: datetime
    mount_time_str: str = ""
    pc_mount_diff_ms: float = 0.0
    pc_loop_time_ms: float = 0.0
    mount_loop_time_ms: float = 0.0
    pc_ntp_diff_ms: Optional[float] = None


@dataclass
class SeismicSample:
    """Seismometer data sample."""
    timestamp: datetime
    raw_values: list[float] = field(default_factory=list)
    offset_values: list[float] = field(default_factory=list)
    stdev: float = 0.0


@dataclass
class SessionInfo:
    """Session metadata, written to log file headers."""
    version: str = ""
    observatory: str = ""
    mount_name: str = ""
    mount_id: str = ""
    mount_driver: str = ""
    firmware: str = ""
    protocol: ConnectionProtocol = ConnectionProtocol.LX200
    latitude: str = ""
    longitude: str = ""
    elevation: str = ""
    pier_side: PierSide = PierSide.UNKNOWN
    azimuth: float = 0.0
    altitude: float = 0.0
    start_time: Optional[datetime] = None


@dataclass
class ToleranceState:
    """Current tolerance state for RA/DEC/Seismic."""
    ra_exceeded: bool = False
    dec_exceeded: bool = False
    seismic_exceeded: bool = False
    ra_stdev_exceeded: bool = False
    dec_stdev_exceeded: bool = False
    ra_exceeded_since: Optional[datetime] = None
    dec_exceeded_since: Optional[datetime] = None
