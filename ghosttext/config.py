"""User settings, stored as JSON in %APPDATA%\\GhostText\\config.json."""
import json
import logging
import os
import sys
import threading
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GhostText"
CONFIG_PATH = APP_DIR / "config.json"
FROZEN = getattr(sys, "frozen", False)
log = logging.getLogger(__name__)
# Where bin\ and models\ live: next to GhostText.exe, or the source checkout.
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent

DEFAULTS = {
    "enabled": True,
    # Global shortcut that turns GhostText on/off.
    "hotkey": "ctrl+alt+g",
    "first_run_done": False,
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
    # Downloaded on first launch if models\ is empty.
    "model_url": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "server_exe": "",
    "server_port": 8768,
    "gpu_layers": 99,
    "context_chars": 600,
    # Pause between keys GhostText types. Win11 Notepad garbles faster input.
    "type_delay_ms": 12,
    # Confidence cut-offs (natural-log probabilities). Lower = longer, riskier suggestions.
    "min_token_logprob": -2.3,
    "min_total_logprob": -4.5,
}


class Config:
    def __init__(self):
        self._lock = threading.Lock()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                raise ValueError("config.json must hold a JSON object")
            self.data.update(saved)
        except FileNotFoundError:
            self.save()
        except OSError as e:  # e.g. locked by another program: keep the settings in use
            log.warning("could not read config.json (%s); settings unchanged", e)
        except ValueError as e:
            # A hand edit with a typo: keep the settings in use (the defaults at startup),
            # but don't lose the edit. The next setting change saves over config.json,
            # so move it aside first.
            bad = CONFIG_PATH.with_suffix(".json.bad")
            log.warning("config.json unreadable (%s); settings unchanged, kept it as %s", e, bad.name)
            try:
                os.replace(CONFIG_PATH, bad)
            except OSError:
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
