# GhostText

Copilot-style autocomplete and autocorrect for **every Windows app**, running fully
offline on your own PC. Nothing you type leaves the machine.

- **Ghost text:** pause while typing and a grey suggestion appears right after the caret.
  `Tab` accepts it, `Ctrl+→` accepts one word, `Esc` or just keep typing to ignore it.
- **Autocorrect:** common typos are fixed when you finish a word (`teh ` → `the `,
  `dont ` → `don't `, `i ` → `I `). Pressed `Backspace` right after a fix? It's undone
  and GhostText remembers to leave that word alone.
- **Local model:** a 1.5B-parameter model (Qwen2.5-1.5B-Instruct, Q4) served by
  llama.cpp on `127.0.0.1` only, on the GPU via Vulkan (falls back to CPU).
- **Tray icon:** turn it on/off, toggle autocomplete or autocorrect, turn it off for the
  current app, start with Windows.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1   # venv + llama.cpp (~40 MB) + model (~1 GB)
.\GhostText.vbs                                      # starts in the tray, no window (or double-click GhostText.lnk)
```

### Install as an app (GhostText.exe)

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1     # PyInstaller -> dist\GhostText\GhostText.exe
powershell -ExecutionPolicy Bypass -File install.ps1   # -> %LOCALAPPDATA%\Programs\GhostText + Start menu
```

The installed app has no window: it lives in the tray, starts with Windows (set on first
launch, toggle in the tray), and **Ctrl+Alt+G** turns it on/off (falls back to
Ctrl+Shift+G if another app owns that shortcut; the tray menu shows which).

Needs Python 3.11+ on Windows 10/11 to build. The first start takes a few seconds while the
model loads; the tray menu's first line shows the model status.

Run `python -m ghosttext --debug` from the venv to see status logs in a console.

## How it works

| Piece | File | What it does |
| --- | --- | --- |
| Keyboard/mouse hook | `ghosttext/engine.py` | Low-level hooks keep a short in-memory buffer of what you typed in the focused field; reset on clicks, arrow keys and window switches. |
| Autocorrect | `ghosttext/autocorrect.py` | Hand-made list of common slips plus SymSpell (edit distance) over an 82k-word dictionary. Only fixes when one candidate clearly wins; leaves names, acronyms, camelCase, URLs and paths alone. |
| Caret finder | `ghosttext/caret.py` | Win32 caret, then MSAA (Chrome/Edge/Electron), then UI Automation (Word, modern apps). Also detects password fields. |
| Overlay | `ghosttext/overlay.py` | A click-through, never-focused, per-pixel-alpha window that draws the suggestion. |
| Model | `ghosttext/completer.py` | Starts `bin\llama-server.exe` privately and trims its output to a short, whole-word suggestion. |
| Typing | `ghosttext/engine.py` (`Injector`) | Types fixes/completions with `SendInput`, pacing Backspaces (some apps drop batched ones) and replaying keys you press meanwhile, in order. |

## Privacy

- The model runs locally; the server listens on `127.0.0.1` only.
- Typed text lives only in memory (a rolling buffer of ~2,000 characters) and is never
  written to disk or logs. The log file (`%APPDATA%\GhostText\ghosttext.log`) records
  status only.
- Password fields are skipped (Win32 `ES_PASSWORD` and UI Automation `IsPassword`).
- Terminals, VS Code, Visual Studio, password managers and Remote Desktop are excluded by
  default; edit `excluded_apps` in settings.

## Settings

Tray → **Open settings file** (`%APPDATA%\GhostText\config.json`), then **Reload settings**.

| Key | Default | Meaning |
| --- | --- | --- |
| `debounce_ms` | 250 | Pause after your last keystroke before asking the model |
| `max_words` | 6 | Longest suggestion |
| `excluded_apps` | terminals, editors, password managers | Process names GhostText ignores |
| `ignored_words` | `[]` | Words autocorrect never touches (undoing a fix adds to this) |
| `model_path` | first `.gguf` in `models\` | Any GGUF model works; small ones (0.5B–3B) feel instant |
| `gpu_layers` | 99 | Set to 0 to run on CPU |

## Limits

- Apps running as administrator can't be hooked from a normal-privilege app (Windows UIPI).
- Some apps don't report their caret (certain games, Java and Qt apps); there you get
  autocorrect but no ghost text.
- Context is what you typed since you last clicked or switched windows, plus, where the
  app exposes it through UI Automation, the text before the caret in that field.

## Tests

```powershell
.\.venv\Scripts\python tests\test_engine.py      # typing logic, autocorrect, trimming
.\.venv\Scripts\python tests\e2e_harness.py --accept --undo   # live, in a throwaway window
.\.venv\Scripts\python tests\e2e_browser.py                   # live, in a throwaway Edge profile
```
