"""Click-through, never-focused layered window that draws the grey ghost text
right after the caret. Lives on the UI thread (same thread as the hooks)."""
import ctypes
import os
import threading
from ctypes import wintypes as wt

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import win32 as w

WM_GHOST_UPDATE = w.WM_APP + 1
FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _font(px):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), px)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex(color, alpha=255):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


class Overlay:
    def __init__(self, color="#8a8a8a"):
        self.color = color
        self.hwnd = None
        self._pending = None
        self._lock = threading.Lock()
        self._fonts = {}
        self.visible = False
        self.on_show = None  # callback(seq, text) -> bool, runs on the UI thread
        self._wndproc = w.WNDPROC(self._proc)  # keep a reference

    # -- creation (call on the UI thread) --
    def create(self):
        hinst = w.GetModuleHandleW(None)
        wc = w.WNDCLASSEXW(cbSize=ctypes.sizeof(w.WNDCLASSEXW), lpfnWndProc=self._wndproc,
                           hInstance=hinst, lpszClassName="GhostTextOverlay")
        w.RegisterClassExW(ctypes.byref(wc))
        ex = (w.WS_EX_LAYERED | w.WS_EX_TRANSPARENT | w.WS_EX_TOPMOST
              | w.WS_EX_TOOLWINDOW | w.WS_EX_NOACTIVATE)
        self.hwnd = w.CreateWindowExW(ex, "GhostTextOverlay", "GhostText", w.WS_POPUP,
                                      0, 0, 1, 1, None, None, hinst, None)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_GHOST_UPDATE:
            with self._lock:
                job, self._pending = self._pending, None
            if job is None:
                return 0
            if job == "hide":
                self._hide_now()
            else:
                text, x, y, height, pill, seq, max_width = job
                text = self._fit(text, height, max_width)
                if text and (self.on_show is None or self.on_show(seq, text)):
                    try:
                        self._render(text, x, y, height, pill)
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception("render failed")
            return 0
        return w.DefWindowProcW(hwnd, msg, wparam, lparam)

    # -- thread-safe API --
    def show(self, text, x, y, height, pill=False, seq=None, max_width=None):
        with self._lock:
            self._pending = (text, x, y, height, pill, seq, max_width)
        w.PostMessageW(self.hwnd, WM_GHOST_UPDATE, 0, 0)

    def hide(self):
        """Safe from any thread; immediate when called on the UI thread."""
        with self._lock:
            self._pending = "hide"
        w.PostMessageW(self.hwnd, WM_GHOST_UPDATE, 0, 0)

    def hide_now(self):
        """UI thread only (e.g. from inside the keyboard hook)."""
        with self._lock:
            self._pending = None
        self._hide_now()

    def _hide_now(self):
        if self.visible:
            w.ShowWindow(self.hwnd, w.SW_HIDE)
            self.visible = False

    # -- drawing --
    def _get_font(self, px):
        px = max(9, min(int(px), 64))
        if px not in self._fonts:
            self._fonts[px] = _font(px)
        return self._fonts[px]

    def _font_px(self, height):
        return height * 0.72 if height >= 12 else 14

    def _fit(self, text, height, max_width):
        """Drop trailing words until the suggestion (plus the Tab badge) fits."""
        if not max_width:
            return text
        font = self._get_font(self._font_px(height))
        budget = max_width - 60
        while text and font.getlength(text) > budget:
            cut = text.rstrip().rfind(" ")
            if cut <= 0:
                return None
            text = text[:cut]
        return text

    def _render(self, text, x, y, height, pill):
        text = text.replace("\n", " ")
        font_px = self._font_px(height)
        font = self._get_font(font_px)
        hint_font = self._get_font(max(9, font_px * 0.62))
        ascent, descent = font.getmetrics()
        tw = int(font.getlength(text)) + 2
        hint = "Tab"
        hw = int(hint_font.getlength(hint)) + 10
        gap = 6
        h = max(int(height), ascent + descent) + 2
        width = tw + gap + hw + (12 if pill else 0) + 2
        img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        tx = 6 if pill else 0
        if pill:
            d.rounded_rectangle((0, 0, width - 1, h - 1), radius=h // 3, fill=(32, 32, 32, 225))
            color = (210, 210, 210, 255)
        else:
            color = _hex(self.color)
        # Put the text baseline about where the app's baseline is: bottom of caret minus descent.
        ty = h - 1 - descent - ascent
        d.text((tx, ty), text, font=font, fill=color)
        hx = tx + tw + gap
        hb = (hx, (h - hint_font.size - 6) // 2, hx + hw, (h + hint_font.size + 6) // 2)
        d.rounded_rectangle(hb, radius=4, fill=(60, 60, 60, 200))
        d.text((hx + 5, hb[1] + 2), hint, font=hint_font, fill=(235, 235, 235, 255))
        self._blit(img, int(x) - (tx if pill else 0), int(y + (height - h)) if not pill else int(y))

    def _blit(self, img, x, y):
        width, height = img.size
        r, g, b, a = img.split()
        r, g, b = (ImageChops.multiply(c, a) for c in (r, g, b))  # premultiply
        data = Image.merge("RGBA", (b, g, r, a)).tobytes()  # BGRA byte order
        screen = w.GetDC(None)
        mem = w.CreateCompatibleDC(screen)
        bmi = w.BITMAPINFOHEADER(biSize=ctypes.sizeof(w.BITMAPINFOHEADER), biWidth=width,
                                 biHeight=-height, biPlanes=1, biBitCount=32, biCompression=0)
        bits = ctypes.c_void_p()
        hbmp = w.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = w.SelectObject(mem, hbmp)
        ctypes.memmove(bits, data, len(data))
        blend = w.BLENDFUNCTION(w.AC_SRC_OVER, 0, 255, w.AC_SRC_ALPHA)
        w.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wt.POINT(x, y)),
                              ctypes.byref(wt.SIZE(width, height)), mem,
                              ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), w.ULW_ALPHA)
        w.SelectObject(mem, old)
        w.DeleteObject(hbmp)
        w.DeleteDC(mem)
        w.ReleaseDC(None, screen)
        if not self.visible:
            w.ShowWindow(self.hwnd, w.SW_SHOWNOACTIVATE)
            self.visible = True
        w.SetWindowPos(self.hwnd, w.HWND_TOPMOST, 0, 0, 0, 0,
                       w.SWP_NOMOVE | w.SWP_NOSIZE | w.SWP_NOACTIVATE)
