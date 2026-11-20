"""LX200 Serial port connection implementation.

Reuses all LX200 commands from lx200_protocol.py but communicates
over a serial (COM) port instead of TCP/IP.
"""

import logging
import threading
from typing import Optional

import serial

from .lx200_protocol import LX200Connection
from ..models.mount_data import ConnectionProtocol

logger = logging.getLogger(__name__)


class LX200SerialConnection(LX200Connection):
    """LX200 protocol connection via serial port.

    Inherits all LX200 command methods; only the transport layer
    (connect, disconnect, _send_command) is replaced with serial I/O.
    """

    def __init__(self, port: str = "COM1", baudrate: int = 9600, timeout: float = 5.0):
        # Skip LX200Connection.__init__ TCP fields, call MountConnection.__init__
        super(LX200Connection, self).__init__()
        self._serial_port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._protocol = ConnectionProtocol.LX200
        self._reconnect_attempts = 0
        # LX200Connection.__init__ is skipped (super(LX200Connection, ...)):
        # the I/O lock shared by poller and GUI must be recreated here.
        self._io_lock = threading.Lock()

    @property
    def host(self) -> str:
        return self._serial_port

    @property
    def port(self) -> int:
        return self._baudrate

    def connect(self) -> bool:
        """Connect to mount via serial port."""
        try:
            self.disconnect()
            self._serial = serial.Serial(
                port=self._serial_port,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                timeout=self._timeout,
            )
            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to mount on {self._serial_port} @ {self._baudrate}")

            self.set_high_precision()
            return True

        except (serial.SerialException, OSError) as e:
            logger.error(f"Serial connection failed on {self._serial_port}: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        if self._serial is not None:
            try:
                self._serial.close()
            except OSError:
                pass
            self._serial = None
        self._connected = False

    def abort(self) -> None:
        s = self._serial
        if s is not None:
            try:
                s.cancel_read()
            except Exception:
                pass

    def reconnect(self) -> bool:
        """One reconnection attempt after a connection loss.

        No ceiling: the attempts used to stop for good after five, about
        thirty seconds, so a mount that rebooted (one to two minutes) was
        never found again and the rest of the night was lost. The poller now
        spaces the attempts out (2, 4, 8... up to 60 s)."""
        self._reconnect_attempts += 1
        logger.info(f"Serial reconnection attempt {self._reconnect_attempts}")
        return self.connect()

    # Maximum response size to prevent unbounded buffer growth (security)
    _MAX_RESPONSE_BYTES = 4096

    def _send_command(self, command: str) -> Optional[str]:
        """Send a command via serial and receive the response.

        Commands start with : and responses end with #.
        Security: response buffer is bounded to _MAX_RESPONSE_BYTES.
        """
        if not self._serial or not self._connected:
            return None

        with self._io_lock:
            return self._send_command_locked(command)

    def _send_no_reply(self, command: str) -> None:
        if not self._serial or not self._connected:
            return
        with self._io_lock:
            try:
                self._serial.write(command.encode('ascii'))
            except (serial.SerialException, OSError) as e:
                logger.warning(f"Serial communication error: {e}")
                self._connected = False

    def _send_command_locked(self, command: str) -> Optional[str]:
        try:
            self._serial.reset_input_buffer()
            self._serial.write(command.encode('ascii'))

            # Read until # terminator (with size limit)
            response = b''
            while True:
                byte = self._serial.read(1)
                if not byte:
                    # Timeout
                    if response:
                        break
                    logger.warning("Serial read timeout")
                    return None
                response += byte
                if byte == b'#':
                    break
                if len(response) > self._MAX_RESPONSE_BYTES:
                    logger.warning(f"Serial response exceeded {self._MAX_RESPONSE_BYTES} bytes")
                    return None

            decoded = response.decode('ascii', 'replace').rstrip('#')
            return decoded

        except (serial.SerialException, OSError) as e:
            logger.warning(f"Serial communication error: {e}")
            self._connected = False
            return None
