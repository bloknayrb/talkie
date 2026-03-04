"""Near-cursor floating status indicator for Talkie pipeline state."""

import ctypes
import tkinter as tk
from typing import Optional

from talkie_modules.logger import get_logger
from talkie_modules.state import AppState

logger = get_logger("indicator")

# Win32 cursor position
_point_cls = ctypes.wintypes.POINT if hasattr(ctypes, "wintypes") else None


def _get_cursor_pos() -> tuple[int, int]:
    """Return (x, y) screen coordinates of the mouse cursor."""
    import ctypes.wintypes

    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


class StatusIndicator:
    """
    Small floating Toplevel near the cursor showing pipeline state.

    - Recording: red circle
    - Processing: blue pulsing circle
    - Success: green checkmark flash (1.5s)
    - Idle/Error: hidden

    Must be created and driven from the Tk main thread.
    Use root.after(0, indicator.on_state_change, new_state) from other threads.
    """

    SIZE = 28
    OFFSET_X = 16
    OFFSET_Y = 16

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._pulse_id: Optional[str] = None
        self._hide_id: Optional[str] = None
        self._pulse_growing = True
        self._anchor_x = 0
        self._anchor_y = 0

    def _ensure_window(self) -> None:
        """Create the indicator Toplevel if it doesn't exist."""
        if self._win is not None and self._win.winfo_exists():
            return

        self._win = tk.Toplevel(self._root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", "black")
        self._win.configure(bg="black")
        # Make it non-interactive (click-through)
        self._win.attributes("-disabled", True)

        self._canvas = tk.Canvas(
            self._win,
            width=self.SIZE,
            height=self.SIZE,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack()
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
        self._cancel_pulse()
        self._cancel_auto_hide()
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def _draw_circle(self, color: str, radius: Optional[int] = None) -> None:
        """Draw a filled circle (recording/processing indicator)."""
        if not self._canvas:
            return
        self._canvas.delete("all")
        r = radius or (self.SIZE // 2 - 2)
        cx, cy = self.SIZE // 2, self.SIZE // 2
        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r, fill=color, outline=color
        )

    def _draw_checkmark(self, color: str = "#22c55e") -> None:
        """Draw a checkmark shape (success indicator)."""
        if not self._canvas:
            return
        self._canvas.delete("all")
        # Simple checkmark path scaled to SIZE
        s = self.SIZE
        self._canvas.create_line(
            s * 0.2, s * 0.5, s * 0.42, s * 0.72, s * 0.8, s * 0.28,
            fill=color, width=3, capstyle="round", joinstyle="round",
        )

    def _start_pulse(self) -> None:
        """Animate a pulsing blue circle."""
        self._pulse_growing = True
        self._pulse_step(8)

    def _pulse_step(self, radius: int) -> None:
        """Single pulse animation frame."""
        if not self._canvas or not self._win or not self._win.winfo_exists():
            return
        self._draw_circle("#3b82f6", radius)
        max_r = self.SIZE // 2 - 2
        min_r = max_r - 4

        if self._pulse_growing:
            radius += 1
            if radius >= max_r:
                self._pulse_growing = False
        else:
            radius -= 1
            if radius <= min_r:
                self._pulse_growing = True

        self._pulse_id = self._root.after(80, self._pulse_step, radius)

    def _cancel_pulse(self) -> None:
        if self._pulse_id:
            self._root.after_cancel(self._pulse_id)
            self._pulse_id = None

    def _cancel_auto_hide(self) -> None:
        if self._hide_id:
            self._root.after_cancel(self._hide_id)
            self._hide_id = None

    # -- Public API (call from Tk thread via root.after) --

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
            self._cancel_pulse()
            self._cancel_auto_hide()
            self._position_near_cursor()
            self._draw_circle("#ef4444")  # red
            self._show()

        elif new_state == AppState.PROCESSING:
            self._cancel_auto_hide()
            # Keep position from recording start — don't reposition
            self._start_pulse()
            self._show()

        elif new_state == AppState.IDLE:
            self._cancel_pulse()
            if success:
                self._draw_checkmark()
                self._show()
                self._hide_id = self._root.after(1500, self._hide)
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
