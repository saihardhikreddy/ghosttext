"""GhostText entry point: tray icon on the main thread, hooks + overlay on a UI thread."""
import sys

sys.coinit_flags = 0  # COM multithreaded apartment everywhere (UI Automation prefers MTA)

import ctypes  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import winreg  # noqa: E402
from ctypes import wintypes as wt  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

from . import win32 as w  # noqa: E402
from .config import APP_DIR, ROOT, Config  # noqa: E402

log = logging.getLogger("ghosttext")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def make_icon(size=64, paused=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    body = (120, 120, 120, 255) if paused else (124, 92, 255, 255)
    # A little ghost: round head, wavy hem.
    d.rounded_rectangle((10 * s, 6 * s, 54 * s, 58 * s), radius=22 * s, fill=body)
    for i in range(4):
        cx = (15.5 + i * 11) * s
        d.ellipse((cx - 5.5 * s, 50 * s, cx + 5.5 * s, 62 * s), fill=(0, 0, 0, 0))
    d.ellipse((21 * s, 22 * s, 29 * s, 32 * s), fill="white")
    d.ellipse((35 * s, 22 * s, 43 * s, 32 * s), fill="white")
    d.ellipse((24 * s, 25 * s, 28 * s, 31 * s), fill=(30, 30, 40, 255))
    d.ellipse((38 * s, 25 * s, 42 * s, 31 * s), fill=(30, 30, 40, 255))
    return img


def autostart_command():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw}" "{ROOT / "GhostText.pyw"}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "GhostText")
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "GhostText", 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, "GhostText")
            except OSError:
                pass


class App:
    def __init__(self):
        from .completer import LocalModel
        from .engine import Engine
        from .overlay import Overlay

        self.config = Config()
        self.overlay = Overlay(self.config["ghost_color"])
        self.model = LocalModel(self.config)
        self.engine = Engine(self.config, self.overlay, self.model)
        self.ui_thread_id = None
        self.icon = None
        self._ui_ready = threading.Event()

    # ------------------------------------------------------------ threads
    def _ui_loop(self):
        self.ui_thread_id = w.GetCurrentThreadId()
        self.engine.ui_thread = self.ui_thread_id
        from .engine import WM_REINSTALL_HOOKS
        try:
            self.overlay.create()
            self.engine.install()
        finally:
            self._ui_ready.set()
        msg = wt.MSG()
        while w.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_REINSTALL_HOOKS and not msg.hwnd:
                self.engine.reinstall()
                continue
            w.TranslateMessage(ctypes.byref(msg))
            w.DispatchMessageW(ctypes.byref(msg))
        self.engine.uninstall()

    def _load_dictionary(self):
        from .autocorrect import AutoCorrect
        try:
            self.engine.autocorrect = AutoCorrect(self.config["ignored_words"])
            log.info("autocorrect dictionary loaded")
        except Exception:
            log.exception("autocorrect unavailable")

    def run(self):
        import pystray
        from pystray import Menu, MenuItem as Item

        threading.Thread(target=self._ui_loop, name="ui", daemon=True).start()
        threading.Thread(target=self._load_dictionary, name="dict", daemon=True).start()
        self.model.start()
        self._ui_ready.wait(5)

        cfg = self.config

        def toggle(key):
            def f(icon, item):
                cfg[key] = not cfg[key]
                if key == "enabled":
                    icon.icon = make_icon(paused=not cfg["enabled"])
                self.engine.refresh_exclusion()
            return f

        def last_app():
            return self.engine.exe or "this app"

        def toggle_app(icon, item):
            exe = self.engine.exe
            if not exe:
                return
            apps = list(cfg["excluded_apps"])
            if cfg.is_excluded(exe):
                apps = [a for a in apps if a.lower() != exe.lower()]
            else:
                apps.append(exe)
            cfg["excluded_apps"] = apps
            self.engine.refresh_exclusion()

        def status_text(item):
            s = self.engine.stats
            return f"Model: {self.model.status}  ·  {s['accepted']} accepted, {s['fixed']} fixed"

        def open_settings(icon, item):
            os.startfile(str(APP_DIR / "config.json"))

        def reload_settings(icon, item):
            cfg.load()
            self.overlay.color = cfg["ghost_color"]
            if self.engine.autocorrect:
                self.engine.autocorrect.ignored = {x.lower() for x in cfg["ignored_words"]}
            self.engine.refresh_exclusion()

        def quit_(icon, item):
            icon.stop()

        menu = Menu(
            Item(status_text, None, enabled=False),
            Menu.SEPARATOR,
            Item("Enabled", toggle("enabled"), checked=lambda i: cfg["enabled"], default=True),
            Item("Autocomplete (Tab to accept)", toggle("autocomplete"), checked=lambda i: cfg["autocomplete"]),
            Item("Autocorrect typos", toggle("autocorrect"), checked=lambda i: cfg["autocorrect"]),
            Item(lambda i: f"Turn off in {last_app()}", toggle_app,
                 checked=lambda i: cfg.is_excluded(self.engine.exe)),
            Menu.SEPARATOR,
            Item("Start with Windows", lambda i, it: set_autostart(not autostart_enabled()),
                 checked=lambda i: autostart_enabled()),
            Item("Open settings file", open_settings),
            Item("Reload settings", reload_settings),
            Item("Quit GhostText", quit_),
        )
        self.icon = pystray.Icon("GhostText", make_icon(paused=not cfg["enabled"]),
                                 "GhostText: offline autocomplete", menu)
        try:
            self.icon.run()
        finally:
            self.shutdown()

    def shutdown(self):
        if self.ui_thread_id:
            w.PostThreadMessageW(self.ui_thread_id, w.WM_QUIT, 0, 0)
        self.model.stop()


def main():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=APP_DIR / "ghosttext.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("comtypes").setLevel(logging.WARNING)
    if "--debug" in sys.argv:
        logging.getLogger().addHandler(logging.StreamHandler())
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("comtypes").setLevel(logging.WARNING)
    if "--trace" in sys.argv:
        from . import engine
        engine.TRACE = True
    w.set_dpi_aware()
    mutex = w.single_instance()
    if mutex is None:
        ctypes.windll.user32.MessageBoxW(None, "GhostText is already running (see the tray).",
                                         "GhostText", 0x40)
        return
    App().run()


if __name__ == "__main__":
    main()
