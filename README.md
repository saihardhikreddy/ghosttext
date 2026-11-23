<div align="center">

<img src="ghosttext.ico" width="72" alt="GhostText icon">

# GhostText

**Copilot-style autocomplete and autocorrect for every Windows app, 100% offline.**

Pause while typing and a grey suggestion appears at your cursor. Press <kbd>Tab</kbd>.
Typos fix themselves as you finish each word. A small local AI model does the work, so
nothing you type ever leaves your PC.

[![Release](https://img.shields.io/github/v/release/saihardhikreddy/ghosttext?label=download&color=7c5cff)](https://github.com/saihardhikreddy/ghosttext/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/saihardhikreddy/ghosttext/total?color=7c5cff)](https://github.com/saihardhikreddy/ghosttext/releases)
[![CI](https://github.com/saihardhikreddy/ghosttext/actions/workflows/ci.yml/badge.svg)](https://github.com/saihardhikreddy/ghosttext/actions/workflows/ci.yml)
![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows)
![Offline](https://img.shields.io/badge/runs-100%25%20offline-2ea44f)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

<img src="docs/demo.gif" alt="GhostText fixing typos and suggesting the rest of the sentence" width="760">

</div>

## Features

- **Ghost text everywhere.** Suggestions appear right after the caret in Notepad, Chrome,
  Edge and other apps that report where the caret is (Win32, browsers, Electron, UI Automation). <kbd>Tab</kbd> accepts,
  <kbd>Ctrl</kbd>+<kbd>→</kbd> takes one word, and <kbd>Esc</kbd> (or just typing on) dismisses it.
- **Autocorrect as you type.** `teh` → `the`, `dont` → `don't`, `wwter` → `water`.
  Only fixes things that look like a slip of the finger, so lowercase names like *priya*
  or *reddy* are left alone. Pressed <kbd>Backspace</kbd> right after a fix? It's undone, and
  GhostText remembers that word.
- **Private by design.** A 1.5B-parameter model (Qwen2.5, 4-bit) runs through llama.cpp on
  `127.0.0.1`. No account, no cloud, no telemetry, and it works on a plane.
- **Fast.** About 0.2 s per suggestion on a laptop GPU (Vulkan), and it falls back to the CPU.
- **Only suggests when it's sure.** Suggestions stop where the model's confidence drops,
  so you get "week." instead of a made-up paragraph.
- **Stays out of the way.** No window, just a tray icon. It starts with Windows, and
  <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>G</kbd> turns it on or off. It skips password fields,
  and terminals, code editors and password managers are off by default.

## Download

1. Download **`GhostText-<version>-win64.zip`** from the
   [latest release](https://github.com/saihardhikreddy/ghosttext/releases/latest).
2. Unzip it anywhere, for example `%LOCALAPPDATA%\Programs\GhostText`.
3. Run **`GhostText.exe`**. The exe isn't code-signed yet, so if Windows SmartScreen
   warns you, click **More info → Run anyway**.

The ghost icon appears in the tray. On first launch GhostText downloads its ~1 GB model
once (autocorrect works meanwhile, and the tray menu shows progress). After that it starts
with Windows.

| Shortcut | Does |
| --- | --- |
| <kbd>Tab</kbd> | Accept the suggestion |
| <kbd>Ctrl</kbd>+<kbd>→</kbd> | Accept the next word |
| <kbd>Esc</kbd> | Dismiss |
| <kbd>Backspace</kbd> right after a fix | Undo the autocorrection and remember the word |
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>G</kbd> | Turn GhostText on/off (falls back to <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> if taken) |

## How it compares

| | GhostText | Cotypist | Grammarly | Windows text suggestions | Copilot in Word/Outlook |
| --- | :---: | :---: | :---: | :---: | :---: |
| Works in every app | ✅ | ✅ | Most apps | ✅ | Word & Outlook only |
| Inline AI sentence completion | ✅ | ✅ | ❌ | Single words | ✅ |
| Autocorrect while typing | ✅ | ❌ | ✅ | ✅ | ✅ |
| Runs offline, text stays on device | ✅ | ✅ | ❌ | ✅ | ❌ |
| Windows | ✅ | ❌ (macOS) | ✅ | ✅ | ✅ |
| Free and open source | ✅ | ❌ | ❌ | ❌ | ❌ |

## Privacy

- The model runs locally, and the server listens on `127.0.0.1` only.
- What you type lives only in memory (a rolling buffer of about 2,000 characters). It's
  never written to disk or to logs; `%APPDATA%\GhostText\ghosttext.log` records status only.
- Password fields are skipped (Win32 `ES_PASSWORD` and UI Automation `IsPassword`).
- The only network request GhostText makes is the one-time model download from Hugging Face.

## How it works

```
 keyboard ──► low-level hook ──► typed-text buffer ──► autocorrect (SymSpell + keyboard-slip rules)
                    │                    │
                    │                    └──► pause 250 ms ──► llama.cpp (local) ──► confident part only
                    ▼                                                                      │
             Tab / Ctrl+→ ◄── click-through overlay at the caret ◄── caret finder ◄────────┘
                               (Win32 caret → MSAA → UI Automation)
```

| Piece | File | What it does |
| --- | --- | --- |
| Keyboard/mouse hook | `ghosttext/engine.py` | Low-level hooks keep a short in-memory buffer of what you typed in the focused field. It resets on clicks, arrow keys and window switches. |
| Autocorrect | `ghosttext/autocorrect.py` | A list of common slips, plus SymSpell over an 82k-word dictionary, filtered to edits a finger could make on QWERTY. Leaves names, acronyms, camelCase, URLs and paths alone. |
| Caret finder | `ghosttext/caret.py` | Tries the Win32 caret, then MSAA (Chrome, Edge, Electron), then UI Automation (Word, modern apps). Also detects password fields. |
| Overlay | `ghosttext/overlay.py` | A click-through, never-focused, per-pixel-alpha window. Inline at the end of a line, a small pill below the line mid-sentence. |
| Model | `ghosttext/completer.py` | Runs `llama-server` privately. Uses token healing (a grammar-forced prefix) for half-typed words, then keeps only the high-probability part. |
| Typing | `ghosttext/engine.py` (`Injector`) | Types with `SendInput`, one key at a time (Win11 Notepad garbles batched input), and replays keys you press meanwhile, in order. |

## Settings

Tray → **Open settings file** (`%APPDATA%\GhostText\config.json`), then **Reload settings**.
If the file isn't valid JSON (a trailing comma is the usual slip), GhostText keeps the settings it has, renames your file to `config.json.bad` so it isn't overwritten, and says so in the log. Fix it and save it back as `config.json`.

| Key | Default | Meaning |
| --- | --- | --- |
| `hotkey` | `ctrl+alt+g` | On/off shortcut |
| `debounce_ms` | `250` | Pause after your last keystroke before asking the model |
| `max_words` | `6` | Longest suggestion |
| `min_token_logprob` / `min_total_logprob` | `-2.3` / `-4.5` | Confidence cut-offs; lower means longer, riskier suggestions |
| `excluded_apps` | terminals, code editors, password managers | Process names GhostText ignores (or use the tray's "Turn off in …") |
| `ignored_words` | `[]` | Words autocorrect never touches (undoing a fix adds to this) |
| `model_path` / `model_url` | Qwen2.5-1.5B-Instruct Q4_K_M | Any GGUF model works; small ones (0.5B–3B) feel instant |
| `gpu_layers` | `99` | Set to `0` to run on the CPU |
| `type_delay_ms` | `12` | Pause between keys GhostText types |

## Limits

- Apps running as administrator can't receive input from a normal-privilege app (Windows UIPI).
- Some apps don't report their caret (certain games, Java and Qt apps). There you get
  autocorrect but no ghost text.
- Context is what you typed since your last click or window switch, plus the text before the
  caret in that field when the app exposes it through UI Automation.
- English only for now.

## Build from source

Needs Python 3.11+ on Windows 10/11.

```powershell
git clone https://github.com/saihardhikreddy/ghosttext && cd ghosttext
powershell -ExecutionPolicy Bypass -File setup.ps1     # venv + llama.cpp (~40 MB) + model (~1 GB)
.\GhostText.vbs                                        # run from source, in the tray
powershell -ExecutionPolicy Bypass -File build.ps1     # -> dist\GhostText\GhostText.exe
powershell -ExecutionPolicy Bypass -File install.ps1   # -> %LOCALAPPDATA%\Programs\GhostText + Start menu
powershell -ExecutionPolicy Bypass -File release.ps1   # -> dist\GhostText-<version>-win64.zip
```

Run `python -m ghosttext --debug` from the venv to see status logs in a console.

### Tests

```powershell
.\.venv\Scripts\python tests\test_engine.py                   # typing logic, autocorrect, trimming (runs in CI)
.\.venv\Scripts\python tests\e2e_harness.py --accept --undo   # live, in a throwaway window
.\.venv\Scripts\python tests\e2e_browser.py                   # live, in a throwaway Edge profile
.\.venv\Scripts\python tests\demo_gif.py                      # re-records docs/demo.gif
```

## Roadmap

- [ ] Signed installer (no SmartScreen prompt)
- [ ] More languages for autocorrect
- [ ] Per-app tone (casual for chat, formal for email)
- [ ] Learn your own phrases, locally

Ideas and bug reports are welcome in [Issues](https://github.com/saihardhikreddy/ghosttext/issues).

## License

[MIT](LICENSE). The bundled model (Qwen2.5) is Apache-2.0, and llama.cpp is MIT.
