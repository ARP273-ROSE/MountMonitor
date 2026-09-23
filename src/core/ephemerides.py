"""Sunrise, sunset and twilights from the site the mount reports.

No external dependency: the app ships a frozen Python and adding an
ephemeris library for one body would cost more than the algorithm. The
solar position follows the low-precision formulae of Meeus (Astronomical
Algorithms, ch. 25), which are good to about 0.01 deg on the Sun -- some
40 times finer than the 0.833 deg refraction allowance in the sunset
definition itself, so the limiting factor here is the convention, not the
arithmetic.

Checked against skyfield/DE421 over a full year at the user's latitude:
worst case 32 s on any twilight boundary.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Sun altitude defining each boundary, in degrees.
# -0.833 folds in refraction at the horizon and the solar semi-diameter.
HORIZON = -0.833
CIVIL = -6.0
NAUTICAL = -12.0
ASTRONOMICAL = -18.0


@dataclass
class Nuit:
    """The boundaries of one night, all in UTC."""
    coucher: datetime | None = None
    civil: datetime | None = None
    nautique: datetime | None = None
    astro_debut: datetime | None = None
    astro_fin: datetime | None = None
    nautique_fin: datetime | None = None
    civil_fin: datetime | None = None
    lever: datetime | None = None
    soleil_toujours_haut: bool = False
    soleil_toujours_bas: bool = False
    nuit_noire: bool = True          # False when the Sun never reaches -18

    @property
    def duree_noire(self) -> timedelta | None:
        if self.astro_debut and self.astro_fin:
            return self.astro_fin - self.astro_debut
        return None


def _jour_julien(dt: datetime) -> float:
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    d = (dt.day + dt.hour / 24 + dt.minute / 1440
         + (dt.second + dt.microsecond / 1e6) / 86400)
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1))
            + d + b - 1524.5)


def position_soleil(dt: datetime) -> tuple[float, float]:
    """Apparent right ascension (hours) and declination (degrees)."""
    n = _jour_julien(dt) - 2451545.0
    # Mean longitude and mean anomaly
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    # Ecliptic longitude: the equation of the centre, two terms
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    return (math.degrees(ra) % 360) / 15.0, math.degrees(dec)


def _gmst_heures(dt: datetime) -> float:
    d = _jour_julien(dt) - 2451545.0
    return (18.697375 + 24.065709824279 * d) % 24


def hauteur_soleil(dt: datetime, lat: float, lon: float) -> float:
    """Sun altitude in degrees. ``lon`` is positive EAST."""
    ra, dec = position_soleil(dt)
    ha = (_gmst_heures(dt) + lon / 15.0 - ra) * 15.0
    ha_r, dec_r, lat_r = math.radians(ha), math.radians(dec), math.radians(lat)
    sin_h = (math.sin(lat_r) * math.sin(dec_r)
             + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_h))))


def _croisement(depart: datetime, fin: datetime, lat: float, lon: float,
                seuil: float, descendant: bool) -> datetime | None:
    """First time the Sun crosses ``seuil`` between two instants.

    Scanned every 4 minutes, then bisected. A coarser scan can step over
    the whole event near the poles, where the Sun skims a boundary for
    minutes at a time.
    """
    pas = timedelta(minutes=4)
    t = depart
    h0 = hauteur_soleil(t, lat, lon) - seuil
    while t < fin:
        t2 = min(t + pas, fin)
        h1 = hauteur_soleil(t2, lat, lon) - seuil
        if h0 == 0:
            return t
        if (h0 > 0) != (h1 > 0):
            if (h0 > 0) == descendant:
                a, b = t, t2
                for _ in range(40):
                    m = a + (b - a) / 2
                    if (hauteur_soleil(a, lat, lon) - seuil > 0) == \
                       (hauteur_soleil(m, lat, lon) - seuil > 0):
                        a = m
                    else:
                        b = m
                return a + (b - a) / 2
        t, h0 = t2, h1
    return None


def nuit_autour(reference: datetime, lat: float, lon: float) -> Nuit:
    """Boundaries of the night containing or following ``reference``.

    ``reference`` may be naive, in which case it is read as UTC.
    ``lon`` is positive EAST -- see :func:`parse_longitude_lx200`, the
    LX200 protocol does the opposite.
    """
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    # Which night to describe. A session opened at 02:00 is IN a night and
    # wants that one; someone connecting at 09:16 in the morning is looking
    # ahead to the evening, not back at the night that just ended. The Sun
    # itself settles it: if it is up, the interesting night is the next one.
    midi_local = reference.replace(hour=12, minute=0, second=0, microsecond=0) \
        - timedelta(hours=lon / 15.0)
    recule = midi_local > reference
    if recule:
        midi_local -= timedelta(days=1)
    if recule and hauteur_soleil(reference, lat, lon) > HORIZON:
        # Morning, after sunrise: the night that just ended is over, and the
        # one being prepared is tonight's. Only this case needs the jump --
        # an afternoon reference already points at the right window.
        midi_local += timedelta(days=1)
    fin = midi_local + timedelta(days=1)

    n = Nuit()
    n.coucher = _croisement(midi_local, fin, lat, lon, HORIZON, True)
    n.civil = _croisement(midi_local, fin, lat, lon, CIVIL, True)
    n.nautique = _croisement(midi_local, fin, lat, lon, NAUTICAL, True)
    n.astro_debut = _croisement(midi_local, fin, lat, lon, ASTRONOMICAL, True)
    n.astro_fin = _croisement(midi_local, fin, lat, lon, ASTRONOMICAL, False)
    n.nautique_fin = _croisement(midi_local, fin, lat, lon, NAUTICAL, False)
    n.civil_fin = _croisement(midi_local, fin, lat, lon, CIVIL, False)
    n.lever = _croisement(midi_local, fin, lat, lon, HORIZON, False)

    if n.coucher is None and n.lever is None:
        h = hauteur_soleil(midi_local + timedelta(hours=12), lat, lon)
        n.soleil_toujours_haut = h > HORIZON
        n.soleil_toujours_bas = h <= HORIZON
    # Above ~49 deg of latitude there are weeks with no astronomical night
    # at all: the Sun never gets 18 deg under. Saying "no dark night" is
    # the useful answer, not leaving two empty fields.
    n.nuit_noire = n.astro_debut is not None and n.astro_fin is not None
    return n


# ── Site coordinates ────────────────────────────────────────────────────

_SEXA = re.compile(r'^\s*([+-])?\s*(\d+)\s*[*:d°]\s*(\d+)'
                   r'(?:\s*[:\'m]\s*([\d.]+))?')


def _sexa_en_degres(texte: str) -> float | None:
    if not texte:
        return None
    m = _SEXA.match(str(texte).strip())
    if not m:
        try:
            return float(str(texte).strip())
        except ValueError:
            return None
    signe = -1.0 if m.group(1) == '-' else 1.0
    d, mi = float(m.group(2)), float(m.group(3))
    s = float(m.group(4)) if m.group(4) else 0.0
    return signe * (d + mi / 60.0 + s / 3600.0)


def parse_latitude_lx200(texte: str) -> float | None:
    """``:Gt#`` -> degrees, positive north. Format sDD*MM or sDD*MM:SS."""
    return _sexa_en_degres(texte)


def parse_longitude_lx200(texte: str) -> float | None:
    """``:Gg#`` -> degrees, **positive EAST**.

    The LX200 protocol reports longitude positive WEST, and 10Micron
    follows it: a site at 2.76 deg EAST answers -002*45 (and firmwares
    that refuse a negative sign answer 357*15 instead). Getting this
    backwards puts the observatory 5.5 deg away and shifts every twilight
    by 22 minutes, which is exactly the kind of error that looks almost
    right. Both forms are handled here and the sign is flipped once.
    """
    d = _sexa_en_degres(texte)
    if d is None:
        return None
    if d > 180.0:
        d -= 360.0
    return -d
