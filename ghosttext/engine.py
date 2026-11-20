"""The typing brain: a global low-level keyboard/mouse hook that keeps a short
buffer of what you've typed in the focused field, fixes typos at word
boundaries, and shows/accepts ghost-text completions.

Threading: hooks, overlay and all buffer state live on one UI thread. The
Worker thread does the slow things (model calls, caret lookup over COM) and
hands results back to the UI thread through the overlay's window message."""
import ctypes
import ctypes.wintypes
import logging
import queue
import re
import threading
import time

from . import win32 as w
from .caret import CaretLocator

log = logging.getLogger(__name__)

MODIFIERS = {w.VK_SHIFT, w.VK_CONTROL, w.VK_MENU, w.VK_LSHIFT, w.VK_RSHIFT, w.VK_LCONTROL,
             w.VK_RCONTROL, w.VK_LMENU, w.VK_RMENU, w.VK_LWIN, w.VK_RWIN, w.VK_CAPITAL}
NAV_KEYS = {w.VK_PRIOR, w.VK_NEXT, w.VK_END, w.VK_HOME, w.VK_LEFT, w.VK_UP, w.VK_RIGHT,
            w.VK_DOWN, w.VK_DELETE}
BOUNDARIES = set(" \n.,!?;:)")
MAX_BUFFER = 2000
VK_SNAPSHOT = 0x2C
WM_REINSTALL_HOOKS = w.WM_APP + 2
TRACE = False  # set by --trace; logs key codes, so never on by default
_TAIL_WORD = re.compile(r"([A-Za-z]+(?:'[A-Za-z]+)?)$")


