"""Generate Talkie app icon — walkie-talkie design using PIL.

Creates a multi-resolution ICO file (16x16, 32x32, 48x48, 64x64)
with simplified detail at smaller sizes.
"""

import os

from PIL import Image, ImageDraw

from talkie_modules.paths import ASSETS_DIR
from talkie_modules.logger import get_logger

logger = get_logger("icon")

# Talkie blue
_BLUE = "#3b82f6"
_DARK_BLUE = "#2563eb"
_LIGHT_BLUE = "#60a5fa"
_WHITE = "#ffffff"
_GRAY = "#94a3b8"

ICO_PATH = os.path.join(ASSETS_DIR, "talkie.ico")


def _draw_walkie_talkie(size: int) -> Image.Image:
    """
    Draw a walkie-talkie icon at the given size.

    At 16px, simplified (no grille detail).
    At 32px+, includes antenna, speaker grille lines, and PTT button.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scale factor
    s = size / 64.0

    # Body — rounded rectangle
    body_left = int(14 * s)
    body_top = int(16 * s)
    body_right = int(50 * s)
    body_bottom = int(60 * s)
    body_radius = int(4 * s)
    draw.rounded_rectangle(
        [body_left, body_top, body_right, body_bottom],
        radius=body_radius,
        fill=_BLUE,
        outline=_DARK_BLUE,
        width=max(1, int(1 * s)),
    )

    # Antenna — thin rectangle from top of body upward
    ant_width = max(2, int(4 * s))
    ant_left = int(22 * s)
    ant_top = int(4 * s)
    ant_bottom = body_top + int(2 * s)
    draw.rectangle(
        [ant_left, ant_top, ant_left + ant_width, ant_bottom],
        fill=_GRAY,
    )
    # Antenna tip — small circle
    tip_r = max(1, int(3 * s))
    tip_cx = ant_left + ant_width // 2
    tip_cy = ant_top
    draw.ellipse(
        [tip_cx - tip_r, tip_cy - tip_r, tip_cx + tip_r, tip_cy + tip_r],
        fill=_LIGHT_BLUE,
    )

    if size >= 32:
        # Speaker grille — horizontal lines in upper portion of body
        grille_top = int(22 * s)
        grille_bottom = int(38 * s)
        grille_left = int(20 * s)
        grille_right = int(44 * s)
        line_spacing = max(3, int(5 * s))
        line_width = max(1, int(1.5 * s))

        y = grille_top
        while y < grille_bottom:
            draw.line(
                [(grille_left, y), (grille_right, y)],
                fill=_DARK_BLUE,
                width=line_width,
            )
            y += line_spacing

        # PTT button on the side — small rounded rectangle
        btn_left = body_right - int(2 * s)
        btn_top = int(34 * s)
        btn_right = body_right + int(4 * s)
        btn_bottom = int(48 * s)
        btn_radius = max(1, int(2 * s))
        draw.rounded_rectangle(
            [btn_left, btn_top, btn_right, btn_bottom],
            radius=btn_radius,
            fill=_LIGHT_BLUE,
            outline=_DARK_BLUE,
            width=max(1, int(1 * s)),
        )

    return img


def generate_icon(output_path: str | None = None) -> str:
    """
    Generate a multi-resolution ICO file.

    Returns the path to the generated ICO.
    """
    output_path = output_path or ICO_PATH
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    sizes = [16, 32, 48, 64]
    images = [_draw_walkie_talkie(s) for s in sizes]

    # Save as ICO with all resolutions
    images[0].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    logger.info("Generated icon: %s (%s)", output_path, ", ".join(f"{s}x{s}" for s in sizes))
    return output_path


def get_tray_image(size: int = 64) -> Image.Image:
    """Get a PIL Image suitable for the system tray icon."""
    return _draw_walkie_talkie(size)


if __name__ == "__main__":
    path = generate_icon()
    print(f"Icon generated: {path}")
