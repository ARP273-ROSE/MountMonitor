#!/usr/bin/env python3
"""Échantillonnage des instruments de Kevin, et ce qu'il faut en lire.

Script de vérification livré avec le cours : aucun chiffre du document n'est
posé de tête. Relancez-le, les valeurs du cours doivent réapparaître.

    python3 echantillonnage.py
"""
import math

# 206 265 secondes d'arc dans un radian : c'est ce facteur qui convertit une
# taille de pixel (en millimètres) et une focale (en millimètres) en angle.
RADIAN_EN_SECONDES = 180.0 * 3600.0 / math.pi

INSTRUMENTS = [
    # (nom, focale mm, capteur, taille de pixel µm)
    ("RC10 CFF f/8",        2000.0, "ASI 6200 MM Pro", 3.76),
    ("FSQ-106 f/5",          530.0, "ASI 6200 MM Pro", 3.76),
    ("FC-76DCU f/7,5",       570.0, "ASI 2600 MC Air", 3.76),
]

# Site de Kevin : sud de la forêt de Compiègne.
SEEING_MIN, SEEING_MAX = 2.5, 3.5   # secondes d'arc


def echantillonnage(focale_mm, pixel_um):
    """Angle couvert par un pixel, en secondes d'arc."""
    return RADIAN_EN_SECONDES * (pixel_um * 1e-3) / focale_mm


def vitesse_siderale_arcsec_par_s():
    """Vitesse de rotation apparente du ciel, à l'équateur céleste.

    Un tour en un jour sidéral : 23 h 56 min 4,0905 s.
    """
    jour_sideral_s = 23 * 3600 + 56 * 60 + 4.0905
    return 360.0 * 3600.0 / jour_sideral_s


print(f"  Seconde d'arc par radian      : {RADIAN_EN_SECONDES:.0f}")
print(f"  Vitesse sidérale à l'équateur : {vitesse_siderale_arcsec_par_s():.3f} arcsec/s")
print()
entete_angle = '"/pixel'
entete_pixels = 'pixels pour 1"'
print(f"  {'Instrument':22s} {'focale':>8s} {'pixel':>7s} {entete_angle:>9s} "
      f"{entete_pixels:>15s}")
for nom, focale, capteur, pixel in INSTRUMENTS:
    e = echantillonnage(focale, pixel)
    print(f"  {nom:22s} {focale:7.0f}mm {pixel:6.2f}µm {e:9.2f} {1.0/e:15.1f}")

print()
print("  Ce qu'une déviation de tolérance représente à l'image :")
for nom, focale, capteur, pixel in INSTRUMENTS:
    e = echantillonnage(focale, pixel)
    for tol in (0.5, 1.0, 2.0):
        print(f'    {nom:22s} tolérance {tol:.1f}" = {tol/e:5.2f} pixel(s)')

print()
print(f'  Seeing du site : {SEEING_MIN}" à {SEEING_MAX}" (sud de Compiègne)')
for nom, focale, capteur, pixel in INSTRUMENTS:
    e = echantillonnage(focale, pixel)
    print(f"    {nom:22s} : la turbulence étale l'étoile sur "
          f"{SEEING_MIN/e:.1f} à {SEEING_MAX/e:.1f} pixels")

print()
print("  Règle de lecture : une erreur de suivi qui reste nettement sous la")
print("  tache de seeing ne se voit pas sur l'image. C'est ce qui fixe le")
print("  seuil au-delà duquel il vaut la peine de s'en occuper.")
