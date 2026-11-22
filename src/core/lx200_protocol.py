"""LX200 TCP/IP protocol implementation for telescope mounts.

Based on the 10Micron Mount Command Protocol v2.15.8.
Compatible with 10Micron, Meade, and other LX200-compatible mounts.
"""

import socket
import threading
import time
import logging
from typing import Optional

from .mount_connection import MountConnection
from ..models.mount_data import MountStatus, PierSide, ConnectionProtocol, EnvironmentSample

logger = logging.getLogger(__name__)



def parse_prlist_chunk(chunk: str, prefs: dict) -> tuple:
    """Add one :PRlist# chunk to `prefs`; return (complete, empty).

    "Name,type,W,value,...;" entries; a last entry "x" means more follows,
    "c" that the list is complete."""
    entries = [e for e in str(chunk).strip().rstrip('#').split(';') if e != '']
    done = False
    for entry in entries:
        if entry in ('c', 'x'):
            done = entry == 'c'
            continue
        fields = entry.split(',')
        prefs[fields[0].strip()] = [f.strip() for f in fields[1:]]
    return done, not entries


def summarise_preferences(prefs: dict) -> dict:
    """What MountMonitor checks in the preference list (see
    LX200Connection.check_mount_settings)."""
    result = {}
    for name, f in prefs.items():
        if len(f) < 3:
            continue
        value = f[2]                    # Name,type,W,VALUE,...
        low = name.lower()
        if low.startswith('follow object'):
            result["follow_object"] = value != '0'
        elif low.startswith('tracking correction'):
            result["tracking_correction"] = value
        elif low.startswith('custom tracking rate r.a'):
            result["custom_rate_ra"] = value
        elif low.startswith('custom tracking rate dec'):
            result["custom_rate_dec"] = value
        elif low.startswith('tracking speed'):
            try:
                choices = f[4:]        # count, then the names
                result["tracking_speed"] = choices[int(value)]
            except (ValueError, IndexError):
                result["tracking_speed"] = value
    return result



def parse_getain(reply) -> dict:
    """The alignment model from :getain# (10Micron protocol 3.2.5, p. 9):

        ZZZ.ZZZZ,+AA.AAAA,EE.EEEE,PPP.PP,+OO.OOOO,+aa.aa,+bb.bb,NN,RRRRR.R#

    azimuth and altitude of the RA axis, polar align error (deg), position
    angle, orthogonality error (deg), knob turns (az, alt), NUMBER OF MODEL
    TERMS, expected RMS (arcsec). "E#" below two stars; any field may be "E"
    when not computed (RMS and terms below 4 stars, polar error on alt-az).
    The old reading took the azimuth as the star count, so it always failed.
    """
    val = (reply or '').strip().rstrip('#')
    parts = [p.strip() for p in val.split(',')]
    if len(parts) < 9:
        return {}

    def num(text, kind=float):
        try:
            return kind(float(text)) if text and text.upper() != 'E' else None
        except ValueError:
            return None
    return {'polar_error_deg': num(parts[2]), 'orthogonality_deg': num(parts[4]),
            'terms': num(parts[7], int), 'rms': num(parts[8])}


