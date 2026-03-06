"""ASCOM Telescope driver connection implementation.

Uses comtypes (Windows COM library) to communicate with ASCOM-compatible
telescope drivers. Falls back gracefully on non-Windows platforms.

Supports 10Micron, Celestron, iOptron, and any ASCOM-compliant mount driver.
"""

import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Optional

from .mount_connection import MountConnection
from ..models.mount_data import MountStatus, PierSide, ConnectionProtocol, EnvironmentSample

logger = logging.getLogger(__name__)

# Graceful import of comtypes (Windows-only)
_comtypes_available = False
try:
    import comtypes
    import comtypes.client
    _comtypes_available = True
except ImportError:
    logger.info("comtypes not available - ASCOM connections disabled (non-Windows platform)")

# ASCOM tracking rate constants
_TRACKING_RATES = {
    0: "Sidereal",
    1: "Lunar",
    2: "Solar",
    3: "King",
}

# ASCOM pier side constants
_ASCOM_PIER_EAST = 0   # pierEast - telescope on east side, looking west
_ASCOM_PIER_WEST = 1   # pierWest - telescope on west side, looking east
_ASCOM_PIER_UNKNOWN = -1


def _hours_to_hms(hours: float) -> str:
    """Convert decimal hours to HH:MM:SS.dd string."""
    negative = hours < 0
    hours = abs(hours)
    h = int(hours)
    remainder = (hours - h) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    sign = "-" if negative else ""
    return f"{sign}{h:02d}:{m:02d}:{s:05.2f}"


def _degrees_to_dms(degrees: float) -> str:
    """Convert decimal degrees to +DD:MM:SS.d string."""
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    remainder = (degrees - d) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    return f"{sign}{d:02d}:{m:02d}:{s:04.1f}"


def _degrees_to_dms_lat(degrees: float) -> str:
    """Convert decimal degrees to latitude string (sDD*MM'SS)."""
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    remainder = (degrees - d) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    return f"{sign}{d:02d}*{m:02d}'{s:04.1f}"


def _degrees_to_dms_lon(degrees: float) -> str:
    """Convert decimal degrees to longitude string (sDDD*MM'SS)."""
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    remainder = (degrees - d) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    return f"{sign}{d:03d}*{m:02d}'{s:04.1f}"


