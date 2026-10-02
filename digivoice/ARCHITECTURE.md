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
| `src/digivoice/menu_tree.py` | TTY `/settings` path. Enter opens a folder or a list. A model list shows size and the recommended row; a missing file downloads only after confirm. Each row is a bold name, a bracketed value, and a gray explanation. |
| `src/digivoice/setup.py` | TTY opens the `/settings` path. Pipes keep the numbered wizard. `--print` overview and `recommend_models()` hardware stub (#4939 hook). |
| `src/digivoice/tui.py` | Shared menu blocks and the non-TTY numbered prompts. |
| `src/digivoice/opentui.py` | Replaces a TTY process with the OpenTUI app. |
| `src/digivoice/tui_bridge.py` | Local JSON screen model the OpenTUI process calls. No network. |
| `tui/` | OpenTUI (`@opentui/core`) app: `createCliRenderer`, boxes, and text. |
| `src/digivoice/pixel_hero.py` | 7×10 DIGIVOICE glyph map. The home header paints those glyphs as five half-block rows in `tui.py`. |
| `src/digivoice/catalog.py` | Suggested local STT ggml + rewrite GGUF list; download + wire into models/. |
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

A TTY does not draw the Python alternate screen. `opentui.py` replaces the process with `bun digivoice/tui/src/main.js` (the OpenTUI quickstart runtime; `DIGIVOICE_NODE` can point at another binary). That file follows the quickstart: `createCliRenderer` from `@opentui/core`, then `BoxRenderable` and `TextRenderable`. The five-row half-block DIGIVOICE wordmark (block V, letter gap 2, cube grays 59/102/145/188/231, or matching `38;2` RGB only when `COLORTERM` is `truecolor` or `24bit`) is centered on the page. The build runs about 1400ms, then a short glint. Under it, every screen uses the same left-aligned column, centered on the page: `[*]` or `[ ]`, the action, then in cube gray 145 (RGB 175 when truecolor) the shortcut, the slash path, and metadata when the row has a value or a timestamp. Empty parts are skipped. Home, history, settings, choosers, system, logs, and doctor all use that row. Extra prose stays off the page. The footer is `↑↓ move · enter select · esc back · click`. Esc on home exits 0 and leaves Hammerspoon running. `SIGHUP` does the same. Quit is the action that stops Hammerspoon. Restart confirms, then the OpenTUI process re-execs the Python CLI in place. Update stays on System and shows the reinstall line. A click runs the same action as Enter, including a settings choice. After a choice or a cancelled download, the parent stays on the opened row. The OpenTUI process reads screens from `python -m digivoice.tui_bridge` (stdin JSON, no socket). Pipes and agents stay on the Python CLI. The OpenTUI check is `npm test` in `digivoice/tui`, which runs `bun test` and `createTestRenderer` from `@opentui/core/testing`.

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
| `settings` / `setup` [`get`/`set`/`path`] [`--json`] | 0 / 2 | `settings` shows or changes settings.json. `setup` on a TTY opens the `/settings` path (speech, rewrite, banner, hotkeys). Enter opens a folder or a chooser. It does not toggle or cycle in place. On/off, pin, position, animations, style, model, and voice each open a list; the value is saved only when that row is picked. After a choice or cancel, the parent stays on the row that was opened, including when that row was clicked. Esc goes up. Every screen shows `↑↓ move · enter select · esc back · click`. Left and right change page only when the screen has another page; previous and next are clickable. On home, Esc returns without stopping Hammerspoon. Speech model and Piper voice each open a chooser; a click stays inside that list. Hotkeys: Enter a row, press the key (modifiers included) or type its name (`Right Option`, `Esc`, `ctrl+shift+space`); Enter saves a typed name into `hotkey_bindings` (Esc cancels that row only). The Hammerspoon adapter reads those binds. Model rows show the English or multilingual description once and the model id once. `--print` or `DIGIVOICE_SETUP_NONINTERACTIVE=1` still prints the section menu with no prompts (exit 0, also when stdin is not a TTY); `--json` dumps settings + that menu + hardware stub. Detection flags (`word_detection`, `spelling_detection`) default off; stubs only, not wired to STT yet. Rewrite timeout is off by default and cycles 15/30/60s only. Post-process and STT menus offer a suggested local catalog; select downloads and wires the file. No user-hosted / cloud endpoints. |
| `quit` | 0 | Stop the adapter and quit Hammerspoon. This is the full stop. Esc and closing the terminal do not call it. `digivoice /quit` is the same command. |
| `reset` | 0 | Restore settings defaults. History and models stay. `digivoice /reset` is the same command. |
| `restart` | 0 | Stop Hammerspoon, then replace this process with a fresh digivoice. |
| `system` | 0 | TTY: Doctor, Reload, Reset, Restart, Update, Logs (`/system/logs`). Otherwise print those slash paths. Logs shows the whole `system.log` in the data directory (beside `status.json`). A take appends one line when it reaches `error` or `empty`. A missing file stays on the page as "No log yet". Reset confirm is still the first choice on that dialog. |
| `update` / `uninstall` | 0 | Thin stubs: not wired yet (reinstall via uv / brew; remove tool + data dir manually). |
| `reload [--json]` | 0 refreshed, 1 settings invalid or Hammerspoon reload failed | Re-resolve CLI path, validate settings, check the installed Lua adapter (symlink realpath proves the tip), `hs -c hs.reload()` with an 8s timeout; on failure clear stale `status.json`. `hs` absent is a skip, not an error. |
| bare `digivoice` (no args) | 0 | TTY: fullscreen home. Centered DIGIVOICE half-block wordmark (five rows, xterm cube grays or truecolor, block V) that builds in place, then a short glint, a blank gap, status strip (models / banner / health / control), step-rail actions. The selected row is `[*]` in the terminal foreground; other rows are `[ ]`. Home is History, Settings, System, Quit. Doctor is inside System. On macOS the same launch opens Hammerspoon if it is down (background-only: hide Dock icon, no digivoice menubar, no launch toast), loads `require("digivoice")` when the adapter is installed, and arms the banner (`M.ensure_banner` returns `armed`) without drawing it unless `banner_pinned` is true or a take is in progress. `live_banner` false skips the overlay. A running Hammerspoon is reloaded once when this launch added the require line, or when the loaded adapter has no `ensure_banner`; a take is never reloaded. Budget 4s; failure is a status line, not a hang. TUI Quit and `digivoice quit` stop the adapter and quit Hammerspoon. Esc and closing the Terminal leave it running. Every row is a block: action, then a gray shortcut, slash path, and metadata. Typing `/` runs that path (`/doctor`, `/settings/banner/pin`, `/quit`). History shows the text with the timestamp in gray underneath; Copy is `c` and Delete is `d`, or a click. Settings returns to home. No TTY: print the home overview (including that control line) and exit 0. `--help` / `-h` / `help` still show argparse help. |
| unknown / bad flags | 2 | Usage on stderr. |

`--hold` and `--toggle` cannot be combined. `speak` takes text or exactly one of
`--clipboard` / `--selection` / `--clipboard-or-history`.

## dict

1. **Capture** (`capture.py`). `sox` if it is on `PATH`, otherwise `ffmpeg`. 16 kHz mono
   16-bit, which is what whisper.cpp wants, so nothing has to resample. The file is
   `recordings/dict-<UTC stamp>-<8 hex>.wav`.
2. **Transcribe** (`transcribe.py`). `whisper-cli` (or the `whisper-cpp` alias) with
   `-m <models_dir>/ggml-base.en.bin -f <wav> -l en -nt`. stdout is the transcript; the
   banner chatter goes to stderr. Segment timestamps are stripped and whitespace is
   collapsed into one line.
3. **Rewrite** (`rewrite.py`, optional). When `rewrite_enabled`: local llama.cpp (or
   local ollama) with a preset (email / SMS / professional / coding / blog). The
   model is a local GGUF: a suggested catalog file under the models
   dir, or an absolute file already on disk. The download list adds whisper.cpp
   medium and large ggml files plus Qwen2.5 7B, Llama 3.2 3B, and Gemma 2 2B
   GGUF weights. The same chooser also lists runnable files discovered under
   `~/.lmstudio/models`, `~/.cache/lm-studio/models`, `~/.ollama/models`
   (or `OLLAMA_MODELS`), and `~/.mlxstudio/models` (MLX Studio, the app also
   called MX Studio). Safetensors and an Ollama tag whose blob is missing stay
   out. URLs, OpenRouter, and ollama registry tags are rejected. Setup lists
   the catalog; select downloads and wires the file. Selecting a discovered
   file stores that path. Auto-route from the focused app when enabled
   (match table is `rewrite_app_routes` in settings). Timeout is off by
   default; when enabled it cycles 15 / 30 / 60 seconds only. Fail soft —
   raw transcript on error. Disabled by default. `--no-rewrite` skips.
4. **History** (`history.py`). One JSON object appended to `history.jsonl` (rewritten text when applied).
5. **Paste** (`paste.py`). darwin only, and never fatal. Skipped when `paste_on_stop` is false. When it is on, the transcript is copied with `pbcopy` and Command-V is sent to the app that had focus when the take started (`--focus-name` / `--focus-bundle`, or the frontmost process captured before recording). Speak `--selection` reads that same app's selected text.

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
   text, then Ghostty's selection pasteboard when Ghostty is frontmost, then
   Cmd+C via osascript only when the clipboard *changes*; Linux: primary),
   or `--clipboard-or-history` (clipboard only; **no** history fallback — not the hotkey path).
   Hammerspoon speak uses `--selection`.