def apply_getain(reply, sample) -> None:
    info = parse_getain(reply)
    if info:
        sample.alignment_stars = info['terms']       # number of model terms (field kept for the .env column)
        sample.alignment_rms = info['rms']
        sample.polar_error_deg = info['polar_error_deg']

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
        # The socket is shared between the poller's QThread and the GUI thread
        # (post-slew checks, get_target_ra/dec): without a lock, two interleaved
        # commands steal each other's replies (an RA read as the reply to a
        # Gstat). Every send/receive pair must be atomic.
        self._io_lock = threading.Lock()

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

    def abort(self) -> None:
        s = self._socket
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def reconnect(self) -> bool:
        """One reconnection attempt after a connection loss.

        No ceiling: the attempts used to stop for good after five, about
        thirty seconds, so a mount that rebooted (one to two minutes) was
        never found again and the rest of the night was lost. The poller now
        spaces the attempts out (2, 4, 8... up to 60 s)."""
        self._reconnect_attempts += 1
        logger.info(f"Reconnection attempt {self._reconnect_attempts}")
        return self.connect()

    # Maximum response size to prevent unbounded buffer growth (security)
    _MAX_RESPONSE_BYTES = 4096

    def _drain(self):
        """Drop bytes left over from an earlier exchange (a reply that came
        after its timeout). Read as the start of the next answer, one stray
        "1" shifted every reply that followed: the status read as PARKED
        while the mount tracked."""
        import select
        try:
            while select.select([self._socket], [], [], 0)[0]:
                if not self._socket.recv(1024):
                    break
        except (OSError, ValueError):
            pass

    def _send_command(self, command: str, fixed_len: Optional[int] = None) -> Optional[str]:
        """Send a command and receive the response.

        Commands start with : and responses end with #. A few 10Micron
        commands answer without the '#' (":GREF#", ":Gdat#", ":Guaf#" answer
        one character '0'/'1' -- MountWizzard4 lists them as COMMAND_B):
        for those pass `fixed_len`, the number of characters to read.
        Waiting for a '#' that never comes cost the 5 s timeout and a
        reconnection at every check.
        Returns None on failure.
        Security: response buffer is bounded to _MAX_RESPONSE_BYTES.
        """
        if not self._socket or not self._connected:
            return None

        with self._io_lock:
            try:
                self._drain()
                # Send command
                self._socket.sendall(command.encode('ascii'))

                # Receive response (read until #, or fixed_len chars, or limit)
                response = b''
                while True:
                    chunk = self._socket.recv(1024)
                    if not chunk:
                        raise ConnectionError("Connection closed by mount")
                    response += chunk
                    if fixed_len is not None:
                        if len(response) >= fixed_len:
                            break
                    elif b'#' in chunk:
                        break
                    if len(response) > self._MAX_RESPONSE_BYTES:
                        logger.warning(f"Response exceeded {self._MAX_RESPONSE_BYTES} bytes, aborting")
                        raise ConnectionError("Response too large")

                # A stray byte (line noise, another program on the port) must
                # not escape as UnicodeDecodeError: it crashed the GUI-side
                # checks and produced a false crash report.
                decoded = response.decode('ascii', 'replace').rstrip('#')
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
        self._firmware = result or ""
        return result or "Unknown"

    def get_product_name(self) -> str:
        """Get product name: :GVP# -> product string"""
        result = self._send_command(':GVP#')
        # Remembered for check_mount_settings(), which only applies to
        # 10Micron mounts — without it the post-slew check never ran.
        self._product_name = result or "Unknown"
        return self._product_name

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
        result = self._send_command(':GREF#', fixed_len=1)
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
        """How the mount updates its refraction data: :WSG# (10Micron).

        Returns: 0 = not_updating, 1 = not_updating_tracking, 2 = continuously_updating.

        :GREF# only says whether refraction correction is ON (0/1); it used to
        be read here as the update mode, so an enabled correction reported
        "not updating while tracking". :WSG# is the update type, the one
        MountWizzard4 reads and sets with :WSS<n># (mountcontrol/setting.py).
        """
        result = self._send_command(':WSG#')
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
        result = self._send_command(':Gdat#', fixed_len=1)
        if result is None:
            return None
        return result.strip() == '1'

    def is_gps_synced(self) -> Optional[bool]:
        """GPS clock synchronisation (10Micron): :gtgpps# from firmware 3.2.5,
        :gtg# before (as MountWizzard4 reads it). ":gps#" is not a 10Micron
        command: the mount never answered and the check timed out."""
        cmd = ':gtgpps#' if self._firmware_at_least(3, 2, 5) else ':gtg#'
        result = self._send_command(cmd)
        if result is None:
            return None
        return result.strip() == '1'

    def _firmware_at_least(self, *version) -> bool:
        import re
        nums = re.findall(r'\d+', str(getattr(self, '_firmware', '') or ''))
        try:
            return tuple(int(n) for n in nums[:3]) >= tuple(version)
        except ValueError:
            return False

    PRLIST_MAX_CHUNKS = 200      # a full list is a few dozen chunks

    def read_mount_preferences(self) -> Optional[dict]:
        """The mount's preference list, as {name: [fields...]} (10Micron).

        Sequence confirmed by Nicolas de Hilster on a GM3000HPS (fw 3.2.5):
        ":PRclr#" restarts the list and answers one character ('1', no '#');
        then each ":PRlist#" returns the next chunk, ending in '#', made of
        "Name,type,W,value,...;" entries. A chunk whose last entry is "x"
        means more follows; "c" means the list is complete (after that,
        ":PRlist#" keeps answering "c#"). Example entries:
            Tracking correction (%),3,W,0.000,3,-9.999,9.999
            Tracking speed,2,W,0,5,Sidereal,Solar,Lunar,Custom,Stop
        Returns None when the mount is not a 10Micron or does not answer.
        """
        product = getattr(self, '_product_name', '') or ''
        if '10micron' not in product.lower():
            return None
        if self._send_command(':PRclr#', fixed_len=1) is None:
            return None
        prefs: dict[str, list[str]] = {}
        for _ in range(self.PRLIST_MAX_CHUNKS):
            chunk = self._send_command(':PRlist#')
            if chunk is None:
                return prefs or None
            done, empty = parse_prlist_chunk(chunk, prefs)
            if done or empty:
                break
        return prefs

    def check_mount_settings(self) -> Optional[dict]:
        """Tracking-related preferences, as MountMonitor 3 checks them:
        {"follow_object": bool, "tracking_correction": "0.000",
         "tracking_speed": "Sidereal", "custom_rate_ra": "00.000",
         "custom_rate_dec": "00.000"} -- keys missing when not reported.
        Follow object switches the speed to "Custom" and writes the
        object's rates there (lists sent by N. de Hilster, fw 3.2.5).
        None when the list cannot be read."""
        prefs = self.read_mount_preferences()
        if prefs is None:
            return None
        return summarise_preferences(prefs)

    def set_high_precision(self) -> bool:
        """Ultra-precision output (10Micron :U2#), sent WITHOUT reading a reply.

        The old :U# has no reply: waiting for one cost the 5 s timeout and
        then marked the fresh connection as lost. It also TOGGLES the
        precision, so a mount already in high precision went back to the
        short formats. :U2# sets it outright; a mount that does not know it
        ignores it, and parse_ra/parse_dec read the short formats anyway."""
        self._send_no_reply(':U2#')
        return True

    def _send_no_reply(self, command: str) -> None:
        if not self._socket or not self._connected:
            return
        with self._io_lock:
            try:
                self._socket.sendall(command.encode('ascii'))
            except OSError as e:
                logger.warning(f"Communication error: {e}")
                self._connected = False

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
        apply_getain(self._send_command(":getain#"), sample)

        return sample
