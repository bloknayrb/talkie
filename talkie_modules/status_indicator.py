"""Near-cursor floating status indicator for Talkie pipeline state.

Renders anti-aliased shapes via PIL at 2x resolution, downsampled with LANCZOS.
Displays via ImageTk.PhotoImage on a click-through Tkinter Toplevel.
"""

import ctypes
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from talkie_modules.logger import get_logger
from talkie_modules.state import AppState

logger = get_logger("indicator")


def _get_cursor_pos() -> tuple[int, int]:
    """Return (x, y) screen coordinates of the mouse cursor."""
    import ctypes.wintypes

    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors. t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# Colors
_RED = _hex_to_rgb("#ef4444")
_BLUE = _hex_to_rgb("#3b82f6")
_GREEN = _hex_to_rgb("#22c55e")


class StatusIndicator:
    """
    Small floating Toplevel near the cursor showing pipeline state.

    - Recording: red circle with subtle glow
    - Processing: blue pulsing circle (opacity-varying)
    - Success: green checkmark with fade-in/hold/fade-out
    - Idle/Error: hidden

    Must be created and driven from the Tk main thread.
    Use root.after(0, indicator.on_state_change, new_state) from other threads.
    """

    SIZE = 32
    _RENDER_SCALE = 2  # Render at 2x, downsample for anti-aliasing
    OFFSET_X = 16
    OFFSET_Y = 16

    # Animation timing (ms)
    _FRAME_MS = 33  # ~30 FPS
    _PULSE_PERIOD_MS = 1200  # Full pulse cycle
    _TRANSITION_MS = 200  # Color transition duration
    _CHECK_FADE_IN_MS = 200
    _CHECK_HOLD_MS = 800
    _CHECK_FADE_OUT_MS = 500

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._label: Optional[tk.Label] = None
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._anim_id: Optional[str] = None
        self._hide_id: Optional[str] = None

        self._anchor_x = 0
        self._anchor_y = 0

        # Animation state
        self._anim_mode: str = "none"  # "recording", "processing", "transition", "checkmark"
        self._anim_tick: int = 0
        self._transition_from: tuple[int, int, int] = _RED
        self._transition_to: tuple[int, int, int] = _BLUE

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _ensure_window(self) -> None:
        """Create the indicator Toplevel if it doesn't exist."""
        if self._win is not None and self._win.winfo_exists():
            return

        self._win = tk.Toplevel(self._root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", "black")
        self._win.configure(bg="black")
        self._win.attributes("-disabled", True)

        self._label = tk.Label(self._win, bg="black", borderwidth=0)
        self._label.pack()
        self._win.withdraw()

    def _position_near_cursor(self) -> None:
        """Move the window near the current cursor position."""
        try:
            x, y = _get_cursor_pos()
        except Exception:
            x, y = 100, 100
        self._anchor_x = x + self.OFFSET_X
        self._anchor_y = y + self.OFFSET_Y
        if self._win:
            self._win.geometry(f"{self.SIZE}x{self.SIZE}+{self._anchor_x}+{self._anchor_y}")

    def _show(self) -> None:
        if self._win:
            self._win.deiconify()
            self._win.lift()

    def _hide(self) -> None:
        self._cancel_anim()
        self._cancel_auto_hide()
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def _cancel_anim(self) -> None:
        if self._anim_id:
            self._root.after_cancel(self._anim_id)
            self._anim_id = None

    def _cancel_auto_hide(self) -> None:
        if self._hide_id:
            self._root.after_cancel(self._hide_id)
            self._hide_id = None

    # ------------------------------------------------------------------
    # PIL rendering
    # ------------------------------------------------------------------

    def _render_circle(self, color: tuple[int, int, int], alpha: float = 1.0,
                       glow: bool = False) -> Image.Image:
        """
        Render an anti-aliased circle at 2x resolution and downsample.

        Args:
            color: RGB tuple
            alpha: Overall opacity 0.0-1.0
            glow: Whether to add a soft glow behind the circle
        """
        s = self.SIZE * self._RENDER_SCALE
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Main circle radius (with margin for glow)
        margin = 6 if glow else 4
        r = s // 2 - margin

        # Glow layer
        if glow:
            glow_img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_img)
            glow_r = r + 4
            glow_alpha = int(80 * alpha)
            glow_draw.ellipse(
                [s // 2 - glow_r, s // 2 - glow_r, s // 2 + glow_r, s // 2 + glow_r],
                fill=(*color, glow_alpha),
            )
            glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=4))
            img = Image.alpha_composite(img, glow_img)
            draw = ImageDraw.Draw(img)

        # Main circle
        a = int(255 * alpha)
        draw.ellipse(
            [s // 2 - r, s // 2 - r, s // 2 + r, s // 2 + r],
            fill=(*color, a),
        )

        # Downsample with LANCZOS for anti-aliasing
        return img.resize((self.SIZE, self.SIZE), Image.LANCZOS)

    def _render_checkmark(self, color: tuple[int, int, int], alpha: float = 1.0) -> Image.Image:
        """Render an anti-aliased checkmark at 2x resolution and downsample."""
        s = self.SIZE * self._RENDER_SCALE
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        a = int(255 * alpha)
        # Checkmark path scaled to canvas
        points = [
            (s * 0.2, s * 0.5),
            (s * 0.42, s * 0.72),
            (s * 0.8, s * 0.28),
        ]
        draw.line(points, fill=(*color, a), width=max(4, s // 10), joint="curve")

        return img.resize((self.SIZE, self.SIZE), Image.LANCZOS)

    def _display(self, img: Image.Image) -> None:
        """Set the rendered PIL image as the label's photo."""
        if not self._label:
            return
        self._photo = ImageTk.PhotoImage(img)
        self._label.configure(image=self._photo)

    # ------------------------------------------------------------------
    # Animation loops
    # ------------------------------------------------------------------

    def _start_anim(self, mode: str) -> None:
        """Start (or restart) the animation loop for the given mode."""
        self._cancel_anim()
        self._anim_mode = mode
        self._anim_tick = 0
        self._anim_frame()

    def _anim_frame(self) -> None:
        """Single animation frame dispatcher."""
        if not self._win or not self._win.winfo_exists():
            return

        if self._anim_mode == "recording":
            # Static red circle with glow
            self._display(self._render_circle(_RED, alpha=1.0, glow=True))
            # No need to keep animating for static recording
            return

        elif self._anim_mode == "transition":
            # Smooth color transition over _TRANSITION_MS
            progress = min(1.0, (self._anim_tick * self._FRAME_MS) / self._TRANSITION_MS)
            color = _lerp_color(self._transition_from, self._transition_to, progress)
            self._display(self._render_circle(color, alpha=1.0, glow=True))
            if progress >= 1.0:
                # Transition complete — switch to processing pulse
                self._anim_mode = "processing"
                self._anim_tick = 0

        elif self._anim_mode == "processing":
            # Opacity-varying pulse: 0.6 -> 1.0 -> 0.6 using sine wave
            import math
            cycle = (self._anim_tick * self._FRAME_MS) / self._PULSE_PERIOD_MS
            alpha = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * cycle))
            self._display(self._render_circle(_BLUE, alpha=alpha, glow=True))

        elif self._anim_mode == "checkmark":
            elapsed = self._anim_tick * self._FRAME_MS

            if elapsed < self._CHECK_FADE_IN_MS:
                # Fade in
                alpha = elapsed / self._CHECK_FADE_IN_MS
            elif elapsed < self._CHECK_FADE_IN_MS + self._CHECK_HOLD_MS:
                # Hold
                alpha = 1.0
            elif elapsed < self._CHECK_FADE_IN_MS + self._CHECK_HOLD_MS + self._CHECK_FADE_OUT_MS:
                # Fade out
                fade_elapsed = elapsed - self._CHECK_FADE_IN_MS - self._CHECK_HOLD_MS
                alpha = 1.0 - (fade_elapsed / self._CHECK_FADE_OUT_MS)
            else:
                # Done — hide
                self._hide()
                return

            self._display(self._render_checkmark(_GREEN, alpha=max(0.0, alpha)))

        self._anim_tick += 1
        self._anim_id = self._root.after(self._FRAME_MS, self._anim_frame)

    # ------------------------------------------------------------------
    # Public API (call from Tk thread via root.after)
    # ------------------------------------------------------------------

    def on_state_change(self, new_state: AppState, success: bool = False) -> None:
        """
        Update the indicator for the given state.

        Args:
            new_state: The new AppState.
            success: If True and state is IDLE, show green checkmark briefly
                     (indicates successful paste, not a discard/error).
        """
        self._ensure_window()

        if new_state == AppState.RECORDING:
            self._cancel_auto_hide()
            self._position_near_cursor()
            self._start_anim("recording")
            self._show()

        elif new_state == AppState.PROCESSING:
            self._cancel_auto_hide()
            # Smooth color transition from red to blue
            self._transition_from = _RED
            self._transition_to = _BLUE
            self._start_anim("transition")
            self._show()

        elif new_state == AppState.IDLE:
            self._cancel_anim()
            if success:
                self._start_anim("checkmark")
                self._show()
            else:
                self._hide()

        elif new_state == AppState.ERROR:
            self._hide()

    def destroy(self) -> None:
        """Clean up the indicator window."""
        self._hide()
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None
