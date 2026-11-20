"""End-to-end check in Chromium (Edge) using a throwaway profile and a blank
<textarea> app window, so nothing touches the user's own browser session.

    .venv\\Scripts\\python tests\\e2e_browser.py [--shot out.png]
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes as wt

sys.coinit_flags = 0
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghosttext import win32 as w  # noqa: E402
from tests.e2e_harness import tap, u  # noqa: E402

EDGE = [p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if os.path.exists(p)]
PAGE = ("data:text/html,<title>GhostText browser test</title>"
        "<textarea autofocus style='font:22px Segoe UI;width:94vw;height:80vh'></textarea>")


def title(h):
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, buf, 256)
    return buf.value


def main():
    w.set_dpi_aware()
    profile = tempfile.mkdtemp(prefix="ghosttext-edge-")
    proc = subprocess.Popen([EDGE[0], f"--user-data-dir={profile}", "--no-first-run",
                             "--no-default-browser-check", "--window-size=1000,400",
                             "--window-position=150,150", f"--app={PAGE}"])
    win = None
    for _ in range(60):
        time.sleep(0.25)
        found = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(h, _):
            if u.IsWindowVisible(h) and "GhostText browser test" in title(h):
                found.append(h)
            return True
        u.EnumWindows(cb, 0)
        if found:
            win = found[0]
            me = w.GetCurrentThreadId()
            fg_tid = w.GetWindowThreadProcessId(w.GetForegroundWindow(), None)
            u.AttachThreadInput(me, fg_tid, True)
            u.SetForegroundWindow(win)
            u.AttachThreadInput(me, fg_tid, False)
            time.sleep(0.3)
            if w.GetForegroundWindow() == win:
                break
            win = None
    if not win:
        raise SystemExit("test window didn't come to the front")
    time.sleep(1.0)

    def guard():
        if w.GetForegroundWindow() != win:
            raise SystemExit("test window lost focus; stopping")

    def type_text(text):
        for ch in text:
            guard()
            r = u.VkKeyScanW(ord(ch))
            tap(r & 0xFF, shift=bool(r & 0x100))
            time.sleep(0.04)

    from ghosttext.caret import CaretLocator
    loc = CaretLocator()

    def value():
        el = loc.uia.GetFocusedElement()
        pat = el.GetCurrentPattern(10002).QueryInterface(loc.UIA.IUIAutomationValuePattern)
        return pat.CurrentValue

    type_text("Sorry for teh late reply, I was travelling. Let me know if you have any ques")
    time.sleep(0.5)
    print("caret:", loc.locate())
    print("AFTER TYPING:", repr(value()))
    time.sleep(2.0)
    if "--shot" in sys.argv:
        from PIL import ImageGrab
        r = wt.RECT()
        w.GetWindowRect(win, ctypes.byref(r))
        ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True).save(
            sys.argv[sys.argv.index("--shot") + 1])
    guard()
    tap(w.VK_TAB)
    time.sleep(0.5)
    print("AFTER TAB:", repr(value()))
    proc.terminate()
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    time.sleep(1)
    shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
