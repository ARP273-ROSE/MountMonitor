# -*- coding: utf-8 -*-
"""Le RMS ne doit decrire que le suivi — ni les slews, ni la derive.

Ces tests rejouent une session synthetique dont on connait la verite terrain :
deux cibles separees de 14,7 deg, un jitter de 0,26" RMS et une derive de
-5,65"/h. Avant correction, le rapport annoncait 16 446" de RMS combine et la
note MAUVAIS ; la cause etait double.

1. La segmentation cherchait un SAUT entre deux echantillons consecutifs. Un
   slew est un mouvement continu : consecutivement, deux echantillons different
   d'une fraction de degre et aucun saut n'est jamais vu. Les deux cibles
   tombaient donc dans un seul segment, dont la mediane se placait entre elles.
2. Le RMS melangeait la derive lente et le jitter. Une rampe d'amplitude A a
   un ecart-type de A/sqrt(12) : sur 7 h a -5,65"/h, cela fait 12" a soi seul,
   alors que la meme derive ne deplace une etoile que de 0,28" pendant une pose
   de 180 s, et que chaque dither l'annule.
"""
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.logging_module.log_parser import parse_dat_file  # noqa: E402

JITTER = 0.26      # arcsec RMS, verite terrain
DERIVE = -5.65     # arcsec/h en RA
HZ = 1.68
M31 = (0 + 44 / 60 + 28.8 / 3600, 41 + 26 / 60 + 27.1 / 3600)
M33 = (1 + 35 / 60 + 23.0 / 3600, 30 + 47 / 60 + 56.0 / 3600)


def _hms(h):
    h %= 24
    H = int(h); m = (h - H) * 60; M = int(m)
    return "%02d:%02d:%05.2f" % (H, M, (m - M) * 60)


def _dms(d):
    sg = '+' if d >= 0 else '-'
    d = abs(d); D = int(d); m = (d - D) * 60; M = int(m)
    return "%s%02d:%02d:%05.2f" % (sg, D, M, (m - M) * 60)


def _clock(t):
    t = int(t) % 86400
    return "%02d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60)


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """Une nuit : M 31 pendant 48 min, un slew de 30 s, M 33 pendant 7 h 20."""
    random.seed(42)
    dt = 1.0 / HZ
    lignes = []

    def ecrire(t, ra, dec):
        r, d = _hms(ra), _dms(dec)
        cols = [_clock(t), _clock(t), r, r, "0.150", d, d, "0.200"] + [''] * 6 + \
               [r, r, "0.150", d, d, "0.200", '', '', "0.000", '', '', "0.000", "TRACKING"]
        lignes.append("\t".join(cols))

    t = 0.0
    n1 = 4898
    for _ in range(n1):
        dec = M31[1] + random.gauss(0, JITTER) / 3600
        ra = M31[0] + (DERIVE * t / 3600 + random.gauss(0, JITTER)) / 3600 / 15 / math.cos(math.radians(M31[1]))
        ecrire(t, ra, dec); t += dt

    nslew = int(30 * HZ)
    for i in range(nslew):
        f = (i + 1) / nslew
        ecrire(t, M31[0] + (M33[0] - M31[0]) * f, M31[1] + (M33[1] - M31[1]) * f)
        t += dt

    t2 = t
    n2 = int(7 * 3600 * HZ + 20 * 60 * HZ)
    for _ in range(n2):
        dec = M33[1] + random.gauss(0, JITTER) / 3600
        ra = M33[0] + (DERIVE * (t - t2) / 3600 + random.gauss(0, JITTER)) / 3600 / 15 / math.cos(math.radians(M33[1]))
        ecrire(t, ra, dec); t += dt

    entete = [
        "MountMonitor mount data file (v.1.9.0)", "Location:\tTest", "Mount:\tGM1000",
        "Mount ID:\t", "Firmware:\t3.20",
        "Telescopes are Unknown of the mount, pointing at azimuth 0.0, altitude 0.0",
        "\t".join(["RAW Mount time", "Mount time", "RAW RA", "RA", "RA StDev",
                   "RAW DEC", "DEC", "DEC StDev"] + ['x'] * 19 + ["Status"]),
    ]
    p = tmp_path_factory.mktemp("mm") / "MountMonitor_20260921-220015.dat"
    p.write_text("\n".join(entete + lignes) + "\n")
    return parse_dat_file(p)


