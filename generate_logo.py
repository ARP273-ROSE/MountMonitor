#!/usr/bin/env python3
"""Generate MountMonitor logo and icon.

Creates a professional astronomy-themed logo with a telescope mount
and crosshair/tracking motif on a dark cosmic background.

Output:
  logo.png     - 512x512 PNG
  logo_64.png  - 64x64 PNG
  logo.ico     - Multi-size ICO (16, 24, 32, 48, 64, 128, 256)
"""

from PIL import Image, ImageDraw, ImageFont
import math
import os

# Work at 2x resolution for anti-aliasing, then downscale
SIZE = 1024  # 2x of 512


def draw_logo(draw: ImageDraw.Draw, size: int):
    """Draw the MountMonitor logo."""
    cx, cy = size // 2, size // 2
    r = size // 2 - 20

    # === Background: dark navy/space gradient (radial approximation) ===
    for i in range(r, 0, -1):
        ratio = i / r
        # Deep navy center → slightly lighter edge
        cr = int(8 + 12 * (1 - ratio))
        cg = int(12 + 18 * (1 - ratio))
        cb = int(28 + 30 * (1 - ratio))
        draw.ellipse(
            [cx - i, cy - i, cx + i, cy + i],
            fill=(cr, cg, cb)
        )

    # === Stars in background ===
    import random
    random.seed(42)  # Reproducible
    for _ in range(80):
        x = random.randint(cx - r + 30, cx + r - 30)
        y = random.randint(cy - r + 30, cy + r - 30)
        # Check if inside circle
        dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if dist < r - 20:
            brightness = random.randint(100, 255)
            star_size = random.choice([1, 1, 1, 2, 2, 3])
            draw.ellipse(
                [x - star_size, y - star_size, x + star_size, y + star_size],
                fill=(brightness, brightness, brightness)
            )

    # === Circular border ring (double) ===
    ring_color = (60, 130, 200)  # Blue steel
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=ring_color, width=6
    )
    draw.ellipse(
        [cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14],
        outline=(40, 90, 150), width=2
    )

    # === Telescope mount (German equatorial silhouette) ===
    # Tripod base
    tripod_color = (50, 60, 80)
    tripod_w = 8
    base_y = cy + int(r * 0.55)
    mount_top_y = cy - int(r * 0.15)

    # Tripod legs (3 legs spreading from center)
    leg_spread = int(r * 0.35)
    # Center leg (down)
    draw.line(
        [(cx, mount_top_y + int(r * 0.35)), (cx, base_y)],
        fill=tripod_color, width=tripod_w
    )
    # Left leg
    draw.line(
        [(cx, mount_top_y + int(r * 0.35)), (cx - leg_spread, base_y)],
        fill=tripod_color, width=tripod_w
    )
    # Right leg
    draw.line(
        [(cx, mount_top_y + int(r * 0.35)), (cx + leg_spread, base_y)],
        fill=tripod_color, width=tripod_w
    )

    # Mount head (RA axis housing)
    head_color = (70, 80, 100)
    head_x = cx
    head_y = mount_top_y + int(r * 0.2)
    head_w = int(r * 0.12)
    head_h = int(r * 0.25)
    draw.rounded_rectangle(
        [head_x - head_w, head_y - head_h, head_x + head_w, head_y + head_h],
        radius=10, fill=head_color, outline=(90, 100, 120), width=2
    )

    # Counterweight shaft
    cw_angle = -35  # degrees from vertical
    cw_len = int(r * 0.35)
    cw_end_x = head_x + int(cw_len * math.sin(math.radians(cw_angle)))
    cw_end_y = head_y + int(cw_len * math.cos(math.radians(cw_angle)))
    draw.line(
        [(head_x, head_y), (cw_end_x, cw_end_y)],
        fill=(60, 70, 90), width=6
    )
    # Counterweight
    cw_r = int(r * 0.06)
    draw.ellipse(
        [cw_end_x - cw_r, cw_end_y - cw_r, cw_end_x + cw_r, cw_end_y + cw_r],
        fill=(80, 90, 110), outline=(100, 110, 130), width=2
    )

    # Telescope tube (OTA)
    ota_angle = 35  # degrees from vertical (opposite to CW)
    ota_len = int(r * 0.4)
    ota_end_x = head_x + int(ota_len * math.sin(math.radians(ota_angle)))
    ota_end_y = head_y - int(ota_len * math.cos(math.radians(ota_angle)))
    # OTA tube
    tube_w = int(r * 0.05)
    dx = ota_end_x - head_x
    dy = ota_end_y - head_y
    length = math.sqrt(dx ** 2 + dy ** 2)
    if length > 0:
        nx = -dy / length * tube_w
        ny = dx / length * tube_w
        tube_points = [
            (head_x + nx, head_y + ny),
            (ota_end_x + nx, ota_end_y + ny),
            (ota_end_x - nx, ota_end_y - ny),
            (head_x - nx, head_y - ny),
        ]
        draw.polygon(tube_points, fill=(90, 100, 120), outline=(110, 120, 140))

    # Dew shield (front of OTA)
    dew_r = int(r * 0.07)
    draw.ellipse(
        [ota_end_x - dew_r, ota_end_y - dew_r,
         ota_end_x + dew_r, ota_end_y + dew_r],
        fill=(70, 80, 100), outline=(120, 130, 150), width=2
    )

    # === Crosshair / tracking reticle (central focus) ===
    reticle_cx = cx + int(r * 0.15)
    reticle_cy = cy - int(r * 0.35)
    reticle_r = int(r * 0.2)
    reticle_color = (0, 200, 100)  # Green (tracking indicator)

    # Crosshair circle
    draw.ellipse(
        [reticle_cx - reticle_r, reticle_cy - reticle_r,
         reticle_cx + reticle_r, reticle_cy + reticle_r],
        outline=reticle_color, width=3
    )
    # Inner circle
    inner_r = int(reticle_r * 0.5)
    draw.ellipse(
        [reticle_cx - inner_r, reticle_cy - inner_r,
         reticle_cx + inner_r, reticle_cy + inner_r],
        outline=reticle_color, width=2
    )

    # Crosshair lines (with gap at center)
    gap = int(reticle_r * 0.15)
    line_ext = int(reticle_r * 1.3)
    # Horizontal
    draw.line(
        [(reticle_cx - line_ext, reticle_cy), (reticle_cx - gap, reticle_cy)],
        fill=reticle_color, width=2
    )
    draw.line(
        [(reticle_cx + gap, reticle_cy), (reticle_cx + line_ext, reticle_cy)],
        fill=reticle_color, width=2
    )
    # Vertical
    draw.line(
        [(reticle_cx, reticle_cy - line_ext), (reticle_cx, reticle_cy - gap)],
        fill=reticle_color, width=2
    )
    draw.line(
        [(reticle_cx, reticle_cy + gap), (reticle_cx, reticle_cy + line_ext)],
        fill=reticle_color, width=2
    )

    # Star at crosshair center (bright point)
    star_r = 4
    draw.ellipse(
        [reticle_cx - star_r, reticle_cy - star_r,
         reticle_cx + star_r, reticle_cy + star_r],
        fill=(255, 255, 220)
    )
    # Glow around star
    for gr in range(star_r + 6, star_r, -1):
        alpha_ratio = 1.0 - (gr - star_r) / 6.0
        gc = int(255 * alpha_ratio * 0.3)
        draw.ellipse(
            [reticle_cx - gr, reticle_cy - gr,
             reticle_cx + gr, reticle_cy + gr],
            outline=(gc, gc, int(gc * 0.8))
        )

    # === RA/DEC axis indicators (small arrows/lines at mount) ===
    # Small "RA" and "DEC" labels near the mount head
    # (These are too small at icon size, only visible on 512px)

    # === Title text: "MM" monogram (bottom) ===
    # Golden accent color
    gold = (220, 180, 80)

    # Draw "MM" text at bottom
    text_y = cy + int(r * 0.7)
    # Simple geometric "MM" using lines
    mm_w = int(r * 0.35)
    mm_h = int(r * 0.12)
    mm_lx = cx - mm_w
    mm_rx = cx + mm_w
    mm_thickness = 5

    # M left
    draw.line([(mm_lx, text_y + mm_h), (mm_lx, text_y - mm_h)], fill=gold, width=mm_thickness)
    draw.line([(mm_lx, text_y - mm_h), (cx - int(mm_w * 0.5), text_y)], fill=gold, width=mm_thickness)
    draw.line([(cx - int(mm_w * 0.5), text_y), (cx - int(mm_w * 0.05), text_y - mm_h)], fill=gold, width=mm_thickness)
    draw.line([(cx - int(mm_w * 0.05), text_y - mm_h), (cx - int(mm_w * 0.05), text_y + mm_h)], fill=gold, width=mm_thickness)

    # M right
    draw.line([(cx + int(mm_w * 0.05), text_y + mm_h), (cx + int(mm_w * 0.05), text_y - mm_h)], fill=gold, width=mm_thickness)
    draw.line([(cx + int(mm_w * 0.05), text_y - mm_h), (cx + int(mm_w * 0.5), text_y)], fill=gold, width=mm_thickness)
    draw.line([(cx + int(mm_w * 0.5), text_y), (mm_rx, text_y - mm_h)], fill=gold, width=mm_thickness)
    draw.line([(mm_rx, text_y - mm_h), (mm_rx, text_y + mm_h)], fill=gold, width=mm_thickness)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Create at 2x resolution
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_logo(draw, SIZE)

    # Downscale with LANCZOS anti-aliasing
    logo_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
    logo_64 = img.resize((64, 64), Image.Resampling.LANCZOS)

    # Save PNG
    logo_path = os.path.join(script_dir, 'logo.png')
    logo_512.save(logo_path, 'PNG')
    print(f"Created: {logo_path}")

    logo64_path = os.path.join(script_dir, 'logo_64.png')
    logo_64.save(logo64_path, 'PNG')
    print(f"Created: {logo64_path}")

    # Create ICO with multiple sizes
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = []
    for s in ico_sizes:
        resized = img.resize((s, s), Image.Resampling.LANCZOS)
        ico_images.append(resized)

    ico_path = os.path.join(script_dir, 'logo.ico')
    ico_images[0].save(
        ico_path, format='ICO',
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:]
    )
    print(f"Created: {ico_path}")

    print("Logo generation complete!")


if __name__ == '__main__':
    main()