class Engine:
    def __init__(self, config, overlay, model):
        self.config = config
        self.overlay = overlay
        self.model = model
        self.autocorrect = None  # set once the dictionary has loaded
        self.caret = CaretLocator()

        self.buffer = ""
        self.seq = 0
        self.ghost = None
        self.last_fix = None
        self.fg = None
        self.focus = None
        self.exe = ""
        self.excluded = False
        self.secure = False
        self.last_click = None
        self.caps = bool(w.GetKeyState(w.VK_CAPITAL) & 1)
        self._swallow_up = set()
        self._hooks = []
        self.ui_thread = None
        self.last_event = 0
        self.stats = {"accepted": 0, "fixed": 0}
        self.worker = Worker(self)
        self.injector = Injector()
        self.injector.gap = max(0, float(config["type_delay_ms"] or 0)) / 1000
        overlay.on_show = self._on_overlay_show

    # ------------------------------------------------------------- setup
    def install(self):
        """Call on the UI thread (it must pump messages)."""
        # Warm up COM/UI Automation first: importing those big modules holds Python's
        # GIL long enough that Windows would time out (and drop) our hooks.
        self.worker.start()
        self.worker.ready.wait(15)
        self.injector.start()
        self._kb_proc = w.HOOKPROC(self._kb_hook)
        self._ms_proc = w.HOOKPROC(self._mouse_hook)
        self._hook()
        threading.Thread(target=self._watchdog, name="hook-watchdog", daemon=True).start()

    def _hook(self):
        hmod = w.GetModuleHandleW(None)
        self._hooks = [w.SetWindowsHookExW(w.WH_KEYBOARD_LL, self._kb_proc, hmod, 0),
                       w.SetWindowsHookExW(w.WH_MOUSE_LL, self._ms_proc, hmod, 0)]
        self.last_event = w.GetTickCount()
        if not all(self._hooks):
            raise OSError(ctypes.get_last_error(), "SetWindowsHookEx failed")

    def reinstall(self):
        """UI thread. Windows silently removes a low-level hook that once answered too slowly."""
        log.warning("input hooks went quiet; reinstalling")
        self.uninstall()
        self._hook()

    def _watchdog(self):
        while True:
            time.sleep(2)
            gap = (w.last_input_tick() - self.last_event) & 0xFFFFFFFF
            if 1500 < gap < 0x7FFFFFFF and self.ui_thread:
                self.last_event = w.GetTickCount()
                w.PostThreadMessageW(self.ui_thread, WM_REINSTALL_HOOKS, 0, 0)

    def uninstall(self):
        for h in self._hooks:
            if h:
                w.UnhookWindowsHookEx(h)
        self._hooks = []

    @property
    def active(self):
        return self.config["enabled"] and not self.excluded

    # ------------------------------------------------------------- state helpers
    def reset(self):
        self.buffer = ""
        self.seq += 1
        self.last_fix = None
        self.clear_ghost()

    def clear_ghost(self):
        if self.ghost is not None or self.overlay.visible:
            self.ghost = None
            self.overlay.hide_now()

    def _changed(self, schedule=True):
        if len(self.buffer) > MAX_BUFFER:
            self.buffer = self.buffer[-MAX_BUFFER // 2:]
        self.seq += 1
        if schedule:
            self.worker.schedule("complete", self.config["debounce_ms"] / 1000)

    def _on_overlay_show(self, seq, text):
        """UI thread: the worker produced a suggestion; show it only if nothing changed since."""
        if seq != self.seq or not self.active or self.secure:
            return False
        self.ghost = text
        return True

    def _check_focus(self):
        fg = w.GetForegroundWindow()
        gti = w.gui_thread_info(fg)
        focus = gti.hwndFocus if gti else None
        if fg != self.fg or focus != self.focus:
            changed_app = fg != self.fg
            self.fg, self.focus = fg, focus
            self.reset()
            if changed_app:
                self.exe = w.process_name(fg) if fg else ""
                self.excluded = self.config.is_excluded(self.exe) or fg == self.overlay.hwnd
            self.secure = False
            self.worker.schedule("secure", 0)

    def refresh_exclusion(self):
        self.excluded = self.config.is_excluded(self.exe)
        if not self.active:
            self.reset()

    # ------------------------------------------------------------- hooks
    def _kb_hook(self, code, wparam, lparam):
        self.last_event = w.GetTickCount()
        if code >= 0:
            k = w.KBDLLHOOKSTRUCT.from_address(lparam)
            if k.dwExtraInfo != w.GHOST_MAGIC:
                if self.injector.busy and k.dwExtraInfo != w.REPLAY_MAGIC:
                    # We're mid-way through typing a fix; hold this key and replay it after.
                    up = wparam in (w.WM_KEYUP, w.WM_SYSKEYUP)
                    self.injector.hold(k.vkCode, k.scanCode, up, bool(k.flags & w.LLKHF_EXTENDED))
                    return 1
                try:
                    if self._on_key(wparam, k):
                        return 1
                except Exception:
                    log.exception("key handler failed")
        return w.CallNextHookEx(None, code, wparam, lparam)

    def _mouse_hook(self, code, wparam, lparam):
        self.last_event = w.GetTickCount()
        if code >= 0 and wparam in (w.WM_LBUTTONDOWN, w.WM_RBUTTONDOWN, w.WM_MBUTTONDOWN, w.WM_MOUSEWHEEL):
            try:
                if wparam == w.WM_MOUSEWHEEL:
                    self.clear_ghost()
                else:
                    m = w.MSLLHOOKSTRUCT.from_address(lparam)
                    self.last_click = (m.pt.x, m.pt.y, time.monotonic())
                    self.reset()
                    self.worker.schedule("secure", 0.15)
            except Exception:
                log.exception("mouse handler failed")
        return w.CallNextHookEx(None, code, wparam, lparam)

    def _on_key(self, msg, k):
        """Return True to swallow the key."""
        vk = k.vkCode
        if msg in (w.WM_KEYUP, w.WM_SYSKEYUP):
            if vk in self._swallow_up:
                self._swallow_up.discard(vk)
                return True
            return False
        if vk == w.VK_CAPITAL:
            self.caps = not self.caps
            return False
        if vk in MODIFIERS:
            return False

        self._check_focus()
        if TRACE:
            log.debug("key %s active=%s busy=%s secure=%s", vk, self.active, self.injector.busy, self.secure)
        if not self.active:
            return False

        shift = w.key_down(w.VK_SHIFT)
        ctrl = w.key_down(w.VK_CONTROL)
        alt = w.key_down(w.VK_MENU)
        win = w.key_down(w.VK_LWIN) or w.key_down(w.VK_RWIN)
        altgr = ctrl and w.key_down(w.VK_RMENU)
        ghost = self.ghost

        # --- accept the suggestion
        if ghost and vk == w.VK_TAB and not (shift or ctrl or alt or win):
            self._accept(ghost)
            self._swallow_up.add(vk)
            return True
        if ghost and vk == w.VK_RIGHT and ctrl and not (shift or alt or win):
            m = re.match(r"\s*\S+", ghost)
            self._accept(m.group(0) if m else ghost)
            self._swallow_up.add(vk)
            return True
        if vk == w.VK_ESCAPE:
            self.clear_ghost()
            return False

        # --- Backspace right after an autocorrection undoes it
        if vk == w.VK_BACK and self.last_fix and not (ctrl or alt or win):
            if self._undo_fix():
                self._swallow_up.add(vk)
                return True

        fix, self.last_fix = self.last_fix, None

        if win or vk == VK_SNAPSHOT:
            return False  # Win+Shift+S, PrtScn, Win+V...: leave the suggestion on screen
        if (ctrl and not altgr) or alt:
            self.clear_ghost()
            if ctrl and vk == w.VK_BACK:
                self.buffer = re.sub(r"\S*\s*$", "", self.buffer)
                self._changed(schedule=False)
            elif ctrl and vk in (ord("V"), ord("X"), ord("Z"), ord("Y"), ord("A"), w.VK_RETURN, w.VK_DELETE):
                self.reset()
            return False

        if vk == w.VK_BACK:
            self.clear_ghost()
            self.buffer = self.buffer[:-1]
            self._changed()
            return False
        if vk in NAV_KEYS or vk == w.VK_TAB:
            self.reset()
            return False

        if vk == w.VK_RETURN:
            ch = "\n"
        elif vk == w.VK_PACKET:
            ch = chr(k.scanCode)
        else:
            ch = self._to_char(vk, k.scanCode, shift, altgr)
        if not ch:
            self.clear_ghost()
            return False

        if self.secure:
            log.debug("secure field: not buffering")
            return False

        # --- autocorrect the word that just ended
        if ch in BOUNDARIES and self.autocorrect and self.config["autocorrect"] \
                and not (ch == "\n" and shift):
            if self._try_fix(ch, vk):
                return True

        self._type_char(ch)
        return False

    # ------------------------------------------------------------- actions
    def _type_char(self, ch):
        self.buffer += ch
        ghost = self.ghost
        if ghost and ghost.startswith(ch) and len(ghost) > 1:
            self.ghost = ghost[1:]
            self._changed(schedule=False)
            self.worker.schedule("reposition", 0)
            return
        self.clear_ghost()
        self._changed()

    def _accept(self, text):
        self.overlay.hide_now()
        self.ghost = None
        self.injector.submit(text, 0)
        self.buffer += text
        self.stats["accepted"] += 1
        self._changed()

    def _try_fix(self, boundary, vk):
        m = _TAIL_WORD.search(self.buffer)
        if not m:
            log.debug("no word before boundary (buffer len %d)", len(self.buffer))
            return False
        word, before = m.group(1), self.buffer[:m.start()]
        # Leave URLs, emails, paths, handles and code-ish tokens alone.
        if before and before[-1] not in " \t\n(\"'[{":
            return False
        if not before.strip() and len(self.buffer) == len(word) and word[:1].isupper():
            sentence_start = False  # we don't know what's before; could be a name
        else:
            tail = before.rstrip()
            sentence_start = not tail or tail[-1] in ".!?\n"
        fix = self.autocorrect.correct(word, sentence_start=sentence_start)
        if not fix or fix == word:
            return False
        self.clear_ghost()
        self.injector.submit(fix + boundary, len(word))
        self.buffer = before + fix + boundary
        self.last_fix = (word, fix, boundary)
        self._swallow_up.add(vk)
        self.stats["fixed"] += 1
        log.info("autocorrected a word")
        self._changed()
        return True

    def _undo_fix(self):
        word, fix, boundary = self.last_fix
        self.last_fix = None
        if boundary == "\n" or not self.buffer.endswith(fix + boundary):
            return False
        self.clear_ghost()
        self.injector.submit(word + boundary, len(fix) + len(boundary))
        self.buffer = self.buffer[:-(len(fix) + len(boundary))] + word + boundary
        self.autocorrect.ignore(word)
        ignored = list(self.config["ignored_words"])
        if word.lower() not in (x.lower() for x in ignored):
            ignored.append(word)
            self.config["ignored_words"] = ignored
        self._changed()
        return True

    def _to_char(self, vk, scan, shift, altgr):
        state = (ctypes.c_ubyte * 256)()
        if shift:
            state[w.VK_SHIFT] = 0x80
        if self.caps:
            state[w.VK_CAPITAL] = 0x01
        if altgr:
            state[w.VK_CONTROL] = state[w.VK_MENU] = 0x80
        buf = ctypes.create_unicode_buffer(8)
        hkl = w.GetKeyboardLayout(w.GetWindowThreadProcessId(self.fg, None))
        n = w.ToUnicodeEx(vk, scan, state, buf, 8, 0x4, hkl)  # 0x4: don't touch dead-key state
        if n == 1 and (ord(buf[0]) >= 32):
            return buf[0]
        return None


class Worker(threading.Thread):
    """Debounced background jobs: 'complete', 'reposition', 'secure'."""

    def __init__(self, engine):
        super().__init__(name="ghost-worker", daemon=True)
        self.e = engine
        self.cv = threading.Condition()
        self.jobs = {}
        self.ready = threading.Event()

    def schedule(self, name, delay):
        with self.cv:
            self.jobs[name] = time.monotonic() + delay
            self.cv.notify()

    def run(self):
        try:
            self.e.caret._init()
            self.e.caret.locate()
        except Exception:
            log.exception("caret locator init failed")
        finally:
            self.ready.set()
        while True:
            with self.cv:
                while True:
                    now = time.monotonic()
                    due = [n for n, t in self.jobs.items() if t <= now]
                    if due:
                        for n in due:
                            del self.jobs[n]
                        break
                    timeout = min(self.jobs.values()) - now if self.jobs else None
                    self.cv.wait(timeout)
            for name in sorted(due, key=["secure", "reposition", "complete"].index):
                try:
                    getattr(self, "_" + name)()
                except Exception:
                    log.exception("worker job %s failed", name)

    def _secure(self):
        e = self.e
        secure = e.caret.is_password()
        if secure != e.secure:
            e.secure = secure
            if secure:
                e.buffer = ""
                e.overlay.hide()

    def _reposition(self):
        e = self.e
        seq, ghost = e.seq, e.ghost
        if not ghost:
            return
        if not self._place(ghost, seq):
            e.overlay.hide()

    def _place(self, text, seq):
        """Find the caret and show `text` there (inline, or as a pill below mid-line)."""
        e = self.e
        c = e.caret.locate()
        if seq != e.seq:
            return True
        if c:
            r = ctypes.wintypes.RECT()
            w.GetWindowRect(e.fg or w.GetForegroundWindow(), ctypes.byref(r))
            room = max(120, r.right - c.x - 12)
        if c and e.caret.text_follows_caret():
            # Mid-line: inline text would sit on top of the app's text; float it below instead.
            e.overlay.show(text, c.x, c.y + c.h + 3, max(18, c.h * 0.8), True, seq, room)
        elif c:
            e.overlay.show(text, c.x, c.y, c.h, False, seq, room)
        elif e.last_click and time.monotonic() - e.last_click[2] < 600:
            x, y, _ = e.last_click
            e.overlay.show(text, x + 4, y + 14, 22, True, seq)
        else:
            return False
        return True

    def _complete(self):
        e = self.e
        cfg = e.config
        if not (cfg["autocomplete"] and e.active and e.model.ready) or e.secure:
            return
        seq, buf = e.seq, e.buffer
        if len(buf.strip()) < cfg["min_context_chars"] or buf.endswith("\n"):
            return
        if e.caret.is_password():
            e.secure = True
            return
        context = buf
        if len(buf) < 200:  # borrow earlier text in the field when the app exposes it
            field = e.caret.field_text_before_caret(cfg["context_chars"])
            if field and field.endswith(buf[-min(len(buf), 30):]):
                context = field
        context = context[-cfg["context_chars"]:]
        if seq != e.seq:
            return
        suggestion = e.model.complete(context)
        if not suggestion or seq != e.seq:
            return
        self._place(suggestion, seq)


class Injector(threading.Thread):
    """Types fixes/completions from its own thread, pacing Backspaces so apps
    don't drop them. Keys the user presses meanwhile are held and replayed in order."""

    def __init__(self):
        super().__init__(name="ghost-injector", daemon=True)
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.busy = False
        self.held = []
        self.gap = 0.012  # seconds between injected keys (config: type_delay_ms)

    def submit(self, text, backspaces):
        with self.lock:
            self.busy = True
        self.q.put((text, backspaces))

    def hold(self, vk, scan, up, extended):
        with self.lock:
            self.held.append((vk, scan, up, extended))

    def run(self):
        while True:
            text, backspaces = self.q.get()
            try:
                w.send_paced(text, backspaces, self.gap, w.GetForegroundWindow())
            except Exception:
                log.exception("injection failed")
            while True:
                time.sleep(0.012)
                with self.lock:
                    if not self.q.empty():
                        break
                    held, self.held = self.held, []
                    if not held:
                        self.busy = False
                        break
                for ev in held:
                    w.replay_key(*ev)
                    time.sleep(self.gap / 2)
