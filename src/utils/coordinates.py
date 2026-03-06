"""Coordinate parsing and formatting utilities for RA/DEC values.

Handles formats used by LX200 protocol and ASCOM:
  RA:  HH:MM:SS.dd  (hours, minutes, seconds)
  DEC: +DD:MM:SS.d  or sDD*MM:SS.d (degrees, arcminutes, arcseconds)
"""

import re
import math
from typing import Optional


def parse_ra(ra_str: str) -> Optional[float]:
    """Parse RA string (HH:MM:SS.dd) to decimal hours.

    Returns None if parsing fails.
    """
    ra_str = ra_str.strip().rstrip('#')
    m = re.match(r'^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$', ra_str)
    if m:
        h = int(m.group(1))
        minutes = int(m.group(2))
        sec = float(m.group(3))
        return h + minutes / 60.0 + sec / 3600.0
    return None


def parse_dec(dec_str: str) -> Optional[float]:
    """Parse DEC string (+DD:MM:SS.d or sDD*MM:SS.d) to decimal degrees.

    Returns None if parsing fails.
    """
    dec_str = dec_str.strip().rstrip('#')
    # Handle both : and * as degree separator
    m = re.match(r'^([+-]?)(\d{1,3})[:*](\d{2}):(\d{2}(?:\.\d+)?)$', dec_str)
    if m:
        sign = -1 if m.group(1) == '-' else 1
        deg = int(m.group(2))
        minutes = int(m.group(3))
        sec = float(m.group(4))
        return sign * (deg + minutes / 60.0 + sec / 3600.0)
    return None


def format_ra(ra_hours: float, precision: int = 2) -> str:
    """Format decimal hours to HH:MM:SS.dd string."""
    ra_hours = ra_hours % 24.0
    h = int(ra_hours)
    remainder = (ra_hours - h) * 60.0
    m = int(remainder)
    s = (remainder - m) * 60.0
    return f"{h:02d}:{m:02d}:{s:0{3 + precision}.{precision}f}"


def format_dec(dec_degrees: float, precision: int = 1) -> str:
    """Format decimal degrees to +DD:MM:SS.d string."""
    sign = '+' if dec_degrees >= 0 else '-'
    dec_abs = abs(dec_degrees)
    d = int(dec_abs)
    remainder = (dec_abs - d) * 60.0
    m = int(remainder)
    s = (remainder - m) * 60.0
    return f"{sign}{d:02d}:{m:02d}:{s:0{3 + precision}.{precision}f}"


def ra_to_arcsec(ra_hours: float) -> float:
    """Convert RA in decimal hours to arcseconds (RA * 15 * 3600)."""
    return ra_hours * 15.0 * 3600.0


def dec_to_arcsec(dec_degrees: float) -> float:
    """Convert DEC in decimal degrees to arcseconds."""
    return dec_degrees * 3600.0


def arcsec_to_ra(arcsec: float) -> float:
    """Convert arcseconds to RA decimal hours."""
    return arcsec / (15.0 * 3600.0)


def arcsec_to_dec(arcsec: float) -> float:
    """Convert arcseconds to DEC decimal degrees."""
    return arcsec / 3600.0


def ra_diff_arcsec(ra1: float, ra2: float, declination_deg: float = 0.0) -> float:
    """Difference in RA (hours) converted to true arcseconds on sky.

    Applies cos(dec) correction for true angular separation.
    Handles wrap-around at 24h.
    """
    diff = ra1 - ra2
    if diff > 12.0:
        diff -= 24.0
    elif diff < -12.0:
        diff += 24.0
    cos_dec = math.cos(math.radians(declination_deg))
    return diff * 15.0 * 3600.0 * cos_dec


def dec_diff_arcsec(dec1: float, dec2: float) -> float:
    """Difference in DEC (degrees) in arcseconds."""
    return (dec1 - dec2) * 3600.0


def ra_arcsec_to_time_seconds(arcsec: float, declination_deg: float = 0.0) -> float:
    """Convert RA arcseconds to seconds of time, accounting for declination.

    time_seconds = arcsec / (15 * cos(dec))
    """
    cos_dec = math.cos(math.radians(declination_deg))
    if cos_dec < 1e-10:
        return float('inf')
    return arcsec / (15.0 * cos_dec)


def spherical_displacement(displacement_arcsec: float, declination_deg: float) -> float:
    """Compute spherical displacement: displacement * cos(declination).

    This makes the displacement directly comparable to pixel angular resolution.
    """
    return displacement_arcsec * math.cos(math.radians(declination_deg))
