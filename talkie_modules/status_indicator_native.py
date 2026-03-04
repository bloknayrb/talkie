"""Win32 native layered window status indicator for Talkie.

Replaces the Tkinter-based indicator with a pure Win32 layered window
using ctypes. No Tkinter dependency — animation runs in its own daemon thread.
"""

import ctypes
import ctypes.wintypes
import math
import threading
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from talkie_modules.logger import get_logger
from talkie_modules.state import AppState

logger = get_logger("indicator")

# Win32 constants
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_POPUP = 0x80000000
SW_SHOWNOACTIVATE = 8
SW_HIDE = 0
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x02
GWL_EXSTYLE = -20

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


_RED = _hex_to_rgb("#ef4444")
_BLUE = _hex_to_rgb("#3b82f6")
_GREEN = _hex_to_rgb("#22c55e")


class NativeStatusIndicator:
    """
    Win32 layered window status indicator.

    - Recording: red circle with glow
    - Processing: blue opacity-pulsing circle
    - Success: green checkmark with fade-in/hold/fade-out
    - Idle/Error: hidden

    Thread-safe — on_state_change can be called from any thread.
    """

    SIZE = 32
    _RENDER_SCALE = 2
    OFFSET_X = 16
    OFFSET_Y = 16

    _FRAME_INTERVAL = 1 / 30  # ~30 FPS
    _PULSE_PERIOD = 1.2  # seconds
    _TRANSITION_DURATION = 0.2  # seconds
    _CHECK_FADE_IN = 0.2
    _CHECK_HOLD = 0.8
    _CHECK_FADE_OUT = 0.5

    def __init__(self) -> None:
        self._hwnd: int = 0
        self._hdc: int = 0
        self._visible = False

        self._lock = threading.Lock()
        self._anim_mode: str = "none"
        self._anim_start: float = 0.0
        self._transition_from = _RED
        self._transition_to = _BLUE
        self._anchor_x = 0
        self._anchor_y = 0
        self._stop_event = threading.Event()
        self._state_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._create_window()
        self._start_thread()

    def _create_window(self) -> None:
        """Create a layered Win32 window."""
        # Register a window class
        wc_name = "TalkieIndicator"
        wc = ctypes.wintypes.WNDCLASS()
        wc.lpfnWndProc = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.wintypes.HWND,
            ctypes.c_uint,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        )(lambda hwnd, msg, wp, lp: user32.DefWindowProcW(hwnd, msg, wp, lp))
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = wc_name

        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass  # Already registered

        ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW

        self._hwnd = user32.CreateWindowExW(
            ex_style,
            wc_name,
            "TalkieIndicator",
            WS_POPUP,
            0, 0, self.SIZE, self.SIZE,
            0, 0,
            kernel32.GetModuleHandleW(None),
            0,
        )

        if not self._hwnd:
            logger.error("Failed to create native indicator window")

    def _start_thread(self) -> None:
        """Start the animation daemon thread."""
        self._thread = threading.Thread(target=self._animation_loop, daemon=True)
        self._thread.start()

    def _animation_loop(self) -> None:
        """Main animation loop running at ~30 FPS when visible."""
        while not self._stop_event.is_set():
            # Wait until there's something to animate
            self._state_event.wait(timeout=0.1)

            with self._lock:
                mode = self._anim_mode
                visible = self._visible

            if not visible or mode == "none":
                self._state_event.clear()
                continue

            frame = self._render_frame()
            if frame is not None:
                self._update_layered_window(frame)
            else:
                # Animation complete — hide
                self._do_hide()
                self._state_event.clear()
                continue

            time.sleep(self._FRAME_INTERVAL)

    def _render_frame(self) -> Optional[Image.Image]:
        """Render the current animation frame. Returns None if animation is done."""
        with self._lock:
            mode = self._anim_mode
            elapsed = time.time() - self._anim_start
            trans_from = self._transition_from
            trans_to = self._transition_to

        if mode == "recording":
            return self._render_circle(_RED, alpha=1.0, glow=True)

        elif mode == "transition":
            progress = min(1.0, elapsed / self._TRANSITION_DURATION)
            color = _lerp_color(trans_from, trans_to, progress)
            if progress >= 1.0:
                with self._lock:
                    self._anim_mode = "processing"
                    self._anim_start = time.time()
            return self._render_circle(color, alpha=1.0, glow=True)

        elif mode == "processing":
            cycle = elapsed / self._PULSE_PERIOD
            alpha = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * cycle))
            return self._render_circle(_BLUE, alpha=alpha, glow=True)

        elif mode == "checkmark":
            if elapsed < self._CHECK_FADE_IN:
                alpha = elapsed / self._CHECK_FADE_IN
            elif elapsed < self._CHECK_FADE_IN + self._CHECK_HOLD:
                alpha = 1.0
            elif elapsed < self._CHECK_FADE_IN + self._CHECK_HOLD + self._CHECK_FADE_OUT:
                fade_elapsed = elapsed - self._CHECK_FADE_IN - self._CHECK_HOLD
                alpha = 1.0 - (fade_elapsed / self._CHECK_FADE_OUT)
            else:
                return None  # Signal animation complete
            return self._render_checkmark(_GREEN, alpha=max(0.0, alpha))

        return None

    # ------------------------------------------------------------------
    # PIL rendering (same as Tkinter version)
    # ------------------------------------------------------------------

    def _render_circle(self, color: tuple[int, int, int], alpha: float = 1.0,
                       glow: bool = False) -> Image.Image:
        s = self.SIZE * self._RENDER_SCALE
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        margin = 6 if glow else 4
        r = s // 2 - margin

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

        a = int(255 * alpha)
        draw.ellipse(
            [s // 2 - r, s // 2 - r, s // 2 + r, s // 2 + r],
            fill=(*color, a),
        )

        return img.resize((self.SIZE, self.SIZE), Image.LANCZOS)

    def _render_checkmark(self, color: tuple[int, int, int], alpha: float = 1.0) -> Image.Image:
        s = self.SIZE * self._RENDER_SCALE
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        a = int(255 * alpha)
        points = [
            (s * 0.2, s * 0.5),
            (s * 0.42, s * 0.72),
            (s * 0.8, s * 0.28),
        ]
        draw.line(points, fill=(*color, a), width=max(4, s // 10), joint="curve")

        return img.resize((self.SIZE, self.SIZE), Image.LANCZOS)

    # ------------------------------------------------------------------
    # Win32 window operations
    # ------------------------------------------------------------------

    def _update_layered_window(self, img: Image.Image) -> None:
        """Update the layered window with a PIL RGBA image."""
        if not self._hwnd:
            return

        # Convert RGBA to BGRA for Win32
        r, g, b, a = img.split()
        bgra = Image.merge("RGBA", (b, g, r, a))
        raw = bgra.tobytes()

        # Create DIB section
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = self.SIZE
        bmi.biHeight = -self.SIZE  # Top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(
            hdc_mem,
            ctypes.byref(bmi),
            0,  # DIB_RGB_COLORS
            ctypes.byref(bits),
            0,
            0,
        )

        if not hbmp:
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            return

        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        # Copy pixel data — premultiply alpha for UpdateLayeredWindow
        premultiplied = bytearray(len(raw))
        for i in range(0, len(raw), 4):
            alpha_val = raw[i + 3]
            if alpha_val == 255:
                premultiplied[i:i + 4] = raw[i:i + 4]
            elif alpha_val == 0:
                premultiplied[i:i + 4] = b'\x00\x00\x00\x00'
            else:
                factor = alpha_val / 255.0
                premultiplied[i] = int(raw[i] * factor)
                premultiplied[i + 1] = int(raw[i + 1] * factor)
                premultiplied[i + 2] = int(raw[i + 2] * factor)
                premultiplied[i + 3] = alpha_val

        ctypes.memmove(bits, bytes(premultiplied), len(premultiplied))

        # UpdateLayeredWindow
        pt_src = ctypes.wintypes.POINT(0, 0)
        pt_dst = ctypes.wintypes.POINT(self._anchor_x, self._anchor_y)
        sz = ctypes.wintypes.SIZE(self.SIZE, self.SIZE)

        blend = BLENDFUNCTION()
        blend.BlendOp = AC_SRC_OVER
        blend.BlendFlags = 0
        blend.SourceConstantAlpha = 255
        blend.AlphaFormat = AC_SRC_ALPHA

        user32.UpdateLayeredWindow(
            self._hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(sz),
            hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA,
        )

        # Cleanup GDI
        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

    def _do_show(self) -> None:
        """Show the window (non-activating)."""
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            user32.SetWindowPos(
                self._hwnd, HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        with self._lock:
            self._visible = True
        self._state_event.set()

    def _do_hide(self) -> None:
        """Hide the window."""
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_HIDE)
        with self._lock:
            self._visible = False
            self._anim_mode = "none"

    def _get_cursor_pos(self) -> tuple[int, int]:
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def on_state_change(self, new_state: AppState, success: bool = False) -> None:
        """Update the indicator for the given state. Thread-safe."""
        if new_state == AppState.RECORDING:
            try:
                x, y = self._get_cursor_pos()
            except Exception:
                x, y = 100, 100
            with self._lock:
                self._anchor_x = x + self.OFFSET_X
                self._anchor_y = y + self.OFFSET_Y
                self._anim_mode = "recording"
                self._anim_start = time.time()
            self._do_show()

        elif new_state == AppState.PROCESSING:
            with self._lock:
                self._transition_from = _RED
                self._transition_to = _BLUE
                self._anim_mode = "transition"
                self._anim_start = time.time()
            self._state_event.set()

        elif new_state == AppState.IDLE:
            if success:
                with self._lock:
                    self._anim_mode = "checkmark"
                    self._anim_start = time.time()
                self._state_event.set()
            else:
                self._do_hide()

        elif new_state == AppState.ERROR:
            self._do_hide()

    def destroy(self) -> None:
        """Clean up the indicator window and stop the animation thread."""
        self._stop_event.set()
        self._state_event.set()  # Wake up thread so it can exit
        if self._thread:
            self._thread.join(timeout=2.0)
        self._do_hide()
        if self._hwnd:
            try:
                user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = 0
