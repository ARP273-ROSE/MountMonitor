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
    # Four decimals (0.0015″): two decimals quantised the reading to
    # 0.15″ x cos(dec), comparable with the jitter being measured.
    s = round(s, 4)
    if s >= 60.0:
        s -= 60.0; m += 1
    if m >= 60:
        m -= 60; h += 1
    return f"{sign}{h:02d}:{m:02d}:{s:07.4f}"


def _degrees_to_dms(degrees: float) -> str:
    """Convert decimal degrees to +DD:MM:SS.d string."""
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    remainder = (degrees - d) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    s = round(s, 3)
    if s >= 60.0:
        s -= 60.0; m += 1
    if m >= 60:
        m -= 60; d += 1
    return f"{sign}{d:02d}:{m:02d}:{s:06.3f}"


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


def is_tenmicron_driver(driver_id: str) -> bool:
    """The 10Micron ASCOM driver (ASCOM.tenmicron_mount.Telescope, ...)."""
    d = (driver_id or "").lower()
    return "tenmicron" in d or "10micron" in d


class ASCOMConnection(MountConnection):
    """ASCOM Telescope driver connection via Windows COM.

    Requires:
        - Windows platform
        - comtypes package (pip install comtypes)
        - An ASCOM telescope driver installed (e.g. ASCOM.tenmicron_mount.Telescope)

    The COM object is created and accessed from a dedicated thread to ensure
    proper COM apartment threading (CoInitialize/CoUninitialize).
    """

    def __init__(self, driver_id: str = "ASCOM.tenmicron_mount.Telescope",
                 tenmicron_commands: bool = False):
        """Initialize ASCOM connection.

        Args:
            driver_id: ASCOM driver ProgID (e.g. "ASCOM.tenmicron_mount.Telescope")
            tenmicron_commands: allow 10Micron LX200 commands through the
                driver (honoured only for the 10Micron driver)
        """
        super().__init__()
        self.tenmicron_commands = bool(tenmicron_commands) and is_tenmicron_driver(driver_id)
        self._driver_id = driver_id
        self._protocol = ConnectionProtocol.ASCOM
        self._telescope = None  # COM object
        self._reconnect_attempts = 0
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

    def thread_enter(self) -> None:
        self._ensure_com_init()

    def thread_exit(self) -> None:
        self._com_uninit()

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
        """One reconnection attempt after a connection loss.

        No ceiling: the attempts used to stop for good after five, about
        thirty seconds, so a mount that rebooted (one to two minutes) was
        never found again and the rest of the night was lost. The poller now
        spaces the attempts out (2, 4, 8... up to 60 s)."""
        self._reconnect_attempts += 1
        logger.info(f"ASCOM reconnection attempt {self._reconnect_attempts}")
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
                    # Hundredths kept: truncated to the second, the PC-mount
                    # offset became a 0-1000 ms sawtooth and the mount loop
                    # time read 0 or 1000 ms.
                    if isinstance(utc_date, datetime):
                        return utc_date.strftime("%H:%M:%S.%f")[:-4]
                    # Try converting OLE float date
                    from datetime import timedelta
                    ole_epoch = datetime(1899, 12, 30)
                    dt = ole_epoch + timedelta(days=float(utc_date))
                    return dt.strftime("%H:%M:%S.%f")[:-4]
                except Exception:
                    pass
            # UTCDate not working — fall through to PC UTC clock
            self._utcdate_failed = True
            logger.warning("UTCDate unavailable from ASCOM driver, using PC UTC clock")

        # Fallback: use PC UTC time (time diff will be ~0 but loop times still useful)
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-4]

    def get_firmware_version(self) -> str:
        """The MOUNT's firmware (10Micron :GVN#), with the driver version.

        The ASCOM DriverVersion alone ("1.7") was shown as the firmware: it
        is the driver's, not the mount's (fw 3.4 on the GM1000 measured).
        """
        driver = self._safe_read("DriverVersion")
        mount_fw = self.send_raw_command(":GVN#")
        mount_fw = (mount_fw or '').strip().rstrip('#')
        if mount_fw:
            return f"{mount_fw} (ASCOM {driver})" if driver else mount_fw
        if driver:
            return str(driver)
        info = self._safe_read("DriverInfo")
        if info:
            return str(info)
        desc = self._safe_read("Description")
        if desc:
            return str(desc)
        return "Unknown"

    def get_product_name(self) -> str:
        """The mount's product name (10Micron :GVP#), else the driver Name
        ("10Micron Mount Driver", which named the driver, not the mount)."""
        product = (self.send_raw_command(":GVP#") or '').strip().rstrip('#')
        if product:
            return product
        name = self._safe_read("Name")
        if name:
            return str(name)
        return "Unknown ASCOM Mount"

    def get_mount_id(self) -> str:
        """No identifier: ASCOM's Description names the DRIVER ("10Micron
        Mount ASCOM Driver"), which the window printed as the mount's
        identifier. Product and firmware already come from the mount."""
        return ""

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
        # ASCOM's DoesRefraction (MM3's equivalent of :GREF#); the 10Micron
        # command only when the option allows it and the property is missing.
        value = self._safe_read("DoesRefraction")
        if value is not None:
            return bool(value)
        return self.send_raw_bool(":GREF#")

    def get_refraction_mode(self) -> Optional[str]:
        """Refraction update type via raw command :WSG# (10Micron specific).

        Not :GREF#, which only tells whether the correction is on (see
        lx200_protocol.get_refraction_mode)."""
        result = self.send_raw_command(":WSG#")
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
        return self.send_raw_bool(":Gdat#")

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

        ASCOM returns decimal degrees, counted positive EAST. The LX200
        protocol counts the other way, and the string produced here is read
        back with the LX200 convention -- so the sign is flipped once, at
        the source, and there is one convention in the rest of the program
        instead of two.

        Getting this wrong does not fail loudly: it moves the observatory to
        the wrong side of Greenwich. On a site 5.71 deg east it shifted every
        twilight by 46 minutes, which reads as plausible.
        """
        lon = self._safe_read("SiteLongitude")
        if lon is None:
            return None
        try:
            return _degrees_to_dms_lon(-float(lon))
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
        """Send a raw LX200 command through the driver's CommandString.

        Sent RAW (raw=True, the full ":...#" command): the 10Micron driver
        1.7.2 adds ':' and '#' itself when raw=False, so ":GREF#" went out
        as "::GREF##", failed its validation and EVERY 10Micron command
        returned nothing in ASCOM mode (measured on a GM1000HPS fw 3.4,
        22/11/2026). raw=False with the bare command is kept as a fallback
        for drivers that only accept that form.

        Returns the reply (trailing '#' kept, callers strip it), or None
        when the driver has no CommandString or refuses the command. A
        refusal is not a lost connection.
        """
        if self._telescope is None or not self._connected:
            return None
        if not self.tenmicron_commands:
            # Pure ASCOM (default, as MM3): an LX200 command is never sent
            # to an ASCOM driver, which may belong to any make of mount.
            return None
        bare = command.strip().lstrip(':').rstrip('#')
        last_error = None
        for cmd, raw in ((command, True), (bare, False)):
            try:
                result = self._telescope.CommandString(cmd, raw)
                return str(result) if result is not None else None
            except AttributeError:
                logger.debug("ASCOM driver does not support CommandString")
                return None
            except Exception as e:
                last_error = e
        self._note_refused(command, last_error)
        return None

    def send_raw_bool(self, command: str) -> Optional[bool]:
        """A command whose reply is ONE character without '#' (:GREF#,
        :Gdat#). The 10Micron driver only accepts those through
        CommandBool; CommandString rejects them."""
        if self._telescope is None or not self._connected:
            return None
        if not self.tenmicron_commands:
            return None
        try:
            return bool(self._telescope.CommandBool(command, True))
        except AttributeError:
            pass
        except Exception as e:
            logger.debug(f"ASCOM CommandBool refused '{command}': {e}")
        result = self.send_raw_command(command)
        if result is None:
            return None
        return result.strip().rstrip('#') == '1'

    def _note_refused(self, command: str, error) -> None:
        """Log a refused command once, not at every poll."""
        refused = self.__dict__.setdefault('_refused_commands', set())
        if command not in refused:
            refused.add(command)
            logger.info(f"ASCOM driver refused '{command}': {error}")

    def read_mount_preferences(self) -> Optional[dict]:
        """The 10Micron preference list through the driver, when it lets
        it through. The 10Micron driver 1.7.2 rejects :PRclr# and :PRlist#
        unless "unchecked raw commands" is allowed in its setup dialog;
        `preferences_refused` then tells the window why nothing came back."""
        self.preferences_refused = False
        self.preferences_pure_ascom = not self.tenmicron_commands
        if self.preferences_pure_ascom:
            return None
        from .lx200_protocol import LX200Connection, parse_prlist_chunk
        cleared = self.send_raw_bool(':PRclr#')
        prefs: dict = {}
        for _ in range(LX200Connection.PRLIST_MAX_CHUNKS):
            chunk = self.send_raw_command(':PRlist#')
            if chunk is None:
                break
            done, empty = parse_prlist_chunk(chunk, prefs)
            if done or empty:
                break
        if not prefs:
            self.preferences_refused = (cleared is None and ':PRlist#' in
                                        self.__dict__.get('_refused_commands', ()))
            return None
        return prefs

    def check_mount_settings(self) -> Optional[dict]:
        prefs = self.read_mount_preferences()
        if prefs is None:
            return None
        from .lx200_protocol import summarise_preferences
        return summarise_preferences(prefs)

    def set_high_precision(self) -> bool:
        """Set high precision mode.

        For ASCOM, precision is inherent (floating point values).
        For 10Micron via ASCOM, try sending :U# via CommandString.
        """
        # ASCOM gives floating-point values: nothing to set. Sending the
        # LX200 :U# here would TOGGLE the precision of the mount for every
        # other program connected through the driver (NINA...).
        return True

    def is_gps_synced(self) -> Optional[bool]:
        """GPS time synchronisation, as in LX200Connection.is_gps_synced:
        :gtgpps# from firmware 3.2.5, :gtg# before. The old ":gps#" is not
        a 10Micron command (the mount answers an empty "#")."""
        firmware = self.send_raw_command(":GVN#")
        import re
        nums = re.findall(r'\d+', firmware or '')
        try:
            recent = tuple(int(n) for n in nums[:3]) >= (3, 2, 5)
        except ValueError:
            recent = False
        for cmd in ((":gtgpps#", ":gtg#") if recent else (":gtg#",)):
            result = self.send_raw_command(cmd)
            value = (result or '').strip().rstrip('#')
            if value in ('0', '1'):
                return value == '1'
        return None

    def get_environment(self) -> EnvironmentSample:
        """Get environmental and diagnostic data via ASCOM/LX200 commands.

        Uses 10Micron-specific LX200 commands via ASCOM CommandString.
        Sent raw (see send_raw_command): with raw=False the 10Micron driver
        1.7.2 rejected every one of them.
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
        from .lx200_protocol import apply_getain
        apply_getain(self.send_raw_command(":getain#"), sample)

        return sample