def test_les_deux_cibles_sont_separees(session):
    """Un slew continu doit couper la session, meme sans saut entre echantillons."""
    assert len(session.target_segments) == 2


def test_les_echantillons_de_slew_sont_ecartes(session):
    """Ils sont du deplacement, pas du suivi : hors des segments."""
    hors = session.tracking_sample_count - session.samples_in_segments
    assert 20 <= hors <= 60, f"{hors} echantillons ecartes, attendu ~50"


def test_le_jitter_retrouve_la_verite_terrain(session):
    """0,26\" injecte, 0,26\" restitue — a 20 % pres."""
    for seg in session.target_segments:
        assert np.std(seg.ra_detrended) == pytest.approx(JITTER, rel=0.2)
        assert np.std(seg.dec_detrended) == pytest.approx(JITTER, rel=0.2)


def test_la_derive_retrouve_la_verite_terrain(session):
    for seg in session.target_segments:
        assert seg.ra_drift_arcsec_per_hour == pytest.approx(DERIVE, abs=0.5)
        assert abs(seg.dec_drift_arcsec_per_hour) < 0.5


def test_le_rms_brut_est_domine_par_la_derive(session):
    """Le piege qu'il ne faut plus jamais reprendre pour une erreur de suivi.

    Une rampe d'amplitude A a un ecart-type de A/sqrt(12).
    """
    long = max(session.target_segments, key=lambda g: g.sample_count)
    duree_h = (long.timestamps[-1] - long.timestamps[0]) / 3600.0
    attendu = abs(DERIVE) * duree_h / math.sqrt(12)
    assert np.std(long.ra_deviations) == pytest.approx(attendu, rel=0.15)
    # et il vaut plusieurs dizaines de fois le jitter
    assert np.std(long.ra_deviations) > 20 * np.std(long.ra_detrended)


def test_le_rms_global_reste_sous_la_seconde_d_arc(session):
    """Le chiffre sur lequel la note est fondee."""
    combine = math.hypot(float(np.std(session.ra_detrended)),
                         float(np.std(session.dec_detrended)))
    assert combine < 1.0, f"RMS combine {combine:.3f}\", attendu < 1\""


def test_la_derive_masque_l_erreur_periodique():
    """Une derive n'est pas periodique, mais une fenetre finie en fait un pic.

    MountMonitor existe pour trouver l'erreur periodique de la vis sans fin.
    Tant que la FFT travaillait sur les deviations brutes, une derive de
    20"/h produisait un « pic dominant » a 198 minutes et 15,8" d'amplitude,
    qui n'existe pas, et reléguait la vraie PE en troisieme position.
    """
    rng = np.random.default_rng(7)
    n, fs = 20000, 1.68
    t = np.arange(n) / fs
    periode_min, amplitude = 8.0, 1.5
    signal = (20.0 * t / 3600                        # derive 20"/h
              + amplitude * np.sin(2 * np.pi * t / (periode_min * 60))
              + rng.normal(0, 0.26, n))

    def pic_dominant(x):
        x = x - np.mean(x)
        w = np.hanning(len(x))
        spectre = np.abs(np.fft.rfft(x * w))
        freqs = np.fft.rfftfreq(len(x), 1 / fs)
        spectre[0] = 0.0
        i = int(np.argmax(spectre))
        return 1 / freqs[i] / 60, 2 * spectre[i] / np.sum(w)

    # brut : le pic dominant n'a rien a voir avec la PE
    p_brut, _ = pic_dominant(signal)
    assert p_brut > 50, "le test lui-meme est faux si la derive ne domine pas"

    # detrende : la PE ressort en tete, a la bonne periode et la bonne amplitude
    a, b = np.polyfit(t, signal, 1)
    p_net, amp_net = pic_dominant(signal - (a * t + b))
    assert p_net == pytest.approx(periode_min, rel=0.05)
    assert amp_net == pytest.approx(amplitude, rel=0.1)
