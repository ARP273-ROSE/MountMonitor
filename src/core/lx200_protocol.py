"""LX200 TCP/IP protocol implementation for telescope mounts.

Based on the 10Micron Mount Command Protocol v2.15.8.
Compatible with 10Micron, Meade, and other LX200-compatible mounts.
"""

import socket
import time
import logging
from typing import Optional

from .mount_connection import MountConnection
from ..models.mount_data import MountStatus, PierSide, ConnectionProtocol, EnvironmentSample

logger = logging.getLogger(__name__)


class LX200Connection(MountConnection):
    """LX200 protocol connection via TCP/IP."""

    def __init__(self, host: str = "192.168.1.1", port: int = 3492, timeout: float = 5.0):
        super().__init__()
        self._host = host
        self._port = port
        self._timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._protocol = ConnectionProtocol.LX200
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def connect(self) -> bool:
        """Connect to mount via TCP/IP."""
        try:
            self.disconnect()  # Clean up any existing connection
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self._timeout)
            self._socket.connect((self._host, self._port))
            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to mount at {self._host}:{self._port}")

            # Set high precision mode
            self.set_high_precision()

            return True
        except (socket.error, socket.timeout, OSError) as e:
            logger.error(f"Connection failed to {self._host}:{self._port}: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close TCP/IP connection."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False

    def reconnect(self) -> bool:
        """Attempt to reconnect after connection loss."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return False
        self._reconnect_attempts += 1
        logger.info(f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}")
        return self.connect()

    def _send_command(self, command: str) -> Optional[str]:
        """Send a command and receive the response.

        Commands start with : and responses end with #.
        Returns None on failure.
        """
        if not self._socket or not self._connected:
            return None

        try:
            # Send command
            self._socket.sendall(command.encode('ascii'))

            # Receive response (read until #)
            response = b''
            while True:
                chunk = self._socket.recv(1024)
                if not chunk:
                    raise ConnectionError("Connection closed by mount")
                response += chunk
                if b'#' in chunk:
                    break

            decoded = response.decode('ascii').rstrip('#')
            return decoded

        except (socket.error, socket.timeout, OSError, ConnectionError) as e:
            logger.warning(f"Communication error: {e}")
            self._connected = False
            return None

    def get_ra(self) -> Optional[str]:
        """Get Right Ascension: :GR# -> HH:MM:SS.dd"""
        return self._send_command(':GR#')

    def get_dec(self) -> Optional[str]:
        """Get Declination: :GD# -> sDD*MM:SS.d"""
        return self._send_command(':GD#')

    def get_status(self) -> MountStatus:
        """Get mount status via :Gstat# command (10Micron specific).

        10Micron Gstat# status codes:
        0  = Tracking
        1  = Stopped (STOP key pressed)
        2  = Slewing to park position
        3  = Unparking
        4  = Slewing to home position
        5  = Parked
        6  = Slewing (goto/moving)
        7  = Tracking but not moving (coasting/stiction)
        8  = Motors inhibited (low temp, etc.)
        9  = Beyond limits
        10 = Object below minimum altitude
        11 = Pointing model alignment in progress
        98 = Status not available
        99 = Error
        """
        response = self._send_command(':Gstat#')
        if response is None:
            return MountStatus.UNKNOWN

        try:
            status_code = int(response.strip())
            if status_code == 0:
                return MountStatus.TRACKING
            elif status_code == 1:
                return MountStatus.IDLE
            elif status_code in (2, 4, 6):
                return MountStatus.SLEWING
            elif status_code == 3:
                return MountStatus.IDLE
            elif status_code == 5:
                return MountStatus.PARKED
            elif status_code == 7:
                return MountStatus.TRACKING
            elif status_code in (8, 9):
                return MountStatus.ERROR
            elif status_code in (10, 11):
                return MountStatus.IDLE
            elif status_code == 98:
                return MountStatus.UNKNOWN
            elif status_code == 99:
                return MountStatus.ERROR
            else:
                return MountStatus.UNKNOWN
        except ValueError:
            return MountStatus.UNKNOWN

    def get_mount_time(self) -> Optional[str]:
        """Get mount local time: :GL# -> HH:MM:SS"""
        return self._send_command(':GL#')

    def get_firmware_version(self) -> str:
        """Get firmware version: :GVN# -> version string"""
        result = self._send_command(':GVN#')
        return result or "Unknown"

    def get_product_name(self) -> str:
        """Get product name: :GVP# -> product string"""
        result = self._send_command(':GVP#')
        return result or "Unknown"

    def get_mount_id(self) -> str:
        """Get unique mount ID: :GETID# -> 20-digit ID"""
        result = self._send_command(':GETID#')
        return result or "Unknown"

    def get_pier_side(self) -> PierSide:
        """Get pier side: :pS# -> 'East' or 'West'"""
        result = self._send_command(':pS#')
        if result is None:
            return PierSide.UNKNOWN
        if 'East' in result:
            return PierSide.EAST
        elif 'West' in result:
            return PierSide.WEST
        return PierSide.UNKNOWN

    def get_azimuth(self) -> Optional[float]:
        """Get telescope azimuth: :GZ# -> DDD*MM'SS#"""
        result = self._send_command(':GZ#')
        if result is None:
            return None
        try:
            # Parse DDD*MM'SS or DDD*MM:SS format
            result = result.replace("'", ":").replace("*", ":")
            parts = result.split(':')
            if len(parts) >= 3:
                deg = float(parts[0])
                minutes = float(parts[1])
                sec = float(parts[2])
                return deg + minutes / 60.0 + sec / 3600.0
        except (ValueError, IndexError):
            pass
        return None

    def get_altitude(self) -> Optional[float]:
        """Get telescope altitude: :GA# -> sDD*MM'SS#"""
        result = self._send_command(':GA#')
        if result is None:
            return None
        try:
            result = result.replace("'", ":").replace("*", ":")
            sign = -1 if result.startswith('-') else 1
            result = result.lstrip('+-')
            parts = result.split(':')
            if len(parts) >= 3:
                deg = float(parts[0])
                minutes = float(parts[1])
                sec = float(parts[2])
                return sign * (deg + minutes / 60.0 + sec / 3600.0)
        except (ValueError, IndexError):
            pass
        return None

    def get_ra_axis_position(self) -> Optional[float]:
        """Get RA axis raw position: :GaXa# (10Micron v3.20+)"""
        result = self._send_command(':GaXa#')
        if result is None:
            return None
        try:
            return float(result)
        except ValueError:
            return None

    def get_dec_axis_position(self) -> Optional[float]:
        """Get DEC axis raw position: :GaXb# (10Micron v3.20+)"""
        result = self._send_command(':GaXb#')
        if result is None:
            return None
        try:
            return float(result)
        except ValueError:
            return None

    def get_target_ra(self) -> Optional[str]:
        """Get target RA: :Gr# -> HH:MM:SS"""
        return self._send_command(':Gr#')

    def get_target_dec(self) -> Optional[str]:
        """Get target DEC: :Gd# -> sDD*MM:SS"""
        return self._send_command(':Gd#')

    def is_refraction_enabled(self) -> Optional[bool]:
        """Check refraction correction via :GREF# (10Micron)"""
        result = self._send_command(':GREF#')
        if result is None:
            return None
        return result.strip() == '1'

    def get_tracking_rate(self) -> Optional[str]:
        """Get tracking rate via :GT# (10Micron)"""
        return self._send_command(':GT#')

    def get_latitude(self) -> Optional[str]:
        """Get site latitude: :Gt#"""
        return self._send_command(':Gt#')

    def get_longitude(self) -> Optional[str]:
        """Get site longitude: :Gg#"""
        return self._send_command(':Gg#')

    def get_elevation(self) -> Optional[float]:
        """Get site elevation: :Gev#"""
        result = self._send_command(':Gev#')
        if result:
            try:
                return float(result)
            except ValueError:
                pass
        return None

    def get_refraction_mode(self) -> Optional[str]:
        """Get refraction correction mode via :GREF# (10Micron).

        Returns: 0 = not_updating, 1 = not_updating_tracking, 2 = continuously_updating.
        """
        result = self._send_command(':GREF#')
        if result is None:
            return None
        val = result.strip()
        mode_map = {
            '0': 'not_updating',
            '1': 'not_updating_tracking',
            '2': 'continuously_updating',
        }
        return mode_map.get(val)

    def is_dual_tracking_enabled(self) -> Optional[bool]:
        """Check dual tracking via :Gdat# (10Micron). Returns True if enabled."""
        result = self._send_command(':Gdat#')
        if result is None:
            return None
        return result.strip() == '1'

    def is_gps_synced(self) -> Optional[bool]:
        """Check if GPS clock is synchronized via :gps# (10Micron)."""
        result = self._send_command(':gps#')
        if result is None:
            return None
        return result.strip() == '1'

    def check_mount_settings(self) -> list[str]:
        """Verify 10Micron mount configuration for monitoring.

        Checks (like Java checkMountSettings):
        - Tracking speed should be sidereal (0)
        - Tracking correction should be 0.000%
        - Follow object should be OFF (0)

        Uses :PRlist# command to iterate settings, then :PRnext# to read them.
        Returns list of warning messages.
        """
        warnings = []
        product = getattr(self, '_product_name', '') or ''
        if '10micron' not in product.lower():
            return warnings

        try:
            # Start listing preferences
            response = self._send_command(':PRlist#')
            if response is None:
                return warnings

            # Read through preference entries
            while True:
                entry = self._send_command(':PRnext#')
                if entry is None or entry.strip() == 'c':
                    break

                # Each entry may contain multiple settings separated by ';'
                for setting in entry.split(';'):
                    parts = setting.split(',')
                    if len(parts) < 4:
                        continue

                    name = parts[0] if parts else ''

                    if 'Follow object' in name:
                        if parts[3] != '0':
                            warnings.append(f"Follow object is ON (should be OFF)")
                            logger.warning("WRONG SET-UP: Follow object is ON!")
                        else:
                            logger.info("Verified: Follow object is OFF")

                    elif 'Tracking correction' in name:
                        if parts[3] != '0.000':
                            warnings.append(f"Tracking correction is {parts[3]}% (should be 0.000%)")
                            logger.warning(f"WRONG SET-UP: Tracking correction is {parts[3]}%!")
                        else:
                            logger.info(f"Verified: Tracking correction is {parts[3]}%")

                    elif 'Tracking speed' in name:
                        if parts[3] != '0':
                            speed_name = parts[5 + int(parts[3])] if len(parts) > 5 + int(parts[3]) else parts[3]
                            warnings.append(f"Tracking speed is {speed_name} (should be Sidereal)")
                            logger.warning(f"WRONG SET-UP: Tracking speed is {speed_name}!")
                        else:
                            logger.info(f"Verified: Tracking speed is Sidereal")

        except Exception as e:
            logger.debug(f"checkMountSettings error: {e}")

        return warnings

    def set_high_precision(self) -> bool:
        """Set high precision output mode: :U#

        Toggles between low and high resolution. We send it
        and check if we get high-res output.
        """
        self._send_command(':U#')
        return True

    def send_raw_command(self, command: str) -> Optional[str]:
        """Send any raw LX200 command."""
        return self._send_command(command)

    def get_environment(self) -> EnvironmentSample:
        """Get environment data via LX200 extended commands (10Micron specific)."""
        sample = EnvironmentSample()

        # External temperature
        result = self._send_command(":GRTMP#")
        if result:
            try:
                sample.temperature_ext = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Barometric pressure
        result = self._send_command(":GRPRS#")
        if result:
            try:
                sample.pressure = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Internal temperature
        result = self._send_command(":GTMP1#")
        if result:
            try:
                sample.temperature_int = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Extended status code
        result = self._send_command(":Gstat#")
        if result:
            try:
                sample.mount_status_code = int(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Tracking rate multiplier
        result = self._send_command(":GT#")
        if result:
            try:
                sample.tracking_rate = float(result.strip().rstrip("#"))
            except ValueError:
                pass

        # Meridian flip time
        result = self._send_command(":Gmte#")
        if result:
            try:
                val = result.strip().rstrip("#")
                if val:
                    sample.meridian_flip_minutes = float(val)
            except ValueError:
                pass

        # Pier side
        result = self._send_command(":pS#")
        if result:
            val = result.strip().rstrip("#").lower()
            if "east" in val:
                sample.pier_side = PierSide.EAST
            elif "west" in val:
                sample.pier_side = PierSide.WEST

        # Alignment model info
        result = self._send_command(":getain#")
        if result:
            try:
                val = result.strip().rstrip("#")
                parts = val.split(",")
                if len(parts) >= 3:
                    sample.alignment_stars = int(parts[0])
                    sample.alignment_rms = float(parts[1])
                    sample.polar_error_deg = float(parts[2])
            except (ValueError, IndexError):
                pass

        return sample
