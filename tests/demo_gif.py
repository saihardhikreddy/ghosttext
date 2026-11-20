"""Records docs/demo.gif in our own throwaway window (GhostText must be running).

    .venv\\Scripts\\python tests\\demo_gif.py
"""
import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes as wt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab  # noqa: E402

from ghosttext import win32 as w  # noqa: E402
from tests import e2e_harness as h  # noqa: E402

NL2 = chr(10) * 2
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "demo.gif")


def main():
    threading.Thread(target=h.ui, daemon=True).start()
    for _ in range(50):
        time.sleep(0.1)
        if "edit" in h.state:
            break
    e = h.state["edit"]
    h.u.SetWindowTextW(e, "")
    h.u.SetWindowPos(e, None, 150, 120, 1150, 430, 0x4)  # SWP_NOZORDER
    me = w.GetCurrentThreadId()
    for _ in range(5):
        fg_tid = w.GetWindowThreadProcessId(w.GetForegroundWindow(), None)
        h.u.AttachThreadInput(me, fg_tid, True)
        h.u.SetForegroundWindow(e)
        h.u.AttachThreadInput(me, fg_tid, False)
        time.sleep(0.3)
        if w.GetForegroundWindow() == e:
            break
    h.guard()
    r = wt.RECT()
    w.GetWindowRect(e, ctypes.byref(r))
    box = (r.left + 8, r.top + 34, r.right - 8, r.bottom - 8)

    frames, rec = [], {"on": True}

    def record():
        while rec["on"]:
            frames.append(ImageGrab.grab(box, all_screens=True).convert("RGB"))
            time.sleep(0.08)
    t = threading.Thread(target=record)
    t.start()
    time.sleep(0.6)

    def type_slow(text):
        for ch in text:
            h.type_text(ch, delay=0.07)

    # Blank lines between phrases keep Windows' own suggestion chips (which sit above
    # the caret line, if that Windows setting is on) from covering the demo text.
    h.type_text(NL2, delay=0.1)
    type_slow("hi priya, i think teh meeting got moved to next ")
    time.sleep(1.6)
    h.guard(); h.tap(w.VK_TAB); time.sleep(0.8)
    h.type_text(NL2, delay=0.1)
    type_slow("Thanks for your hel")
    time.sleep(1.6)
    h.guard(); h.tap(w.VK_TAB); time.sleep(0.8)
    h.type_text(NL2, delay=0.1)
    type_slow("Let me know if you have any ques")
    time.sleep(1.6)
    h.guard(); h.tap(w.VK_TAB); time.sleep(1.8)
    rec["on"] = False
    t.join()
    print("text:", repr(h.read()))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    small = [f.resize((f.width * 7 // 10, f.height * 7 // 10)) for f in frames]
    pal = [f.quantize(colors=64, method=2) for f in small]
    pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=80, loop=0, optimize=True)
    print("saved", OUT, len(frames), "frames", os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
