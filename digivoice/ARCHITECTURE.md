# digivoice architecture

Local CLI package at `digivoice/`. No network service and no port. Python 3.12. Console script `digivoice` and `python -m digivoice`.

## Layout

| Path | Role |
| --- | --- |
| `src/digivoice/cli.py` | Argv dispatch and process entry. |
| `src/digivoice/doctor.py` | Host checks and the text report. |
| `src/digivoice/paths.py` | Data, models, recordings, and history locations. Default model id. |
| `src/digivoice/probe.py` | `PATH` lookup and file checks. No shell. |
| `src/digivoice/runner.py` | `CommandRunner` protocol, the real `subprocess.run` runner, stderr tails. |
| `src/digivoice/capture.py` | Microphone to wav. `sox` first, then `ffmpeg`. Toggle early-stop via stop-file / signals. |
| `src/digivoice/transcribe.py` | `whisper-cli` over a wav, transcript cleanup. |
| `src/digivoice/speak.py` | Piper synthesis + local player (`afplay` / `aplay` / `ffplay`). |
| `src/digivoice/history.py` | JSONL append, tolerant read, `--last` / `--grep` / `--copy-last` / `--json`. |
| `src/digivoice/settings.py` | `settings.json` under the data dir; agent-scriptable get/set. |
| `src/digivoice/menu_tree.py` | TTY `/settings` path. Enter opens a folder or a list. A model list shows size and the recommended row. A file already on disk is marked downloaded. The numbered menu still asks before it fetches a missing speech or rewrite file. Each row is a bold name, a bracketed value, and a gray explanation. |
| `src/digivoice/setup.py` | TTY opens the `/settings` path. Pipes keep the numbered wizard. `--print` overview and `recommend_models()` hardware stub (#4939 hook). |
| `src/digivoice/tui.py` | Shared menu blocks and the non-TTY numbered prompts. |
| `src/digivoice/opentui.py` | Replaces a TTY process with the OpenTUI app. |
| `src/digivoice/tui_bridge.py` | Local JSON screen model the OpenTUI process calls. No network. |
| `tui/` | OpenTUI (`@opentui/core`) app: `createCliRenderer`, boxes, and text. |
| `src/digivoice/pixel_hero.py` | 7×10 DIGIVOICE glyph map. The home header paints those glyphs as five half-block rows in `tui.py`. |
| `src/digivoice/catalog.py` | Suggested local STT ggml, Piper voice, and rewrite GGUF list. A download writes a `.partial` sibling and replaces the real file only after every piece is on disk. |
| `src/digivoice/install.py` | `digivoice install` and `digivoice update`: bun, OpenTUI, whisper-cli, Piper, sox, the default local models, and the Hammerspoon adapter at `~/.hammerspoon/digivoice`. Fetch and runner are injected. No cloud STT/TTS. |
| `src/digivoice/installed_models.py` | Local GGUF and whisper files already installed by LM Studio, Ollama, and MLX Studio. |
| `src/digivoice/home.py` | Bare-`digivoice` home: OpenTUI on a TTY, printed overview otherwise. |
| `src/digivoice/panels.py` | TTY doctor (green ok, red not ok, ready line at the bottom), history browser, and the system pane (reload, reset, restart, update, logs). |
| `src/digivoice/reload.py` | `reload`: CLI path, settings, Lua adapter tip, bounded Hammerspoon reload; clears stale status on failure. |
| `src/digivoice/rewrite.py` | Optional local post-STT rewrite (ollama / llama.cpp). llama-cli runs one turn and the banner is stripped. Fail soft. |
| `src/digivoice/paste.py` | Clipboard plus Command-V into the focused app. Fails soft. Never pastes blank text. |
| `src/digivoice/status.py` | `status.json` feed for the banner, cancel-file token, `CANCELLED_EXIT`. Fails soft. |
| `src/digivoice/errors.py` | `VoiceError` and the capture / transcribe / speak subclasses. |
| `src/digivoice/models.py` | Pydantic v2 models including `RewriteResult` and path/doctor/history types. |
| `hammerspoon/` | Sample hotkey adapter (`init.lua`), status banner logic (`banner_core.lua`, pure Lua), background-only (no Dock/menubar/toast), TCC runbook. |

Every external binary — `sox`, `ffmpeg`, `whisper-cli`, `piper`, `afplay`/`aplay`/`ffplay`, `pbcopy`, `osascript` — is reached
through a `CommandRunner` (argv list, never `shell=True`), except toggle early-stop capture which uses
`subprocess.Popen` so a stop-file or signal can finalize the wav. `Runtime.runner` is the injection
point: `None` / `run_command` means the real runner; tests pass a fake so no test needs a microphone,
sound card, model, or clipboard.

## Terminal UI

A TTY does not draw the Python alternate screen. `opentui.py` replaces the process with `bun digivoice/tui/src/main.js` (the OpenTUI quickstart runtime; `DIGIVOICE_NODE` can point at another binary). That file follows the quickstart: `createCliRenderer` from `@opentui/core`, then `BoxRenderable` and `TextRenderable`. The half-block DIGIVOICE wordmark (block V, letter gap 2, rest cube gray 102 and brighter cube 231, or the matching `38;2` RGB only when `COLORTERM` is `truecolor` or `24bit`) is a fixed six-row slot. On a tall window that slot rests about one third of the way down, between one quarter and one third from the top. The menu does not move it. A short window shifts the slot up, and a small window can put it at the top. The slot stays fixed while the page scrolls. The face is still those five rows. Every letter cube rests in a subdued gray. A level rises and falls inside each column, out of step with the others, and a cube turns bright only while that level reaches it from the bottom of the glyph upward. Cubes above the level stay gray. Gaps and the space above a letter stay dark. A dark-gray copy sits one cell down and one cell right and does not animate. The face stays opaque. Under it is a gap, then one status row, then the page, a gap, and the footer `↑↓ move · enter select · esc back · click` at the bottom. The status row is one line: a quiet rule, the selected model, the settings that are on, and the doctor summary. OK is green. A problem uses the existing red. Info stays plain. The row is not a slash path and it is not a menu item. When the page does not fit, that region scrolls. The wordmark and the status row stay on screen. History, logs, and doctor stay in the page and do not move the hero. Home header is `/digivoice`; the rows are `/history`, `/settings`, `/system`, and `/quit`. The current path has a one-cell left rule and a quiet row background. Other rows keep that cell blank, so the path text does not shift. Hover paints the same bar. A click is mouse up and runs the same action as Enter. Gray text on that same row is only the value or status, and a long value ellipsizes in the middle on one line. The page fades in on a path change. The wordmark does not. Settings header is the screen path (`/settings`, `/settings/speech`). The frame is a fixed width, centered in the terminal, so the wordmark stays centered and does not jump when the menu changes. The page is left-aligned in that frame and sits above the footer. A hotkey row shows an input only while capturing. The moment the placeholder `input new hotkey` is showing, digivoice writes `hotkey.capture` and its own hotkeys stop. The event tap passes that key through to the terminal, so Option, Command, and the other binds do not start dictation, speak, cancel, or the banner. Enter, Esc, or leaving the field removes the flag and arms the hotkeys again. Focus shows the cursor. Enter is the only save. Blur does not write. A physical Option press fills it with Left Option or Right Option (Right Option when the event does not say which side). The words `option` and `alt` are Right Option. Enter locks the binding into `hotkey_bindings`, reloads Hammerspoon the same way System Reload does, and returns to that row. Esc cancels and keeps the previous binding. A name that is not a key keeps that binding, warns, and is not written. A binding another role already uses is refused the same way: `settings.json` is not written, and the pane names that role. Saving the role's current binding is still allowed. Leaving `/settings` or any child writes `settings.json` before the screen changes. System header is `/system`; the rows are `/doctor`, `/reload`, `/reset`, `/restart`, `/update`, and `/logs`. History header is `/digivoice/history`. The takes sit in a scroll box stuck to the newest line; scrolling up pauses that pin until the bottom is visible again. The timestamp is the path, the transcript is gray on that row and stays selectable, and there is no copy button on the list. Enter shows the full text, Copy confirms on screen, and Delete returns to the list. Logs header is `/system/logs`: one line each, Enter shows the full line and any metadata, and an empty log is not a selectable row. Doctor is the word `doctor`: a short name, a few words, and a status. OK is green. Info stays plain. Reload, reset, restart, and update paint a loading state in the page first. Reload ends on a done line. Reset returns home. Restart re-execs the process. Update shows progress in the page, then restarts when the refresh did not fail. Esc on home exits 0 and leaves Hammerspoon running. `SIGHUP` does the same. Quit is the action that stops Hammerspoon. A click runs the same action as Enter, including a settings choice. Speech, voice, and rewrite model lists mark a file on disk with ↓ at the right edge of the row. The path stays left-aligned. `auto` is selectable and has no arrow. Choosing a model that is not on disk opens a download page in the pane: the model name, a progress bar, and a percentage that advances while bytes arrive. The hero and the footer stay. Success returns to that list on the same row, now with ↓. Failure stays on the page with the error and does not mark the model downloaded. Esc returns to the list and deletes only the partial. Choosing a model already on disk selects it and stays on that row. Other choices still return to the parent, which stays on the opened row. The OpenTUI process reads screens from `python -m digivoice.tui_bridge` (stdin JSON, no socket). A download is that same process, one JSON object per line. Pipes and agents stay on the Python CLI. The OpenTUI check is `npm test` in `digivoice/tui`, which runs `bun test` and `createTestRenderer` from `@opentui/core/testing`.

## Data locations

macOS defaults:

- models: `~/Library/Application Support/digivoice/models/`
- recordings: `~/Library/Application Support/digivoice/recordings/`
- history: `~/Library/Application Support/digivoice/history.jsonl`
- toggle stop-file: `~/Library/Application Support/digivoice/dict.stop`
- cancel-file: `~/Library/Application Support/digivoice/dict.cancel`
- banner status feed: `~/Library/Application Support/digivoice/status.json`
- banner spawn flag: `~/Library/Application Support/digivoice/banner.show`
- banner drag position: `~/Library/Application Support/digivoice/banner_pos.json`
- settings: `~/Library/Application Support/digivoice/settings.json`
- default model file: `~/Library/Application Support/digivoice/models/ggml-base.en.bin`

Linux fallback (also what `doctor` prints when reporting the other platform):

- models: `${XDG_DATA_HOME:-~/.local/share}/digivoice/models/`
- recordings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/recordings/`
- history: `${XDG_DATA_HOME:-~/.local/share}/digivoice/history.jsonl`
- toggle stop-file: `${XDG_DATA_HOME:-~/.local/share}/digivoice/dict.stop`
- cancel-file: `${XDG_DATA_HOME:-~/.local/share}/digivoice/dict.cancel`
- banner status feed: `${XDG_DATA_HOME:-~/.local/share}/digivoice/status.json`
- banner spawn flag: `${XDG_DATA_HOME:-~/.local/share}/digivoice/banner.show`
- banner drag position: `${XDG_DATA_HOME:-~/.local/share}/digivoice/banner_pos.json`
- settings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/settings.json`
- same filename: `ggml-base.en.bin`

`DIGIVOICE_DATA_DIR` overrides the data directory on every platform. `DIGIVOICE_PIPER_VOICE`
points at a Piper `.onnx` voice; otherwise `speak` uses the first `*.onnx` under the models
directory. `doctor` does not create directories; `dict`, `speak`, and `history` do, because those
commands write.

`ggml-base.en` is the snappy push-to-talk default. whisper.cpp ships that model as
`ggml-base.en.bin`.

## CLI

| Command | Exit | Behavior |
| --- | --- | --- |
| `doctor` | 0 ready, 1 not ready | Report below. A TTY opens the doctor screen. `digivoice /doctor` is the same command. |
| `dict [--hold\|--toggle] [--seconds N] [--stop-file PATH] [--cancel-file PATH] [--no-paste] [--no-rewrite]` | 0 dictated, 1 capture / transcribe failed or nothing recognized, 3 cancelled | Record, transcribe, optional rewrite, append, paste. |
| `speak [text\|--clipboard\|--selection\|--clipboard-or-history]` | 0 spoken, 1 Piper/player/source failed | Piper playback; append `kind:speak`. |
| `history [--last N] [--grep PATTERN] [--copy-last] [--json]` | 0 (1 if copy-last empty) | Lists / copies last dict. A TTY with no flags opens the history pages. |
| `cancel [--cancel-file PATH]` | 0 | Create the cancel-file; a running `dict` discards its take. |
| `status` | 0 shown, 1 none yet | Print the `status.json` the banner reads. |
| `banner show [--text T]` / `hide` / `toggle` | 0 | Write the `banner.show` spawn flag the adapter polls; shows a preview without dictation. |
| `settings` / `setup` [`get`/`set`/`path`] [`--json`] | 0 / 2 | `settings` shows or changes settings.json. `setup` on a TTY opens the `/settings` path (speech, rewrite, banner, hotkeys). Enter opens a folder or a chooser. It does not toggle or cycle in place. On/off, pin, position, animations, style, model, and voice each open a list; the value is saved only when that row is picked. After a choice or cancel, the parent stays on the row that was opened, including when that row was clicked. Esc goes up. Every screen shows `↑↓ move · enter select · esc back · click`. Left and right change page only when the screen has another page; previous and next are clickable. On home, Esc returns without stopping Hammerspoon. Speech model, Piper voice, and the rewrite model each open a chooser. A file on disk shows ↓ at the right of that row, and selecting it saves the choice without fetching again. A missing catalog file opens a download page in the pane (name, bar, percentage). Success returns to that row with ↓. Failure stays with the error. Esc drops the partial and does not mark the model downloaded. A click stays inside that list. Hotkeys: Enter a row, press the key (modifiers included) or type its name (`Right Option`, `Esc`, `ctrl+shift+space`); Enter saves a typed name into `hotkey_bindings` when it is a key (Esc cancels that row only; a name that is not a key warns and is not written; a name another role already uses is refused and the pane names that role). While the field is open the adapter passes keys through. The Hammerspoon adapter reads those binds. Model rows show the English or multilingual description once and the model id once. `--print` or `DIGIVOICE_SETUP_NONINTERACTIVE=1` still prints the section menu with no prompts (exit 0, also when stdin is not a TTY); `--json` dumps settings + that menu + hardware stub. Detection flags (`word_detection`, `spelling_detection`) default off; stubs only, not wired to STT yet. Rewrite timeout is off by default and cycles 15/30/60s only. Post-process and STT menus offer a suggested local catalog. The numbered menu confirms, then downloads and wires the file. The OpenTUI list opens a download page for a missing file. No user-hosted / cloud endpoints. |
| `quit` | 0 | Stop the adapter and quit Hammerspoon. This is the full stop. Esc and closing the terminal do not call it. `digivoice /quit` is the same command. |
| `reset` | 0 | Restore settings defaults. History and models stay. `digivoice /reset` is the same command. |
| `restart` | 0 | Stop Hammerspoon, then replace this process with a fresh digivoice. |
| `system` | 0 | TTY: Doctor, Reload, Reset, Restart, Update, Logs (`/system/logs`). Otherwise print those slash paths. Logs shows the whole `system.log` in the data directory (beside `status.json`). A take appends one line when it reaches `error` or `empty`. A missing file stays on the page as "No log yet". Reset confirm is still the first choice on that dialog. |
| `install` | 0 every step present or installed, 1 any step failed | Fetch bun 1.4.2, `bun install` `@opentui/core` in `digivoice/tui`, whisper-cli, Piper, sox, `ggml-base.en.bin`, and `en_US-lessac-medium`, then copy the Hammerspoon lua into `~/.hammerspoon/digivoice` and `hs.reload()`. A failed step does not stop the rest. No rewrite GGUF and no cloud STT/TTS. |
| `update` | 0 every step present or installed, 1 any step failed | Same steps as `install` with refresh. A step already at its pin stays. A missing or older step is fetched again. The adapter is copied either way, then `hs.reload()`. The TUI shows that report in the page, then restarts when no step failed. A failure stays in the page. |
| `uninstall` | 0 | Thin stub: not wired yet (remove the tool install and the data dir manually). |
| `reload [--json]` | 0 refreshed, 1 settings invalid or Hammerspoon reload failed | Re-resolve CLI path, validate settings, check the installed Lua adapter (symlink realpath proves the tip), `hs -c hs.reload()` with an 8s timeout. A dropped Mach reply (`CFMessagePort: dropping corrupt reply Mach message`) is success. Timeout and any other non-zero exit clear stale `status.json`. `hs` absent is a skip, not an error. |
| bare `digivoice` (no args) | 0 | TTY: fullscreen home. Centered DIGIVOICE half-block wordmark (five-row face in a six-row slot, xterm cube grays or truecolor, block V) whose letter cubes rest in subdued gray and brighten from the bottom of each column as an uneven level rises and falls. Gaps stay dark. A still dark-gray shadow sits one cell down and one cell right. On a tall window the slot rests about one third of the way down and shifts up when the window is short. A blank gap, then a status row (doctor summary; OK green, a problem red), then the page, which scrolls, then step-rail actions. The selected row has a one-cell left rule and a quiet background; other rows leave that cell blank. Home is History, Settings, System, Quit. Doctor is inside System. On macOS the same launch opens Hammerspoon if it is down (background-only: hide Dock icon, no digivoice menubar, no launch toast), loads `require("digivoice")` when the adapter is installed, and arms the banner (`M.ensure_banner` returns `armed`) without drawing it unless `banner_pinned` is true or a take is in progress. `live_banner` false skips the overlay. A running Hammerspoon is reloaded once when this launch added the require line, or when the loaded adapter has no `ensure_banner`; a take is never reloaded. Budget 4s; failure is a status line, not a hang. TUI Quit and `digivoice quit` stop the adapter and quit Hammerspoon. Esc and closing the Terminal leave it running. Every row is a block: action, then a gray shortcut, slash path, and metadata. Typing `/` runs that path (`/doctor`, `/settings/banner/pin`, `/quit`). History sticks to the newest line; the timestamp is the path and the text is gray on that row. Copy is `c` and Delete is `d`, or a click. Settings returns to home. No TTY: print the home overview (including that control line) and exit 0. `--help` / `-h` / `help` still show argparse help. |
| unknown / bad flags | 2 | Usage on stderr. |

`--hold` and `--toggle` cannot be combined. `speak` takes text or exactly one of
`--clipboard` / `--selection` / `--clipboard-or-history`.

## Install

`digivoice install` brings in the local pieces required to run. `digivoice update` and System → Update (`/system/update`, also `/update`) call the same function with refresh. It does not call a cloud STT or TTS service, and it does not download a rewrite GGUF (rewrite stays off). Issue #4969 is the SHA-safe Hammerspoon adapter hold; it does not add an Otter model pack, and this command does not fetch Otter. Tests pass a fake `fetch` and a fake runner and a home under tmp. They do not download weights, they do not run this command against the network, and they do not write a real home directory.

Each step is `present`, `installed`, or `failed`. Later steps still run after a failure. The process exits 1 when any step failed. Archives that contain `..` or an absolute path are rejected. Tar extraction uses `filter="data"`.

A step that already exists is `present` and is not stamped. The versions this command itself writes live in `~/.local/share/digivoice/vendor/install.json`. Update re-fetches a step when its file is missing or that stamp differs from the pin. A matching stamp stays `present`. Sox that was already on `PATH` (stamp not `brew`) is left alone. Sox or macOS whisper-cli that this command installed with Homebrew is `brew upgrade` on update.

The adapter step copies `init.lua`, `banner_core.lua`, `hotkeys.lua`, and any sibling `*.lua` from `digivoice/hammerspoon` into `~/.hammerspoon/digivoice`. A symlink that already points at this checkout is left in place. A real directory is replaced in place, and lua this checkout no longer ships is deleted, so an old copy or close control cannot remain. Then it runs `hs -c hs.reload()`, the same call as System Reload. `hs` absent is a skip, not an error. A non-zero exit that prints `CFMessagePort: dropping corrupt reply Mach message` is success (`hammerspoon .. reloaded`): reload tears the IPC down after the config has loaded. A timeout stays a failure. Any other failed reload marks the adapter step failed after the files are written.

| Step | Fresh install |
| --- | --- |
| bun | `bun` 1.4.2 zip into `~/.local/bin/bun`: `bun-darwin-aarch64`, `bun-darwin-x64`, `bun-linux-aarch64`, `bun-linux-x64` from `https://github.com/oven-sh/bun/releases/download/bun-v1.4.2/`. |
| opentui | `bun install --cwd digivoice/tui` for `@opentui/core`. `install` is the bun subcommand; `--cwd` follows it. `package.json` has no install script. |
| whisper-cli | Linux: whisper.cpp `v1.9.2` `whisper-bin-ubuntu-x64.tar.gz` or `whisper-bin-ubuntu-arm64.tar.gz` from `https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/`, extracted under `~/.local/share/digivoice/vendor/whisper`, then `~/.local/bin/whisper-cli` points at that binary so the sibling libraries stay beside it. macOS has no official CLI build: `brew install whisper-cpp`. Missing Homebrew fails that step with that reason. |
| piper | Piper `2023.11.14-2` tarball (`piper_linux_x86_64`, `piper_linux_aarch64`, `piper_macos_x64`, `piper_macos_aarch64`) from `https://github.com/rhasspy/piper/releases/download/2023.11.14-2/`, under `vendor/piper`, with `~/.local/bin/piper` pointing at the binary. |
| sox | Already on `PATH`, otherwise `brew install sox`. Missing Homebrew fails that step. |
| stt | `ggml-base.en.bin` from `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin` into the models directory. |
| voice | `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` from `https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/`. |
| adapter | Current `digivoice/hammerspoon/*.lua` into `~/.hammerspoon/digivoice`, then `hs.reload()`. The overlay stays the status icon only: no copy, no close, no pin button. It retracts when idle or pending. |

## dict

1. **Capture** (`capture.py`). `sox` if it is on `PATH`, otherwise `ffmpeg`. 16 kHz mono
   16-bit, which is what whisper.cpp wants, so nothing has to resample. The file is
   `recordings/dict-<UTC stamp>-<8 hex>.wav`.
2. **Transcribe** (`transcribe.py`). `whisper-cli` (or the `whisper-cpp` alias) with
   `-m <model> -f <wav> -l en -nt` (multilingual catalog models use `-l auto`). The
   model is the selected local file: the weights under `models_dir`, an absolute `.bin`,
   or the same filename already installed under LM Studio, Ollama (`OLLAMA_MODELS`), or
   MLX Studio. A missing file raises `model <id> is not installed locally: <path>`,
   the take exits 1, and that line is appended to `system.log`. stdout is the transcript;
   the banner chatter goes to stderr. Segment timestamps are stripped and whitespace is
   collapsed into one line.
3. **Rewrite** (`rewrite.py`, optional). When `rewrite_enabled`: local llama.cpp (or
   local ollama) lightly cleans the dictated words. The dictation is source text,
   never a brief to write something new. Context (email, SMS, professional, coding,
   blog, or none) is a formatting guide and a hint for a misspoken word. It does
   not add sentences, explanations, or extra context. Grammar and spelling stay
   light. Coding formats code or technical prose already dictated and does not
   invent code, APIs, or an implementation. Email formats an email and does not
   invent a subject, recipients, or new points. SMS stays short and in the
   dictated words. The model is a local GGUF: a suggested catalog file under the models
   dir, or an absolute file already on disk. The download list adds whisper.cpp
   medium and large ggml files plus Qwen2.5 7B, Llama 3.2 3B, and Gemma 2 2B
   GGUF weights. The same chooser also lists runnable files discovered under
   `~/.lmstudio/models`, `~/.cache/lm-studio/models`, `~/.ollama/models`
   (or `OLLAMA_MODELS`), and `~/.mlxstudio/models` (MLX Studio, the app also
   called MX Studio). Safetensors and an Ollama tag whose blob is missing stay
   out. URLs, OpenRouter, and ollama registry tags are rejected. Setup lists
   the catalog. The numbered menu confirms, then downloads and wires the file. The OpenTUI chooser opens a download page when that file is missing. Selecting a discovered
   file stores that path. Auto-route from the focused app when enabled
   (match table is `rewrite_app_routes` in settings). Timeout is off by
   default; when enabled it cycles 15 / 30 / 60 seconds only. Fail soft —
   raw transcript on error. Disabled by default. `--no-rewrite` skips.
4. **History** (`history.py`). One JSON object appended to `history.jsonl` (rewritten text when applied).
5. **Paste** (`paste.py`). darwin only, and never fatal. Skipped when `paste_on_stop` is false. When it is on, the transcript is copied with `pbcopy` and Command-V is sent to the app that had focus when the take started (`--focus-name` / `--focus-bundle`, or the frontmost process captured before recording). `osascript -e` receives that bundle id and name as the script argv. A leading `-` is not passed: with `-e` it is not an end-of-options mark, and it used to become the bundle id so the keystroke missed the app. Speak `--selection` uses that same argv when it reads the captured app's selected text, and the Cmd+C fallback activates that app before the keystroke.

Recording modes:

| Mode | Cap | Early stop |
| --- | --- | --- |
| `--hold` | 15s | No — self-bounding `trim` / `-t`. |
| `--toggle` | 30min safety (no UX limit) | Yes — stop-file (default `{data_dir}/dict.stop`), SIGINT/SIGTERM, or ~10s silence pause (sox). |
| neither | 30s | No. |

`--seconds N` overrides the cap. Hold / default use the bounded `CommandRunner` path.
Toggle with the real runner uses `Popen`: open-ended sox/ffmpeg, poll for the stop-file or
signal, SIGINT the recorder process group so the wav header stays valid, then continue the
pipeline. Injected fake runners keep the bounded path so unit tests need no signals.

**Failure behavior.** Missing `sox` and `ffmpeg`, a locked-down microphone, a missing
`ggml-base.en.bin`, a whisper failure, and silence are all exit 1 with a one-line message on
stderr — never a hang. A failed capture leaves nothing behind. A failed transcribe keeps the
wav and prints where it is. Nothing is appended to history for either, so silence never
becomes an empty entry.

**Interrupt / early stop.** Toggle stop (stop-file or signal) keeps the recorded wav, continues whisper → optional rewrite → history → paste of what was captured. Resume-same-take is not supported; expectation is **paste + new take**.

### Cancel (Esc) and empty-take discard

A take can end three ways without producing text, and none of them leaves anything behind:

| Outcome | Trigger | Exit | wav | history | paste | status |
| --- | --- | --- | --- | --- | --- | --- |
| cancelled | cancel-file appears (Esc in the Hammerspoon adapter, or `digivoice cancel`) | 3 | deleted | none | none | `cancelled` |
| empty | whisper returns nothing, or only a silence marker (`[BLANK_AUDIO]`, `[ Silence ]`, `(silence)`), or the final text is blank | 1 | deleted | none | none | `empty` |
| failed | missing tool, whisper error, permission denied | 1 | kept (transcribe failure) | none | none | `error` |

`dict` clears any stale cancel-file at start and again on exit, so a late Esc never kills the next take. The cancel-file is checked while the recorder runs (the recorder process group is signalled and the wav deleted), while `whisper-cli` / the rewrite model run (the real runner polls and kills the child), and between stages. The last check is immediately before the history append; once the history line is written the take is committed and a late cancel is ignored. `paste` / `copy_to_clipboard` also refuse blank text as a last line of defence. Cancelling mid-recording needs `--toggle` (the open-ended recorder, which is what the adapter runs). With `--hold` / default the recorder is bounded and cannot be interrupted, so the cancel lands when it finishes.

## Status feed (banner)

`dict` and `speak` write `status.json` (atomic replace) as they move through stages. The Hammerspoon banner polls it. It is display only. Fails soft: an unwritable file never changes the exit code. Skipped entirely when `live_banner` is false. `banner show [--text T]` / `hide` / `toggle` writes the `banner.show` spawn flag the adapter polls about once a second; a visible flag reveals a preview banner with no dictation behind it.

```json
{"session":"1a2b3c4d5e6f","kind":"dict","state":"rewriting","text":"hey ship the notes","detail":"preset email","updated_ms":1790000000000,"pid":4242}
```

`kind` is `dict` or `speak`. `state` is one of `loading`, `recording`, `transcribing`, `rewriting`, `pasting`, `speaking`, `done`, `cancelled`, `empty`, `error`. `text` is the transcript (dict: raw while transcribing/rewriting, final once pasting), the selected text (speak), or the finished text (`done`). `detail` is the rewrite preset, the paste result, or the error line. `updated_ms` is epoch milliseconds; the adapter ignores any snapshot older than its own session start. Live streaming STT is out of scope: the transcript appears after whisper returns.

**stdout is the transcript and nothing else**, so `digivoice dict | pbcopy` works. Progress,
the wav path, the paste result, and the history path all go to stderr.

## speak

1. **Resolve text.** Argv words, or `--clipboard` (`pbpaste` / `wl-paste` / `xclip` / `xsel`),
   or `--selection` (macOS, in order: focused element's Accessibility selected
   text in the captured app when `--focus-name` / `--focus-bundle` is set, else the
   frontmost app; then Ghostty's selection pasteboard when that target is Ghostty;
   then Cmd+C via osascript only when the clipboard *changes*. A captured app is
   activated before that Command-C, with the same argv rule as paste: no leading
   dash. Linux: primary),
   or `--clipboard-or-history` (clipboard only; **no** history fallback — not the hotkey path).
   Hammerspoon speak uses `--selection`.
2. **Piper** (`speak.py`). `piper --model <voice.onnx> --output_file <speak-…wav>` with text
   on stdin. A saved `tts_voice` file on disk wins, including when `DIGIVOICE_PIPER_VOICE`
   points at a missing default. The env path is used when no saved file exists and that
   path exists. Otherwise the first `*.onnx` under models. The take errors only when no
   voice file can be found.
3. **Play.** `afplay` on darwin; `aplay` then `ffplay` on Linux.
4. **History.** Append `{kind:"speak", text, wav:null}`.

### `--selection` path per app (macOS)

| Frontmost app | Step 1: AX selected text | Step 2: Ghostty pasteboard | Step 3: Cmd+C change-detect |
| --- | --- | --- | --- |
| Ghostty | Miss (terminal grid exposes no `AXSelectedText`; osascript's `missing value` is filtered, never spoken) | **Hit** — `pbpaste -pboard com.mitchellh.ghostty.selection` (copy-on-select) | Fallback when the selection pasteboard is empty (otherwise never reached; clipboard untouched) |
| TextEdit / Notes / Mail (NSText) | **Hit** — focused text view's `AXSelectedText` in the captured app | Skipped (not Ghostty) | Fallback: activate that app, then Cmd+C |
| Safari / Chrome | Hit in text fields; miss on page content | Skipped | **Hit** — activate the captured app, then Cmd+C |
| Grok Bot / other apps | Hit when a text field holds the selection | Skipped | **Hit** — activate the captured app, then Cmd+C |

An unchanged general clipboard at step 3 is empty selection, never readout:
leftover dictation or coding replies are not spoken, and no `kind:dict` history
is consulted. Every step fails soft to the next; all three empty is exit 1.

stdout is the spoken text. Missing piper, voice, player, or empty selection → exit 1,
one line on stderr. Hotkey (`--selection`) soft-fails when nothing is selected — never
falls back to clipboard or `kind:dict` history.

## Paste

darwin only. The transcript is copied to the clipboard with `pbcopy` over stdin — never
interpolated into an AppleScript string — and then `osascript` sends
`keystroke "v" using command down`. When focus is known, the script argv is the
bundle id then the app name. `osascript -e` does not treat a later `-` as the
end of options, so that dash is not passed. It used to be AppleScript argv item
1, the bundle lookup missed, and Command-V never reached the focused app.

The keystroke is the step that needs the macOS Accessibility grant. When it is denied, or
`pbcopy` / `osascript` are missing, or the platform is not darwin, `dict` still exits 0 with
the transcript on stdout and a note on stderr. `pbcopy` leaves the transcript in the
clipboard either way, which is the manual fallback.

## Doctor checks

Required for exit 0:

| id | Ready when |
| --- | --- |
| `whisper-cli` | Executable on `PATH` |
| `piper` | Executable on `PATH`, otherwise `~/.local/bin/piper` |
| `capture` | `sox` or `ffmpeg` on `PATH` |
| `models` | Models directory exists and contains the configured STT file (default `ggml-base.en.bin`) |

Always informational:

| id | Meaning |
| --- | --- |
| `sox`, `ffmpeg` | Each binary, so a missing one is visible when the other satisfies `capture` |
| `settings` | `ok` when settings.json parses and validates (reports banner pin and position); `info` when absent (defaults); `missing` when corrupt. A leftover `banner_density` still loads and is ignored. |
| `hotkeys` | `ok` — defaults are Right Option / Esc / double-tap Left Option until `settings.json` `hotkey_bindings` replaces a row; see `hammerspoon/README.md` |
| `hammerspoon` | `ok` when the adapter dir/init.lua exists under `~/.hammerspoon/digivoice` or the data-dir hammerspoon path; `missing` otherwise |
| `history` | JSONL path and whether the file exists |
| `paths` | Active data directory, macOS models path, Linux models path, recordings directory |
| `tcc` | Mic and Accessibility are not probed; see `hammerspoon/README.md` |
| `rewrite` | Disabled by default (info). Names the configured local GGUF (default `qwen2.5-1.5b-instruct-q4_k_m.gguf`) and reports when that file is not installed. When rewrite is enabled: ok if local runner+GGUF ready, else missing (dict still uses raw transcript). The pass preserves the dictated words; context is format only. Cloud / URL models are not a doctor path. Setup → Post-process lists suggested local GGUFs (download + wire). |
| `detection` | Always info (never required). `word_detection` / `spelling_detection` default off; stubs only, STT still uses whisper |
| `interrupt` | Documents paste-on-stop + new-take behavior, and Esc / `digivoice cancel` discard |

## History records

One JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":"/…/recordings/dict-20260930T120000Z-1a2b3c4d.wav"}
{"ts":"2026-09-30T12:00:01.000Z","kind":"speak","text":"…","wav":null}
```

`ts` is ISO-8601 UTC with milliseconds and a `Z` suffix. `kind` is `dict` or `speak`.
`wav` is the recording path for dictation and `null` for speak (and when dictation has none).

Takes only append. The history screen may delete one line by rewriting the file;
unreadable lines stay. Reads skip lines that do not parse and report how many
were skipped rather than failing the listing. `--grep` matches the entry text
case-insensitively and applies before `--last`, so `--last 5 --grep invoice` is the last five
matching entries. A missing history file is not an error: `history` prints that and exits 0.

## Hammerspoon sample

Under `digivoice/hammerspoon/` (not imported by the Python package):

- Hotkeys are `hotkey_bindings` in `settings.json` (`dictation`, `speak`, `cancel`), parsed by `hammerspoon/hotkeys.lua`. Defaults are Right Option (61) → `dict --toggle --stop-file …`, double-tap Left Option (58) → `speak --selection`, and plain Esc → cancel. A saved remap replaces that bind; the old key is not also kept. The file is re-read when it changes (the next key uses the new bind) and on `hs.reload()` (`digivoice reload`). A binding that does not parse keeps the previous one, prints a warning, and does not stop the event tap. While `hotkey.capture` in the data directory is `1`, that tap returns the key to the terminal and does not run the bind. Enter, Esc, or leaving the field clears the file. A name another role already uses is not written. A custom canvas banner (5x5 square status grid) shows one status icon. No status word, copy, close, pin button, transcript, or fact line. Recording draws a level meter in that grid. The dictating, processing, error, warning, and idle marks each move in place. `banner_animations` false holds one frame. No digivoice menubar mark; background HS only (no Dock icon, no launch toast — TUI Quit tears HS down).
- The icon is the grid (equal 10px pad). Phases map from states the pipeline already sets: `recording`; `transcribing` draws dictating; `loading`, `rewriting`, `pasting`, and `speaking` draw processing; `error`; `warning`. Pending, idle, empty ("nothing to show"), and a finished take draw nothing. A pinned idle banner draws the idle mark, which breathes while animations are on. A `pending: true` flag hides the icon even when it is pinned. Chrome follows the system appearance: dark ground is the digiquant remock canvas (`#000`), light ground is the ivory paper (`#F9F8F6`); recording stays red and warning stays amber.
- The two visibility modes are the existing `banner_pinned` setting, chosen in the terminal UI. Off (the default) retracts for pending, idle, empty, and take end. On keeps the idle icon visible. Drag still moves the icon; release near one of the 9 anchors snaps and persists to `banner_pos.json`. The cancel bind still discards a take. There is no copy button and no close button.
- A click on the icon focuses the digivoice terminal when `tui.pid` shows it is already open, and opens it otherwise. The launcher is injected. Unit tests pass a fake and do not start Terminal or Hammerspoon. The click does not stack a new terminal.
- Launch arms Hammerspoon and draws the idle icon only when `banner_pinned` is true. Recording, dictating, processing, a current error, and a current warning draw the icon. `banner show` is a recording-icon preview unless `pending` is set. `banner hide` retracts it. `banner toggle` retracts while the preview is up and otherwise shows the recording icon. Take start and a `pending: true` flag hide the icon, including a pinned idle icon. Esc still discards a take.
- The cancel bind (Esc by default) writes the cancel-file while a dictation is recording/transcribing/rewriting (swallowed only then, unless the bind is a chord that must not also type). Nothing is pasted or saved.
- The speak bind (double-tap Left Option by default) runs `speak --selection` (the banner shows the processing or error icon, not the selection; no clipboard/history)
- No digivoice menubar mark and no Hammerspoon launch toast (background ship; TUI is chrome for customize / Quit).
- Banner settings (`live_banner`, `banner_position`, `banner_animations`, `banner_pinned`) are read from `settings.json` at the start of every take. `banner_pinned` decides whether the idle icon stays. `banner_animations` false holds one frame of the meter or mark. There is no density setting in the TUI or in `settings set`. A leftover `banner_density` in an old file still loads and is ignored.

See `hammerspoon/README.md` for install and Mic + Accessibility TCC.

## Out of this package

- Cloud STT/TTS or cloud rewrite backends
- OpenRouter / user-hosted URL rewrite models (blocked; post-process is local GGUF from the suggested catalog)
- Super Whisper
- A required OpenCode plugin
- Hammerspoon as a Python dependency (sample adapter only)
- Screen OCR
