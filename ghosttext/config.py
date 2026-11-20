"""User settings, stored as JSON in %APPDATA%\\GhostText\\config.json."""
import json
import os
import threading
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GhostText"
CONFIG_PATH = APP_DIR / "config.json"
ROOT = Path(__file__).resolve().parent.parent  # the ghost-text folder

DEFAULTS = {
    "enabled": True,
    "autocomplete": True,
    "autocorrect": True,
    # Wait this long after the last keystroke before asking the model.
    "debounce_ms": 250,
    "max_words": 6,
    "min_context_chars": 4,
    "ghost_color": "#8a8a8a",
    "excluded_apps": [
        "WindowsTerminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
        "Code.exe", "devenv.exe", "KeePass.exe", "KeePassXC.exe", "1Password.exe",
        "Bitwarden.exe", "mstsc.exe", "LockApp.exe",
    ],
    # Words autocorrect must leave alone (you can add your own; undoing a fix adds it too).
    "ignored_words": [],
    # Model / llama.cpp server. Empty model_path = first .gguf in the models folder.
    "model_path": "",
    "server_exe": "",
    "server_port": 8768,
    "gpu_layers": 99,
    "context_chars": 600,
}


class Config:
    def __init__(self):
        self._lock = threading.Lock()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except FileNotFoundError:
            self.save()
        except Exception:
            pass

    def save(self):
        with self._lock:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, CONFIG_PATH)

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def is_excluded(self, exe):
        exe = (exe or "").lower()
        return any(exe == e.lower() for e in self["excluded_apps"])

    def model_path(self):
        if self["model_path"]:
            return Path(self["model_path"])
        found = sorted((ROOT / "models").glob("*.gguf"))
        return found[0] if found else None

    def server_exe(self):
        if self["server_exe"]:
            return Path(self["server_exe"])
        exe = ROOT / "bin" / "llama-server.exe"
        return exe if exe.exists() else None
