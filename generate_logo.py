#!/usr/bin/env python3
"""MountMonitor logo: ONE SVG source (logo.svg), everything else is rendered from it.

    QT_QPA_PLATFORM=offscreen python generate_logo.py      (PyQt6 + Pillow)

The drawing is the historical one — a German equatorial mount under a green
tracking reticle, on a starry navy disc, with the golden "MM" monogram —
now written as vectors. Outputs: logo.svg (the source), logo_{16,32,64,128,
256,512}.png, logo.png (= 512: window icon, About box, manual), logo.ico
(Windows installer, multi-size) and logo.icns (macOS).
"""

import math
import random
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
SIZE = 1024


def _rgb(c):
    return "#%02x%02x%02x" % c


def construire_svg() -> str:
    cx = cy = SIZE // 2
    r = SIZE // 2 - 20
    e = []

    # background: radial navy gradient
    e.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#fond)"/>')
    # stars (same seed as the original raster drawing)
    random.seed(42)
    for _ in range(80):
        x = random.randint(cx - r + 30, cx + r - 30)
        y = random.randint(cy - r + 30, cy + r - 30)
        if math.hypot(x - cx, y - cy) < r - 20:
            b = random.randint(100, 255)
            s = random.choice([1, 1, 1, 2, 2, 3])
            e.append(f'<circle cx="{x}" cy="{y}" r="{s}" fill="{_rgb((b, b, b))}"/>')
    # double rim
    e.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 3}" fill="none" stroke="#3c82c8" stroke-width="6"/>')
    e.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 15}" fill="none" stroke="#285a96" stroke-width="2"/>')

    # tripod
    base_y = cy + int(r * 0.55)
    mount_top_y = cy - int(r * 0.15)
    pied = mount_top_y + int(r * 0.35)
    ecart = int(r * 0.35)
    for x2 in (cx, cx - ecart, cx + ecart):
        e.append(f'<line x1="{cx}" y1="{pied}" x2="{x2}" y2="{base_y}" stroke="#323c50" '
                 f'stroke-width="8" stroke-linecap="round"/>')
    # mount head
    hy = mount_top_y + int(r * 0.2)
    hw, hh = int(r * 0.12), int(r * 0.25)
    e.append(f'<rect x="{cx - hw}" y="{hy - hh}" width="{2 * hw}" height="{2 * hh}" rx="10" '
             f'fill="#465064" stroke="#5a6478" stroke-width="2"/>')
    # counterweight shaft and weight
    a = math.radians(-35)
    l = int(r * 0.35)
    wx, wy = cx + int(l * math.sin(a)), hy + int(l * math.cos(a))
    e.append(f'<line x1="{cx}" y1="{hy}" x2="{wx}" y2="{wy}" stroke="#3c465a" stroke-width="6"/>')
    e.append(f'<circle cx="{wx}" cy="{wy}" r="{int(r * 0.06)}" fill="#505a6e" stroke="#646e82" stroke-width="2"/>')
    # telescope tube
    a = math.radians(35)
    l = int(r * 0.4)
    ox, oy = cx + int(l * math.sin(a)), hy - int(l * math.cos(a))
    tw = int(r * 0.05)
    dx, dy = ox - cx, oy - hy
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * tw, dx / n * tw
    pts = [(cx + nx, hy + ny), (ox + nx, oy + ny), (ox - nx, oy - ny), (cx - nx, hy - ny)]
    e.append('<polygon points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
             + '" fill="#5a6478" stroke="#6e788c" stroke-width="1"/>')
    e.append(f'<circle cx="{ox}" cy="{oy}" r="{int(r * 0.07)}" fill="#465064" stroke="#78828c" stroke-width="2"/>')

    # tracking reticle
    rx, ry, rr = cx + int(r * 0.15), cy - int(r * 0.35), int(r * 0.2)
    vert = "#00c864"
    e.append(f'<circle cx="{rx}" cy="{ry}" r="{rr}" fill="none" stroke="{vert}" stroke-width="3"/>')
    e.append(f'<circle cx="{rx}" cy="{ry}" r="{int(rr * 0.5)}" fill="none" stroke="{vert}" stroke-width="2"/>')
    gap, ext = int(rr * 0.15), int(rr * 1.3)
    for (x1, y1, x2, y2) in ((rx - ext, ry, rx - gap, ry), (rx + gap, ry, rx + ext, ry),
                             (rx, ry - ext, rx, ry - gap), (rx, ry + gap, rx, ry + ext)):
        e.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{vert}" stroke-width="2"/>')
    e.append(f'<circle cx="{rx}" cy="{ry}" r="10" fill="url(#halo)"/>')
    e.append(f'<circle cx="{rx}" cy="{ry}" r="4" fill="#ffffdc"/>')

    # golden "MM" monogram
    ty = cy + int(r * 0.7)
    mw, mh = int(r * 0.35), int(r * 0.12)
    gauche = [(cx - mw, ty + mh), (cx - mw, ty - mh), (cx - int(mw * 0.5), ty),
              (cx - int(mw * 0.05), ty - mh), (cx - int(mw * 0.05), ty + mh)]
    droite = [(cx + int(mw * 0.05), ty + mh), (cx + int(mw * 0.05), ty - mh), (cx + int(mw * 0.5), ty),
              (cx + mw, ty - mh), (cx + mw, ty + mh)]
    for m in (gauche, droite):
        e.append('<polyline points="' + ' '.join(f'{x},{y}' for x, y in m)
                 + '" fill="none" stroke="#dcb450" stroke-width="5" stroke-linejoin="miter"/>')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="fond" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#14203a"/>
      <stop offset="100%" stop-color="#080c1c"/>
    </radialGradient>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffdc" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#ffffdc" stop-opacity="0"/>
    </radialGradient>
  </defs>
{chr(10).join("  " + x for x in e)}
</svg>
'''


def rendre(svg: Path, sortie: Path, taille: int) -> None:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    img = QImage(taille, taille, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    QSvgRenderer(str(svg)).render(p, QRectF(0, 0, taille, taille))
    p.end()
    img.save(str(sortie), "PNG")


def main():
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)  # noqa: F841 — required for rendering
    svg = ICI / "logo.svg"
    svg.write_text(construire_svg(), encoding="utf-8")
    for taille in (16, 32, 64, 128, 256, 512):
        rendre(svg, ICI / f"logo_{taille}.png", taille)
    (ICI / "logo.png").write_bytes((ICI / "logo_512.png").read_bytes())
    from PIL import Image
    grand = ICI / "_logo_1024.png"
    rendre(svg, grand, 1024)
    img = Image.open(grand).convert("RGBA")
    img.save(ICI / "logo.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                      (64, 64), (128, 128), (256, 256)])
    img.save(ICI / "logo.icns")
    grand.unlink()
    print("logo.svg -> logo_*.png, logo.png, logo.ico, logo.icns")


if __name__ == "__main__":
    main()
