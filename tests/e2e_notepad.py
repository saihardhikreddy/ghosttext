"""Live check in Windows 11 Notepad, in OUR OWN temp file's tab only.

Safety: opens a fresh empty temp file, and before every keystroke checks that
Notepad is in front, the window title names our temp file, and the visible
editor is the one we started in. Anything else aborts.

    .venv\\Scripts\\python tests\\e2e_notepad.py [--text "..."] [--shot out.png] [--close]
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes as wt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghosttext import win32 as w  # noqa: E402
from tests.e2e_harness import key, tap, u  # noqa: E402

u.FindWindowExW.restype = wt.HWND
u.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]


def title(h):
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, buf, 512)
    return buf.value


def visible_edit(top):
    def walk(parent):
        child = None
        while True:
            child = u.FindWindowExW(parent, child, None, None)
            if not child:
                return None
            if w.class_name(child).startswith("RichEdit") and u.IsWindowVisible(child):
                return child
            found = walk(child)
            if found:
                return found
    return walk(top)


def read(edit):
    n = u.SendMessageW(edit, 0x0E, 0, None)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.SendMessageW(edit, 0x0D, n + 1, buf)
    return buf.value


def notepad_windows():
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if w.class_name(h) == "Notepad" and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(cb, 0)
    return found


def focus(win):
    me = w.GetCurrentThreadId()
    for _ in range(5):
        fg_tid = w.GetWindowThreadProcessId(w.GetForegroundWindow(), None)
        u.AttachThreadInput(me, fg_tid, True)
        u.SetForegroundWindow(win)
        u.AttachThreadInput(me, fg_tid, False)
        time.sleep(0.3)
        if w.GetForegroundWindow() == win:
            return True
    return False


def open_own_tab(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    subprocess.Popen(["notepad.exe", path])
    for _ in range(40):
        time.sleep(0.25)
        for h in notepad_windows():
            if stem in title(h) and focus(h):
                return h, stem
        # Notepad may have opened our file as a new tab without refreshing its title
        # until it's in front: bring windows forward and look again (nothing is typed).
        for h in notepad_windows():
            focus(h)
            time.sleep(0.2)
            if stem in title(h):
                return h, stem
    raise SystemExit("couldn't bring our temp tab to the front")


def main():
    w.set_dpi_aware()
    path = os.path.join(tempfile.gettempdir(), f"ghosttext-test-{int(time.time())}.txt")
    open(path, "w").close()
    win, stem = open_own_tab(path)
    time.sleep(0.6)
    edit = visible_edit(win)
    if not edit or read(edit) != "":
        raise SystemExit("editor not found or not empty; refusing to type")

    def guard():
        if w.GetForegroundWindow() != win or stem not in title(win) or visible_edit(win) != edit:
            raise SystemExit("our tab is no longer in front; stopping")

    def type_text(text):
        for ch in text:
            guard()
            if ch == "\n":
                tap(w.VK_RETURN)
            else:
                r = u.VkKeyScanW(ord(ch))
                tap(r & 0xFF, shift=bool(r & 0x100))
            time.sleep(0.05)

    args = sys.argv
    text = args[args.index("--text") + 1] if "--text" in args else \
        "The wwter will freeze at this ooint. I will let you know when I get "
    type_text(text)
    time.sleep(0.5)
    print("AFTER TYPING:", repr(read(edit)))
    time.sleep(2.0)
    if "--shot" in args:
        from PIL import ImageGrab
        r = wt.RECT()
        w.GetWindowRect(win, ctypes.byref(r))
        ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True).save(args[args.index("--shot") + 1])
    guard()
    tap(w.VK_TAB)
    time.sleep(0.6)
    print("AFTER TAB:", repr(read(edit)))
    if "--close" in args:
        guard()
        key(w.VK_CONTROL); tap(ord("S")); key(w.VK_CONTROL, True)   # save our temp file
        time.sleep(0.5)
        guard()
        key(w.VK_CONTROL); tap(ord("W")); key(w.VK_CONTROL, True)   # close our tab
        time.sleep(0.5)
    os.remove(path) if "--close" in args else None


if __name__ == "__main__":
    main()
