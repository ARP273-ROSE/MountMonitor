"""Simulated telescope mount for testing without hardware.

Generates realistic-looking RA/DEC data with configurable noise,
drift, and periodic errors to simulate real mount behavior.
"""

import time
import math
import random
from datetime import datetime
from typing import Optional

from ..core.mount_connection import MountConnection
from ..models.mount_data import MountStatus, PierSide, ConnectionProtocol
from ..utils.coordinates import format_ra, format_dec


class SimulatedMount(MountConnection):
    """Simulated mount connection for testing and demo purposes.

    Generates realistic tracking data with:
    - Periodic error (worm gear simulation)
    - Random noise (seeing/vibration)
    - Occasional drift (polar alignment error)
    - Time variations
    """

    def __init__(self):
        super().__init__()
        self._protocol = ConnectionProtocol.SIMULATION
        self._start_time = time.time()

        # Target coordinates (Cassiopeia region)
        self._target_ra = 2.7357  # ~02:44:08 hours
        self._target_dec = 61.1711  # ~61:10:16 degrees

        # Simulated parameters
        self._pe_amplitude = 3.0  # Periodic error amplitude in arcseconds
        self._pe_period = 480.0   # PE period in seconds (worm gear)
        self._noise_sigma = 0.3   # Random noise sigma in arcseconds
        self._drift_rate = 0.01   # Drift rate in arcsec/s (polar alignment error)

        # State
        self._status = MountStatus.TRACKING
        self._pier_side = PierSide.WEST

        # Axial simulation
        self._ra_axis_base = 45.0  # Starting axis position in degrees

    def connect(self) -> bool:
        self._connected = True
        self._start_time = time.time()
        return True

    def disconnect(self):
        self._connected = False

    def get_ra(self) -> Optional[str]:
        if not self._connected:
            return None
        elapsed = time.time() - self._start_time

        # Simulated RA with periodic error, noise, and drift
        pe = self._pe_amplitude * math.sin(2 * math.pi * elapsed / self._pe_period)
        noise = random.gauss(0, self._noise_sigma)
        drift = self._drift_rate * elapsed * 0.001  # Slow drift

        # Convert deviation arcsec to RA hours offset
        # 1 arcsec RA = 1/15 time-second = 1/(15*3600) hours
        offset_hours = (pe + noise + drift) / (15.0 * 3600.0)
        ra = self._target_ra + offset_hours

        return format_ra(ra, precision=2)

    def get_dec(self) -> Optional[str]:
        if not self._connected:
            return None
        elapsed = time.time() - self._start_time

        # DEC: mainly noise, small periodic error
        pe = self._pe_amplitude * 0.3 * math.sin(2 * math.pi * elapsed / self._pe_period + 1.2)
        noise = random.gauss(0, self._noise_sigma * 0.8)

        offset_deg = (pe + noise) / 3600.0
        dec = self._target_dec + offset_deg

        return format_dec(dec, precision=1)

    def get_status(self) -> MountStatus:
        return self._status

    def get_mount_time(self) -> Optional[str]:
        now = datetime.now()
        return now.strftime("%H:%M:%S")

    def get_firmware_version(self) -> str:
        return "SIM-1.0"

    def get_product_name(self) -> str:
        return "MountMonitor Simulated Mount"

    def get_mount_id(self) -> str:
        return "SIM-00000000000000000001"

    def get_pier_side(self) -> PierSide:
        return self._pier_side

    def get_azimuth(self) -> Optional[float]:
        return 341.34

    def get_altitude(self) -> Optional[float]:
        return 24.47

    def get_ra_axis_position(self) -> Optional[float]:
        if not self._connected:
            return None
        elapsed = time.time() - self._start_time
        # RA axis moves at ~15.04 arcsec/s (sidereal + small corrections)
        position = self._ra_axis_base + (15.04 * elapsed) / 3600.0
        noise = random.gauss(0, 0.001)
        return position + noise

    def get_dec_axis_position(self) -> Optional[float]:
        if not self._connected:
            return None
        # DEC axis mostly stationary with tiny noise
        noise = random.gauss(0, 0.0005)
        return 30.0 + noise

    def get_target_ra(self) -> Optional[str]:
        return format_ra(self._target_ra)

    def get_target_dec(self) -> Optional[str]:
        return format_dec(self._target_dec)

    def is_refraction_enabled(self) -> Optional[bool]:
        return True

    def get_refraction_mode(self) -> Optional[str]:
        return "continuously_updating"

    def is_dual_tracking_enabled(self) -> Optional[bool]:
        return True

    def is_gps_synced(self) -> Optional[bool]:
        return True

    def get_tracking_rate(self) -> Optional[str]:
        return "Sidereal"

    def get_latitude(self) -> Optional[str]:
        return "+49:18:22.6"

    def get_longitude(self) -> Optional[str]:
        return "+02:45:19.5"

    def get_elevation(self) -> Optional[float]:
        return 57.0

    def set_status(self, status: MountStatus):
        """For testing: change the simulated mount status."""
        self._status = status

    def set_pe_amplitude(self, arcsec: float):
        """For testing: change periodic error amplitude."""
        self._pe_amplitude = arcsec

    def set_noise(self, sigma: float):
        """For testing: change noise level."""
        self._noise_sigma = sigma