class ASCOMConnection(MountConnection):
    """ASCOM Telescope driver connection via Windows COM.

    Requires:
        - Windows platform
        - comtypes package (pip install comtypes)
        - An ASCOM telescope driver installed (e.g. ASCOM.tenmicron_mount.Telescope)

    The COM object is created and accessed from a dedicated thread to ensure
    proper COM apartment threading (CoInitialize/CoUninitialize).
    """

    def __init__(self, driver_id: str = "ASCOM.tenmicron_mount.Telescope"):
        """Initialize ASCOM connection.

        Args:
            driver_id: ASCOM driver ProgID (e.g. "ASCOM.tenmicron_mount.Telescope")
        """
        super().__init__()
        self._driver_id = driver_id
        self._protocol = ConnectionProtocol.ASCOM
        self._telescope = None  # COM object
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._lock = threading.Lock()
        self._com_initialized = False
        self._warned_properties: set = set()  # Rate-limit warnings per property

    @property
    def driver_id(self) -> str:
        return self._driver_id

    def _ensure_com_init(self):
        """Initialize COM for the current thread if not already done."""
        if not _comtypes_available:
            return
        if not self._com_initialized:
            try:
                comtypes.CoInitialize()
                self._com_initialized = True
            except OSError:
                # Already initialized in this thread
                self._com_initialized = True

    def _com_uninit(self):
        """Uninitialize COM for the current thread."""
        if not _comtypes_available:
            return
        if self._com_initialized:
            try:
                comtypes.CoUninitialize()
            except OSError:
                pass
            self._com_initialized = False

    def connect(self) -> bool:
        """Connect to mount via ASCOM driver.

        Creates the COM object and sets Connected = True.
        Returns True on success.
        """
        if not _comtypes_available:
            logger.error("comtypes not available - cannot use ASCOM on this platform")
            return False

        if not self._driver_id:
            logger.error("No ASCOM driver ID configured")
            return False

        try:
            self.disconnect()  # Clean up any existing connection
            self._ensure_com_init()

            logger.info(f"Creating ASCOM object: {self._driver_id}")
            self._telescope = comtypes.client.CreateObject(self._driver_id)

            # Connect to the telescope
            self._telescope.Connected = True

            if not self._telescope.Connected:
                logger.error("ASCOM driver reports not connected after setting Connected=True")
                self._telescope = None
                return False

            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to ASCOM driver: {self._driver_id}")
            return True

        except Exception as e:
            logger.error(f"ASCOM connection failed for {self._driver_id}: {e}")
            self._telescope = None
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from ASCOM driver.

        Sets Connected = False and releases the COM object.
        """
        if self._telescope is not None:
            try:
                self._telescope.Connected = False
                logger.info("ASCOM driver disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting ASCOM driver: {e}")
            finally:
                self._telescope = None

        self._connected = False

    def reconnect(self) -> bool:
        """Attempt to reconnect after connection loss."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("ASCOM max reconnection attempts reached")
            return False
        self._reconnect_attempts += 1
        logger.info(
            f"ASCOM reconnection attempt "
            f"{self._reconnect_attempts}/{self._max_reconnect_attempts}"
        )
        return self.connect()

    def _safe_read(self, property_name: str, default=None):
        """Safely read a property from the ASCOM telescope object.

        Handles COM errors gracefully. Logs WARNING only on first failure
        per property, then DEBUG to avoid log spam.
        Returns default value on failure.
        """
        if self._telescope is None or not self._connected:
            return default
        try:
            value = getattr(self._telescope, property_name)
            # Property recovered — allow future warning if it fails again
            self._warned_properties.discard(property_name)
            return value
        except AttributeError:
            logger.debug(f"ASCOM property not available: {property_name}")
            return default
        except Exception as e:
            if property_name not in self._warned_properties:
                logger.warning(f"ASCOM error reading {property_name}: {e}")
                self._warned_properties.add(property_name)
            else:
                logger.debug(f"ASCOM error reading {property_name}: {e}")
            # Check if connection is lost
            self._check_connection_alive()
            return default

    def _check_connection_alive(self):
        """Check if the ASCOM connection is still alive."""
        if self._telescope is None:
            self._connected = False
            return
        try:
            _ = self._telescope.Connected
        except Exception:
            logger.warning("ASCOM connection lost")
            self._connected = False

    # ── MountConnection abstract methods ─────────────────────────

    def get_ra(self) -> Optional[str]:
        """Get Right Ascension from ASCOM driver.

        ASCOM RightAscension returns decimal hours (0..24).
        Converts to HH:MM:SS.dd format.
        """
        ra_hours = self._safe_read("RightAscension")
        if ra_hours is None:
            return None
        try:
            return _hours_to_hms(float(ra_hours))
        except (ValueError, TypeError):
            logger.warning(f"Invalid RA value from ASCOM: {ra_hours}")
            return None

    def get_dec(self) -> Optional[str]:
        """Get Declination from ASCOM driver.

        ASCOM Declination returns decimal degrees (-90..+90).
        Converts to +DD:MM:SS.d format.
        """
        dec_deg = self._safe_read("Declination")
        if dec_deg is None:
            return None
        try:
            return _degrees_to_dms(float(dec_deg))
        except (ValueError, TypeError):
            logger.warning(f"Invalid DEC value from ASCOM: {dec_deg}")
            return None

    def get_status(self) -> MountStatus:
        """Get mount status from ASCOM properties.

        Checks Tracking, Slewing, AtPark to determine status.
        """
        if self._telescope is None or not self._connected:
            return MountStatus.UNKNOWN

        try:
            # Check Slewing first (transient state)
            slewing = self._safe_read("Slewing", False)
            if slewing:
                return MountStatus.SLEWING

            # Check if parked
            at_park = self._safe_read("AtPark", False)
            if at_park:
                return MountStatus.PARKED

            # Check tracking
            tracking = self._safe_read("Tracking", False)
            if tracking:
                return MountStatus.TRACKING

            return MountStatus.IDLE

        except Exception as e:
            logger.warning(f"Error getting ASCOM status: {e}")
            return MountStatus.UNKNOWN

    def get_mount_time(self) -> Optional[str]:
        """Get mount UTC time from ASCOM UTCDate property.

        Returns time as HH:MM:SS string in UTC.
        Falls back to PC UTC clock if UTCDate is unavailable.

        NOTE: SiderealTime is NOT used as fallback because it is astronomical
        sidereal time, not civil time. Comparing it with PC clock would give
        nonsensical time differences (the Java original used :GL# local time
        instead, but ASCOM provides UTCDate which is the correct approach).
        """
        if not getattr(self, '_utcdate_failed', False):
            utc_date = self._safe_read("UTCDate")
            if utc_date is not None:
                try:
                    if isinstance(utc_date, datetime):
                        return utc_date.strftime("%H:%M:%S")
                    # Try converting OLE float date
                    from datetime import timedelta
                    ole_epoch = datetime(1899, 12, 30)
                    dt = ole_epoch + timedelta(days=float(utc_date))
                    return dt.strftime("%H:%M:%S")
                except Exception:
                    pass
            # UTCDate not working — fall through to PC UTC clock
            self._utcdate_failed = True
            logger.warning("UTCDate unavailable from ASCOM driver, using PC UTC clock")

        # Fallback: use PC UTC time (time diff will be ~0 but loop times still useful)
        return datetime.now(timezone.utc).strftime("%H:%M:%S")

    def get_firmware_version(self) -> str:
        """Get firmware/driver version from ASCOM.

        Tries DriverInfo first, then DriverVersion, then Description.
        """
        # Try DriverVersion (short version string)
        version = self._safe_read("DriverVersion")
        if version:
            return str(version)

        # Try DriverInfo (longer description with version)
        info = self._safe_read("DriverInfo")
        if info:
            return str(info)

        # Fallback to Description
        desc = self._safe_read("Description")
        if desc:
            return str(desc)

        return "Unknown"

    def get_product_name(self) -> str:
        """Get mount product name from ASCOM Name property."""
        name = self._safe_read("Name")
        if name:
            return str(name)
        return "Unknown ASCOM Mount"

    def get_mount_id(self) -> str:
        """Get mount identifier from ASCOM Description property."""
        desc = self._safe_read("Description")
        if desc:
            return str(desc)
        # Fallback to driver ID
        return self._driver_id

    def get_pier_side(self) -> PierSide:
        """Get pier side from ASCOM SideOfPier property.

        ASCOM values: 0 = pierEast, 1 = pierWest.
        """
        side = self._safe_read("SideOfPier", _ASCOM_PIER_UNKNOWN)
        try:
            side_int = int(side)
            if side_int == _ASCOM_PIER_EAST:
                return PierSide.EAST
            elif side_int == _ASCOM_PIER_WEST:
                return PierSide.WEST
        except (ValueError, TypeError):
            pass
        return PierSide.UNKNOWN

    def get_azimuth(self) -> Optional[float]:
        """Get telescope azimuth in degrees from ASCOM Azimuth property."""
        az = self._safe_read("Azimuth")
        if az is None:
            return None
        try:
            return float(az)
        except (ValueError, TypeError):
            return None

    def get_altitude(self) -> Optional[float]:
        """Get telescope altitude in degrees from ASCOM Altitude property."""
        alt = self._safe_read("Altitude")
        if alt is None:
            return None
        try:
            return float(alt)
        except (ValueError, TypeError):
            return None

    # ── Optional methods ─────────────────────────────────────────

    def get_target_ra(self) -> Optional[str]:
        """Get target RA from ASCOM TargetRightAscension property.

        Returns HH:MM:SS.dd format, or None if no target set.
        """
        ra_hours = self._safe_read("TargetRightAscension")
        if ra_hours is None:
            return None
        try:
            return _hours_to_hms(float(ra_hours))
        except (ValueError, TypeError):
            return None

    def get_target_dec(self) -> Optional[str]:
        """Get target DEC from ASCOM TargetDeclination property.

        Returns +DD:MM:SS.d format, or None if no target set.
        """
        dec_deg = self._safe_read("TargetDeclination")
        if dec_deg is None:
            return None
        try:
            return _degrees_to_dms(float(dec_deg))
        except (ValueError, TypeError):
            return None

    def is_refraction_enabled(self) -> Optional[bool]:
        """Check if refraction correction is enabled.

        Not all ASCOM drivers support this. Returns None if unavailable.
        For 10Micron, this may not be exposed via ASCOM; use send_raw_command(":GREF#").
        """
        # ASCOM doesn't have a standard refraction property
        # Try 10Micron-specific raw command if CommandString is available
        result = self.send_raw_command(":GREF#")
        if result is not None:
            return result.strip().rstrip("#") == "1"
        return None

    def get_refraction_mode(self) -> Optional[str]:
        """Get refraction correction mode via raw command (10Micron specific)."""
        result = self.send_raw_command(":GREF#")
        if result is None:
            return None
        val = result.strip().rstrip("#")
        mode_map = {
            '0': 'not_updating',
            '1': 'not_updating_tracking',
            '2': 'continuously_updating',
        }
        return mode_map.get(val)

    def is_dual_tracking_enabled(self) -> Optional[bool]:
        """Check dual tracking via raw command (10Micron specific)."""
        result = self.send_raw_command(":Gdat#")
        if result is None:
            return None
        return result.strip().rstrip("#") == "1"

    def get_tracking_rate(self) -> Optional[str]:
        """Get current tracking rate from ASCOM TrackingRate property.

        ASCOM values: 0=Sidereal, 1=Lunar, 2=Solar, 3=King.
        """
        rate = self._safe_read("TrackingRate")
        if rate is None:
            return None
        try:
            rate_int = int(rate)
            return _TRACKING_RATES.get(rate_int, f"Unknown ({rate_int})")
        except (ValueError, TypeError):
            return str(rate)

    def get_latitude(self) -> Optional[str]:
        """Get site latitude from ASCOM SiteLatitude property.

        ASCOM returns decimal degrees. Converts to DMS format.
        """
        lat = self._safe_read("SiteLatitude")
        if lat is None:
            return None
        try:
            return _degrees_to_dms_lat(float(lat))
        except (ValueError, TypeError):
            return None

    def get_longitude(self) -> Optional[str]:
        """Get site longitude from ASCOM SiteLongitude property.

        ASCOM returns decimal degrees. Converts to DMS format.
        """
        lon = self._safe_read("SiteLongitude")
        if lon is None:
            return None
        try:
            return _degrees_to_dms_lon(float(lon))
        except (ValueError, TypeError):
            return None

    def get_elevation(self) -> Optional[float]:
        """Get site elevation in meters from ASCOM SiteElevation property."""
        elev = self._safe_read("SiteElevation")
        if elev is None:
            return None
        try:
            return float(elev)
        except (ValueError, TypeError):
            return None

    def get_ra_axis_position(self) -> Optional[float]:
        """Get RA axis raw position.

        Uses CommandString(":GaXa#") for 10Micron mounts.
        Not available on all ASCOM drivers.
        """
        result = self.send_raw_command(":GaXa#")
        if result is None:
            return None
        try:
            return float(result.strip().rstrip("#"))
        except ValueError:
            return None

    def get_dec_axis_position(self) -> Optional[float]:
        """Get DEC axis raw position.

        Uses CommandString(":GaXb#") for 10Micron mounts.
        Not available on all ASCOM drivers.
        """
        result = self.send_raw_command(":GaXb#")
        if result is None:
            return None
        try:
            return float(result.strip().rstrip("#"))
        except ValueError:
            return None

    def send_raw_command(self, command: str) -> Optional[str]:
        """Send a raw command via ASCOM CommandString method.

        This is driver-specific and may not be supported by all ASCOM drivers.
        Commonly used for 10Micron-specific LX200 commands.

        Args:
            command: The raw command string (e.g. ":GR#", ":GREF#")

        Returns:
            Response string or None if not supported/failed.
        """
        if self._telescope is None or not self._connected:
            return None
        try:
            # ASCOM CommandString(command, raw=False)
            # raw=False means the driver handles termination
            result = self._telescope.CommandString(command, False)
            if result is not None:
                return str(result)
            return None
        except AttributeError:
            logger.debug("ASCOM driver does not support CommandString")
            return None
        except Exception as e:
            logger.debug(f"ASCOM CommandString error for '{command}': {e}")
            return None

    def set_high_precision(self) -> bool:
        """Set high precision mode.

        For ASCOM, precision is inherent (floating point values).
        For 10Micron via ASCOM, try sending :U# via CommandString.
        """
        # ASCOM natively provides high-precision float values,
        # but for 10Micron mounts we also try the LX200 command
        self.send_raw_command(":U#")
        return True

    def is_gps_synced(self) -> Optional[bool]:
        """Check if GPS is synced.

        Not a standard ASCOM property. Try 10Micron command :gps#.
        """
        result = self.send_raw_command(":gps#")
        if result is not None:
            return result.strip().rstrip("#") == "1"
        return None

    def get_environment(self) -> EnvironmentSample:
        """Get environmental and diagnostic data via ASCOM/LX200 commands.

        Uses 10Micron-specific LX200 commands via ASCOM CommandString.
        All commands confirmed working on 10Micron GM1000HPS with ASCOM driver v1.7.
        """
        sample = EnvironmentSample()

        # External temperature from :GRTMP#
        result = self.send_raw_command(":GRTMP#")
        if result is not None:
            try:
                sample.temperature_ext = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Barometric pressure from :GRPRS#
        result = self.send_raw_command(":GRPRS#")
        if result is not None:
            try:
                sample.pressure = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Internal temperature from :GTMP1#
        result = self.send_raw_command(":GTMP1#")
        if result is not None:
            try:
                sample.temperature_int = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Extended mount status from :Gstat#
        result = self.send_raw_command(":Gstat#")
        if result is not None:
            try:
                sample.mount_status_code = int(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Tracking rate multiplier from :GT#
        result = self.send_raw_command(":GT#")
        if result is not None:
            try:
                sample.tracking_rate = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Minutes until meridian flip from :Gmte#
        result = self.send_raw_command(":Gmte#")
        if result is not None:
            try:
                val = result.strip().rstrip("#")
                if val:
                    sample.meridian_flip_minutes = float(val)
            except ValueError:
                pass

        # Pier side from :pS#
        result = self.send_raw_command(":pS#")
        if result is not None:
            val = result.strip().rstrip("#").lower()
            if "east" in val:
                sample.pier_side = PierSide.EAST
            elif "west" in val:
                sample.pier_side = PierSide.WEST

        # Alignment model info from :getain#
        result = self.send_raw_command(":getain#")
        if result is not None:
            try:
                # Format: "NN,RR.R,PPPP.PP#"
                # NN = number of stars, RR.R = RMS arcsec, PPPP.PP = polar error deg
                val = result.strip().rstrip("#")
                parts = val.split(",")
                if len(parts) >= 3:
                    sample.alignment_stars = int(parts[0])
                    sample.alignment_rms = float(parts[1])
                    sample.polar_error_deg = float(parts[2])
            except (ValueError, IndexError):
                pass

        return sample
