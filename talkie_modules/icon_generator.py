"""Talkie app icon — loads from source PNG asset.

Creates a multi-resolution ICO file (16x16 through 256x256)
from assets/talkie_icon.png.
"""

import os

from PIL import Image

from talkie_modules.paths import ASSETS_DIR
from talkie_modules.logger import get_logger

logger = get_logger("icon")

ICO_PATH = os.path.join(ASSETS_DIR, "talkie.ico")
PNG_PATH = os.path.join(ASSETS_DIR, "talkie_icon.png")


def _load_source() -> Image.Image:
    """Load the source icon PNG."""
    return Image.open(PNG_PATH).convert("RGBA")


def generate_icon(output_path: str | None = None) -> str:
    """
    Generate a multi-resolution ICO file from the source PNG.

    Returns the path to the generated ICO.
    """
    output_path = output_path or ICO_PATH
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    src = _load_source()
    sizes = [16, 32, 48, 64, 128, 256]
    images = [src.resize((s, s), Image.LANCZOS) for s in sizes]

    images[-1].save(
        output_path,
        format="ICO",
        append_images=images[:-1],
    )
    logger.info("Generated icon: %s (%s)", output_path, ", ".join(f"{s}x{s}" for s in sizes))
    return output_path


def get_tray_image(size: int = 64) -> Image.Image:
    """Get a PIL Image suitable for the system tray icon."""
    return _load_source().resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    path = generate_icon()
    print(f"Icon generated: {path}")
