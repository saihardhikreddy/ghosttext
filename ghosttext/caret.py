"""Find the text caret on screen in whatever app has focus.

Tries, in order: the classic Win32 caret (Notepad, most native apps), the MSAA
caret object (Chrome, Edge, Firefox, Electron), then UI Automation's
TextPattern2 caret range (Word, modern XAML apps). Also detects password fields.
Must be used from a single worker thread (COM)."""
import ctypes
import logging
from ctypes import wintypes as wt

from . import win32 as w

log = logging.getLogger(__name__)
OBJID_CARET = 0xFFFFFFF8
UIA_TextPattern2Id = 10024
UIA_TextPatternId = 10014


class Caret:
    __slots__ = ("x", "y", "h", "source")

    def __init__(self, x, y, h, source):
        self.x, self.y, self.h, self.source = int(x), int(y), int(h), source

    def __repr__(self):
        return f"Caret({self.x},{self.y},h={self.h},{self.source})"


class CaretLocator:
    def __init__(self):
        self._ready = False
        self.uia = None
        self.UIA = None
        self.IAccessible = None

    def _init(self):
        if self._ready:
            return
        self._ready = True
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass
        try:
            acc = comtypes.client.GetModule("oleacc.dll")
            self.IAccessible = acc.IAccessible
        except Exception:
            log.exception("MSAA unavailable")
        try:
            uia = comtypes.client.GetModule("UIAutomationCore.dll")
            self.UIA = uia
            self.uia = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        except Exception:
            log.exception("UI Automation unavailable")

    # ---------------------------------------------------------------- caret
    def locate(self):
        self._init()
        fg = w.GetForegroundWindow()
        if not fg:
            return None
        win = wt.RECT()
        w.GetWindowRect(fg, ctypes.byref(win))
        gti = w.gui_thread_info(fg)

        def inside(c):
            return c and c.h > 0 and win.left - 5 <= c.x <= win.right + 5 and win.top - 5 <= c.y <= win.bottom + 5

        for fn in (self._win32, self._msaa, self._uia):
            try:
                c = fn(fg, gti)
            except Exception as e:  # COM can throw all sorts of things
                log.debug("caret %s failed: %s", fn.__name__, e)
                c = None
            if inside(c):
                return c
        return None

    def _win32(self, fg, gti):
        if not gti or not gti.hwndCaret:
            return None
        rc = gti.rcCaret
        if rc.bottom - rc.top <= 0:
            return None
        pt = wt.POINT(rc.left, rc.top)
        w.ClientToScreen(gti.hwndCaret, ctypes.byref(pt))
        return Caret(pt.x, pt.y, rc.bottom - rc.top, "win32")

    def _msaa(self, fg, gti):
        if not self.IAccessible:
            return None
        hwnd = (gti.hwndFocus if gti and gti.hwndFocus else None) or fg
        ptr = ctypes.POINTER(self.IAccessible)()
        hr = ctypes.oledll.oleacc.AccessibleObjectFromWindow
        hr(wt.HWND(hwnd), wt.DWORD(OBJID_CARET), ctypes.byref(self.IAccessible._iid_), ctypes.byref(ptr))
        if not ptr:
            return None
        x, y, cw, ch = ptr.accLocation(0)
        if ch <= 0 or (x == 0 and y == 0):
            return None
        return Caret(x, y, ch, "msaa")

    def _uia(self, fg, gti):
        if not self.uia:
            return None
        el = self.uia.GetFocusedElement()
        if not el:
            return None
        pat = el.GetCurrentPattern(UIA_TextPattern2Id)
        if not pat:
            return None
        tp2 = pat.QueryInterface(self.UIA.IUIAutomationTextPattern2)
        _active, rng = tp2.GetCaretRange()
        if not rng:
            return None
        rects = list(rng.GetBoundingRectangles() or ())
        if len(rects) >= 4:
            return Caret(rects[0], rects[1], rects[3], "uia")
        # Degenerate range: measure the character after the caret, else the one before.
        r = rng.Clone()
        r.ExpandToEnclosingUnit(0)  # TextUnit_Character
        rects = list(r.GetBoundingRectangles() or ())
        if len(rects) >= 4:
            return Caret(rects[0], rects[1], rects[3], "uia")
        r = rng.Clone()
        r.MoveEndpointByUnit(0, 0, -1)  # Start, Character, -1
        rects = list(r.GetBoundingRectangles() or ())
        if len(rects) >= 4:
            return Caret(rects[0] + rects[2], rects[1], rects[3], "uia")
        return None

    # ------------------------------------------------------------- password
    def is_password(self):
        self._init()
        gti = w.gui_thread_info()
        if gti and gti.hwndFocus:
            if w.class_name(gti.hwndFocus).lower() == "edit" and \
                    w.GetWindowLongW(gti.hwndFocus, w.GWL_STYLE) & w.ES_PASSWORD:
                return True
        if self.uia:
            try:
                el = self.uia.GetFocusedElement()
                return bool(el and el.CurrentIsPassword)
            except Exception:
                return False
        return False

    def text_follows_caret(self):
        """True if there is more text on the caret's line (so inline ghost text would
        overlap it); None if we can't tell."""
        self._init()
        gti = w.gui_thread_info()
        if gti and gti.hwndFocus and w.class_name(gti.hwndFocus).lower().startswith(("edit", "richedit")):
            try:
                send = ctypes.windll.user32.SendMessageW
                send.restype = ctypes.c_ssize_t
                send.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
                n = send(gti.hwndFocus, 0x0E, 0, 0)  # WM_GETTEXTLENGTH
                if 0 < n < 200_000:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    send(gti.hwndFocus, 0x0D, n + 1, ctypes.addressof(buf))
                    sel = send(gti.hwndFocus, 0xB0, 0, 0)  # returns start|end<<16 for small texts
                    pos = (sel >> 16) & 0xFFFF
                    nxt = buf.value[pos:pos + 1]
                    return bool(nxt) and nxt not in "\r\n"
            except Exception:
                pass
        if not self.uia:
            return None
        try:
            el = self.uia.GetFocusedElement()
            pat = el.GetCurrentPattern(UIA_TextPattern2Id)
            if not pat:
                return None
            tp2 = pat.QueryInterface(self.UIA.IUIAutomationTextPattern2)
            _active, caret = tp2.GetCaretRange()
            r = caret.Clone()
            r.MoveEndpointByUnit(1, 0, 1)  # End += 1 character
            nxt = r.GetText(1)
            return bool(nxt) and nxt not in "\r\n"
        except Exception:
            return None

    def field_text_before_caret(self, limit=600):
        """Best-effort read of the text already in the focused field (before the caret)."""
        self._init()
        if not self.uia:
            return None
        try:
            el = self.uia.GetFocusedElement()
            pat = el.GetCurrentPattern(UIA_TextPattern2Id)
            if not pat:
                return None
            tp2 = pat.QueryInterface(self.UIA.IUIAutomationTextPattern2)
            _active, caret = tp2.GetCaretRange()
            doc = tp2.DocumentRange
            r = doc.Clone()
            # Make r = [document start, caret]
            r.MoveEndpointByRange(1, caret, 0)  # End <- caret.Start
            text = r.GetText(-1)
            return text[-limit:]
        except Exception:
            return None