2. **Piper** (`speak.py`). `piper --model <voice.onnx> --output_file <speak-…wav>` with text
   on stdin. Voice from `DIGIVOICE_PIPER_VOICE` or the first `*.onnx` under models.
3. **Play.** `afplay` on darwin; `aplay` then `ffplay` on Linux.
4. **History.** Append `{kind:"speak", text, wav:null}`.

### `--selection` path per app (macOS)

| Frontmost app | Step 1: AX selected text | Step 2: Ghostty pasteboard | Step 3: Cmd+C change-detect |
| --- | --- | --- | --- |
| Ghostty | Miss (terminal grid exposes no `AXSelectedText`; osascript's `missing value` is filtered, never spoken) | **Hit** — `pbpaste -pboard com.mitchellh.ghostty.selection` (copy-on-select) | Fallback when the selection pasteboard is empty (otherwise never reached; clipboard untouched) |
| TextEdit / Notes / Mail (NSText) | **Hit** — focused text view's `AXSelectedText` | Skipped (not Ghostty) | Fallback for non-text focus |
| Safari / Chrome | Hit in text fields; miss on page content | Skipped | **Hit** — page selections copy via Cmd+C |
| Grok Bot / other apps | Hit when a text field holds the selection | Skipped | **Hit** (previously the only path; unchanged) |

An unchanged general clipboard at step 3 is empty selection, never readout:
leftover dictation or coding replies are not spoken, and no `kind:dict` history
is consulted. Every step fails soft to the next; all three empty is exit 1.

stdout is the spoken text. Missing piper, voice, player, or empty selection → exit 1,
one line on stderr. Hotkey (`--selection`) soft-fails when nothing is selected — never
falls back to clipboard or `kind:dict` history.

## Paste

darwin only. The transcript is copied to the clipboard with `pbcopy` over stdin — never
interpolated into an AppleScript string — and then `osascript` sends
`keystroke "v" using command down`.

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
| `rewrite` | Disabled by default (info). Names the configured local GGUF (default `qwen2.5-1.5b-instruct-q4_k_m.gguf`) and reports when that file is not installed. When rewrite is enabled: ok if local runner+GGUF ready, else missing (dict still uses raw transcript). Cloud / URL models are not a doctor path. Setup → Post-process lists suggested local GGUFs (download + wire). |
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

- Hotkeys are `hotkey_bindings` in `settings.json` (`dictation`, `speak`, `cancel`), parsed by `hammerspoon/hotkeys.lua`. Defaults are Right Option (61) → `dict --toggle --stop-file …`, double-tap Left Option (58) → `speak --selection`, and plain Esc → cancel. A saved remap replaces that bind; the old key is not also kept. The file is re-read when it changes (the next key uses the new bind) and on `hs.reload()` (`digivoice reload`). A binding that does not parse keeps the previous one, prints a warning, and does not stop the event tap. A custom canvas banner (5x5 square status grid) shows one status icon. No status word, copy, close, pin button, transcript, waveform, or fact line. No digivoice menubar mark; background HS only (no Dock icon, no launch toast — TUI Quit tears HS down).
- The icon is the grid (equal 10px pad). Phases map from states the pipeline already sets: `recording`; `transcribing` draws dictating; `loading`, `rewriting`, `pasting`, and `speaking` draw processing; `error`; `warning`. Pending, idle, empty ("nothing to show"), and a finished take draw nothing. A pinned idle banner draws a calm idle icon. A `pending: true` flag hides the icon even when it is pinned. Chrome follows the system appearance: dark ground is the digiquant remock canvas (`#000`), light ground is the ivory paper (`#F9F8F6`); recording stays red and warning stays amber.
- The two visibility modes are the existing `banner_pinned` setting, chosen in the terminal UI. Off (the default) retracts for pending, idle, empty, and take end. On keeps the idle icon visible. Drag still moves the icon; release near one of the 9 anchors snaps and persists to `banner_pos.json`. The cancel bind still discards a take. There is no copy button and no close button.
- A click on the icon focuses the digivoice terminal when `tui.pid` shows it is already open, and opens it otherwise. The launcher is injected. Unit tests pass a fake and do not start Terminal or Hammerspoon. The click does not stack a new terminal.
- Launch arms Hammerspoon and draws the idle icon only when `banner_pinned` is true. Recording, dictating, processing, a current error, and a current warning draw the icon. `banner show` is a recording-icon preview unless `pending` is set. `banner hide` retracts it. `banner toggle` retracts while the preview is up and otherwise shows the recording icon. Take start and a `pending: true` flag hide the icon, including a pinned idle icon. Esc still discards a take.
- The cancel bind (Esc by default) writes the cancel-file while a dictation is recording/transcribing/rewriting (swallowed only then, unless the bind is a chord that must not also type). Nothing is pasted or saved.
- The speak bind (double-tap Left Option by default) runs `speak --selection` (the banner shows the processing or error icon, not the selection; no clipboard/history)
- No digivoice menubar mark and no Hammerspoon launch toast (background ship; TUI is chrome for customize / Quit).
- Banner settings (`live_banner`, `banner_position`, `banner_animations`, `banner_pinned`) are read from `settings.json` at the start of every take. `banner_pinned` decides whether the idle icon stays. There is no density setting in the TUI or in `settings set`. A leftover `banner_density` in an old file still loads and is ignored.

See `hammerspoon/README.md` for install and Mic + Accessibility TCC.

## Out of this package

- Cloud STT/TTS or cloud rewrite backends
- OpenRouter / user-hosted URL rewrite models (blocked; post-process is local GGUF from the suggested catalog)
- Super Whisper
- A required OpenCode plugin
- Hammerspoon as a Python dependency (sample adapter only)
- Screen OCR
