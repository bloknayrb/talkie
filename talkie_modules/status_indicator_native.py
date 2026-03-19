"""Win32 native layered window status indicator for Talkie.

Replaces the Tkinter-based indicator with a pure Win32 layered window
using ctypes. No Tkinter dependency — animation runs in its own daemon thread.

Thread safety: the animation thread OWNS the window. All Win32 window calls
(CreateWindowExW, ShowWindow, DestroyWindow, etc.) happen on that thread.
Other threads communicate via a pending-action flag + threading.Event.
"""

import ctypes
import ctypes.wintypes
import math
import threading
import time
from typing import Optional

import numpy as np
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
HWND_TOPMOST = ctypes.wintypes.HWND(-1)  # Must be pointer-sized on 64-bit
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x02
GWL_EXSTYLE = -20

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


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

# ---------------------------------------------------------------------------
# Win32 argtypes / restype — required on 64-bit to avoid pointer truncation
# ---------------------------------------------------------------------------

# Window management
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.RegisterClassW.restype = ctypes.wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    ctypes.wintypes.DWORD, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.wintypes.HWND, ctypes.wintypes.HMENU, ctypes.wintypes.HINSTANCE,
    ctypes.wintypes.LPVOID,
]
user32.CreateWindowExW.restype = ctypes.wintypes.HWND

user32.DestroyWindow.argtypes = [ctypes.wintypes.HWND]
user32.DestroyWindow.restype = ctypes.wintypes.BOOL

user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = ctypes.wintypes.BOOL

user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = ctypes.wintypes.BOOL

# Message pump
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND,
    ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
]
user32.PeekMessageW.restype = ctypes.wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
user32.TranslateMessage.restype = ctypes.wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.wintypes.LONG

# DefWindowProcW — handle large LPARAM values on 64-bit
user32.DefWindowProcW.argtypes = [
    ctypes.wintypes.HWND, ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
]
user32.DefWindowProcW.restype = ctypes.c_long

# Cursor and DC
user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
user32.GetCursorPos.restype = ctypes.wintypes.BOOL

user32.GetDC.argtypes = [ctypes.wintypes.HWND]
user32.GetDC.restype = ctypes.wintypes.HDC

user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int

# UpdateLayeredWindow
user32.UpdateLayeredWindow.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HDC,
    ctypes.POINTER(ctypes.wintypes.POINT), ctypes.POINTER(ctypes.wintypes.SIZE),
    ctypes.wintypes.HDC, ctypes.POINTER(ctypes.wintypes.POINT),
    ctypes.wintypes.COLORREF, ctypes.c_void_p, ctypes.wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = ctypes.wintypes.BOOL

# GDI
gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC

gdi32.CreateDIBSection.argtypes = [
    ctypes.wintypes.HDC, ctypes.c_void_p, ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p), ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = ctypes.wintypes.HBITMAP

gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ

gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = ctypes.wintypes.BOOL

gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
gdi32.DeleteDC.restype = ctypes.wintypes.BOOL

# Win32 callback type for window procedures
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.wintypes.HWND,
    ctypes.c_uint,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


class WNDCLASSW(ctypes.Structure):
    """Win32 WNDCLASSW structure — not in ctypes.wintypes."""
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]


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

        # Pending action flag — read by animation thread, set by any thread
        self._pending_action: Optional[str] = None  # "show" or "hide"

        # Window creation happens on the animation thread; wait for it
        self._window_ready = threading.Event()
        self._start_thread()
        self._window_ready.wait(timeout=1.0)

    def _create_window(self) -> None:
        """Create a layered Win32 window. MUST be called on the animation thread."""
        wc_name = "TalkieIndicator"

        # Must keep the callback alive as an instance attribute to prevent GC
        self._wndproc = WNDPROC(
            lambda hwnd, msg, wp, lp: user32.DefWindowProcW(hwnd, msg, wp, lp)
        )

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = wc_name

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            # Class may already be registered from a previous instance
            err = kernel32.GetLastError()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                logger.warning("RegisterClassW failed: error %d", err)

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
            logger.error("Failed to create native indicator window (error %d)",
                         kernel32.GetLastError())
        else:
            logger.info("Created indicator window: HWND=%#x", self._hwnd)

    def _start_thread(self) -> None:
        """Start the animation daemon thread."""
        self._thread = threading.Thread(target=self._animation_loop, daemon=True)
        self._thread.start()

    def _pump_messages(self) -> None:
        """Drain the Win32 message queue for our window."""
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, 0, 0, 0x0001):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _animation_loop(self) -> None:
        """Main animation loop — owns the window, runs at ~30 FPS when visible."""
        # Create window on THIS thread so we own it
        self._create_window()
        self._window_ready.set()

        try:
            while not self._stop_event.is_set():
                self._pump_messages()

                # Read and clear pending action under lock
                with self._lock:
                    action = self._pending_action
                    self._pending_action = None

                # Execute Win32 window calls OUTSIDE the lock
                if action == "show" and self._hwnd:
                    result = user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
                    logger.debug("ShowWindow result: %d", result)
                    user32.SetWindowPos(
                        self._hwnd, HWND_TOPMOST,
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                    )
                elif action == "hide" and self._hwnd:
                    user32.ShowWindow(self._hwnd, SW_HIDE)

                with self._lock:
                    mode = self._anim_mode
                    visible = self._visible

                if not visible or mode == "none":
                    self._state_event.wait(timeout=0.1)
                    self._state_event.clear()
                    continue

                frame = self._render_frame()
                if frame is not None:
                    self._update_layered_window(frame)
                else:
                    # Animation complete — hide
                    with self._lock:
                        self._pending_action = "hide"
                        self._visible = False
                        self._anim_mode = "none"
                    continue

                time.sleep(self._FRAME_INTERVAL)
        finally:
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)
                self._hwnd = 0

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

        # Convert RGBA to premultiplied BGRA using numpy (vectorized)
        arr = np.array(img, dtype=np.uint16)  # uint16 avoids overflow during multiply
        alpha = arr[:, :, 3:4]
        rgb = arr[:, :, :3]
        premultiplied_rgb = (rgb * alpha + 127) // 255  # Round-to-nearest premultiply
        bgra = np.empty((self.SIZE, self.SIZE, 4), dtype=np.uint8)
        bgra[:, :, 0] = premultiplied_rgb[:, :, 2]  # B
        bgra[:, :, 1] = premultiplied_rgb[:, :, 1]  # G
        bgra[:, :, 2] = premultiplied_rgb[:, :, 0]  # R
        bgra[:, :, 3] = arr[:, :, 3]                 # A
        raw = bgra.tobytes()

        # Create DIB section
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

        try:
            ctypes.memmove(bits, raw, len(raw))

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
        finally:
            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)

    def _do_show(self) -> None:
        """Request the animation thread to show the window."""
        with self._lock:
            self._pending_action = "show"
            self._visible = True
        self._state_event.set()

    def _do_hide(self) -> None:
        """Request the animation thread to hide the window."""
        with self._lock:
            self._pending_action = "hide"
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
        # DestroyWindow is called in _animation_loop's finally block
