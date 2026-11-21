"""Abstract mount connection interface."""

from abc import ABC, abstractmethod
from typing import Optional
from ..models.mount_data import MountStatus, PierSide, ConnectionProtocol, EnvironmentSample


# :GT# answers on a 10Micron (MountWizzard4, mountcontrol/setting.py):
# 60.2 sidereal, 60.3 solar, 62.4 lunar, within 0.05.
_RATES_10MICRON = (("sidereal", 60.2), ("solar", 60.3), ("lunar", 62.4))


def classify_tracking_rate(reply):
    """'sidereal' | 'solar' | 'lunar' | 'king' | None from a mount answer.

    Numbers are the 10Micron :GT# values; words come from ASCOM. The old
    test accepted anything starting with "60" -- solar (60.3) passed for
    sidereal (60.2), so a mount left in solar mode raised no alarm.
    """
    if reply is None:
        return None
    text = str(reply).strip().rstrip('#').lower()
    try:
        v = float(text)
    except ValueError:
        for name in ("sidereal", "solar", "lunar", "king"):
            if name in text:
                return name
        return None
    for name, ref in _RATES_10MICRON:
        if abs(v - ref) < 0.05:
            return name
    return None


class MountConnection(ABC):
    """Abstract base class for telescope mount connections.

    All mount communication goes through this interface, regardless
    of protocol (LX200 TCP/IP, LX200 Serial, ASCOM, simulation).
    """

    def __init__(self):
        self._connected = False
        self._protocol = ConnectionProtocol.LX200

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def protocol(self) -> ConnectionProtocol:
        return self._protocol

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to mount. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self):
        """Close connection to mount."""
        ...

    @abstractmethod
    def get_ra(self) -> Optional[str]:
        """Get Right Ascension string from mount (HH:MM:SS.dd)."""
        ...

    @abstractmethod
    def get_dec(self) -> Optional[str]:
        """Get Declination string from mount (+DD:MM:SS.d)."""
        ...

    @abstractmethod
    def get_status(self) -> MountStatus:
        """Get current mount tracking status."""
        ...

    @abstractmethod
    def get_mount_time(self) -> Optional[str]:
        """Get mount internal time string (HH:MM:SS).

        The time zone depends on the protocol:
        - LX200: local time (via :GL# command)
        - ASCOM: UTC time (via UTCDate property)
        - Simulation: UTC time

        Check mount_time_is_utc to know which timezone.
        """
        ...

    @property
    def mount_time_is_utc(self) -> bool:
        """Whether get_mount_time() returns UTC (True) or local time (False)."""
        return self._protocol in (ConnectionProtocol.ASCOM, ConnectionProtocol.SIMULATION)

    @abstractmethod
    def get_firmware_version(self) -> str:
        """Get mount firmware version."""
        ...

    @abstractmethod
    def get_product_name(self) -> str:
        """Get mount product name."""
        ...

    @abstractmethod
    def get_mount_id(self) -> str:
        """Get unique mount identifier."""
        ...

    @abstractmethod
    def get_pier_side(self) -> PierSide:
        """Get which side of pier telescope is on."""
        ...

    @abstractmethod
    def get_azimuth(self) -> Optional[float]:
        """Get telescope azimuth in degrees."""
        ...

    @abstractmethod
    def get_altitude(self) -> Optional[float]:
        """Get telescope altitude in degrees."""
        ...

    def get_ra_axis_position(self) -> Optional[float]:
        """Get RA axis raw position (optional, 10Micron specific)."""
        return None

    def get_dec_axis_position(self) -> Optional[float]:
        """Get DEC axis raw position (optional, 10Micron specific)."""
        return None

    def get_target_ra(self) -> Optional[str]:
        """Get target RA if available."""
        return None

    def get_target_dec(self) -> Optional[str]:
        """Get target DEC if available."""
        return None

    def is_refraction_enabled(self) -> Optional[bool]:
        """Check if refraction correction is enabled."""
        return None

    def get_refraction_mode(self) -> Optional[str]:
        """Get refraction correction mode (10Micron specific).

        Returns one of:
        - "not_updating": Not updating
        - "not_updating_tracking": Not updating while tracking
        - "continuously_updating": Continuously updating
        - None: Unknown or not supported
        """
        return None

    def is_dual_tracking_enabled(self) -> Optional[bool]:
        """Check if dual axis tracking is enabled."""
        return None

    def get_tracking_rate(self) -> Optional[str]:
        """Get current tracking rate (sidereal, lunar, etc.)."""
        return None

    def is_gps_synced(self) -> Optional[bool]:
        """Check if GPS clock is synchronized."""
        return None

    def get_latitude(self) -> Optional[str]:
        """Get site latitude."""
        return None

    def get_longitude(self) -> Optional[str]:
        """Get site longitude."""
        return None

    def get_elevation(self) -> Optional[float]:
        """Get site elevation in meters."""
        return None

    def set_high_precision(self) -> bool:
        """Set mount to high precision output mode. Returns True on success."""
        return True

    # The poller thread owns the connection: it opens it, polls it, runs the
    # GUI's requests and closes it. These two hooks frame that thread (ASCOM
    # initialises COM there, so the COM object lives in the apartment that
    # uses it).
    def thread_enter(self) -> None:
        pass

    def thread_exit(self) -> None:
        pass

    def abort(self) -> None:
        """Unblock a read in progress from another thread (stop). Never raises."""

    def send_raw_command(self, command: str) -> Optional[str]:
        """Send a raw command and get the response. For advanced/10Micron commands."""
        return None

    def check_mount_settings(self) -> Optional[dict]:
        """Tracking preferences read from the mount (10Micron :PRlist#, see
        LX200Connection.check_mount_settings); None when not available."""
        return None

    def get_environment(self) -> EnvironmentSample:
        """Get environmental and diagnostic data from the mount.

        Returns an EnvironmentSample with all available data filled in.
        Default implementation returns an empty sample.
        """
        return EnvironmentSample()
