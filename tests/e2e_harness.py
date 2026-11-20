"""End-to-end check in our own throwaway window (a native Edit control), so test
keystrokes can never land in the user's documents.

Run with GhostText already running:
    .venv\\Scripts\\python tests\\e2e_harness.py [--text "..."] [--accept] [--undo] [--shot out.png]
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes as wt

sys.path.insert(0, __file__.rsplit("\\tests", 1)[0])
from ghosttext import win32 as w  # noqa: E402

u = ctypes.windll.user32
u.CreateWindowExW.restype = wt.HWND
u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
u.SetForegroundWindow.argtypes = [wt.HWND]
u.SetFocus.argtypes = [wt.HWND]
u.VkKeyScanW.restype = ctypes.c_short
gdi = ctypes.windll.gdi32
gdi.CreateFontW.restype = wt.HFONT

state = {}


def ui():
    w.set_dpi_aware()
    hinst = w.GetModuleHandleW(None)
    # Use the built-in "#32770"-free approach: a plain top window of class "Static" hosting an Edit.
    top = u.CreateWindowExW(0, "Edit", "GhostText test harness", 0x10CF0000 | 0x4,  # overlapped+visible, multiline
                            200, 200, 900, 300, None, None, hinst, None)
    font = gdi.CreateFontW(-28, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 5, 0, "Segoe UI")
    u.SendMessageW(top, 0x30, font, None)  # WM_SETFONT
    state["edit"] = top
    msg = wt.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))


def key(vk, up=False):
    inp = w.INPUT(type=w.INPUT_KEYBOARD)
    inp.ki = w.KEYBDINPUT(vk, 0, w.KEYEVENTF_KEYUP if up else 0, 0, 0)  # looks like a real key
    w.SendInput(1, ctypes.byref(inp), ctypes.sizeof(w.INPUT))


def tap(vk, shift=False):
    if shift:
        key(w.VK_SHIFT)
    key(vk)
    key(vk, True)
    if shift:
        key(w.VK_SHIFT, True)


def guard():
    if w.GetForegroundWindow() != state["edit"]:
        raise SystemExit("Harness window lost focus; stopping so keys don't go elsewhere")


def type_text(text, delay=0.04):
    for ch in text:
        guard()
        if ch == "\n":
            tap(w.VK_RETURN)
        else:
            r = u.VkKeyScanW(ord(ch))
            tap(r & 0xFF, shift=bool(r & 0x100))
        time.sleep(delay)


def read():
    e = state["edit"]
    n = u.SendMessageW(e, 0x0E, 0, None)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.SendMessageW(e, 0x0D, n + 1, buf)
    return buf.value


def shot(path):
    from PIL import ImageGrab
    r = wt.RECT()
    w.GetWindowRect(state["edit"], ctypes.byref(r))
    ImageGrab.grab((r.left, r.top, r.right + 300, r.bottom), all_screens=True).save(path)


def main():
    threading.Thread(target=ui, daemon=True).start()
    for _ in range(50):
        time.sleep(0.1)
        if "edit" in state:
            break
    e = state["edit"]
    # Windows' foreground lock can refuse a background process; SwitchToThisWindow usually works.
    u.SwitchToThisWindow.argtypes = [wt.HWND, wt.BOOL]
    me = w.GetCurrentThreadId()
    for _ in range(3):
        fg_tid = w.GetWindowThreadProcessId(w.GetForegroundWindow(), None)
        u.AttachThreadInput(me, fg_tid, True)
        u.BringWindowToTop(e)
        u.SetForegroundWindow(e)
        u.AttachThreadInput(me, fg_tid, False)
        u.SwitchToThisWindow(e, True)
        time.sleep(0.4)
        if w.GetForegroundWindow() == e:
            break
    guard()

    args = sys.argv
    phrase = args[args.index("--text") + 1] if "--text" in args else "i think teh quick brwon fox is realy wierd. "
    type_text(phrase)
    time.sleep(0.5)
    print("AFTER TYPING:", repr(read()))
    if "--accept" in args:
        time.sleep(float(args[args.index("--wait") + 1]) if "--wait" in args else 2.0)
        if "--shot" in args:
            shot(args[args.index("--shot") + 1])
        guard()
        tap(w.VK_TAB)
        time.sleep(0.5)
        print("AFTER TAB:", repr(read()))
    if "--undo" in args:
        type_text("becuase ")
        time.sleep(0.3)
        print("AFTER 'becuase ':", repr(read()))
        guard()
        tap(w.VK_BACK)
        time.sleep(0.4)
        print("AFTER BACKSPACE (undo):", repr(read()))
        print("(undo teaches GhostText to ignore 'becuase'; remove it from ignored_words in config.json)")
    if "--hold" in args:
        time.sleep(float(args[args.index("--hold") + 1]))


if __name__ == "__main__":
    main()
