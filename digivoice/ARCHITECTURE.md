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
| `src/digivoice/setup.py` | Interactive `setup` wizard (stdlib arrow/numbered menus) + `--print` overview and `recommend_models()` hardware stub (#4939 hook). |
| `src/digivoice/tui.py` | Shared stdlib TUI: alternate-screen frames, step-rail menus, intro build-in, wrapping. |
| `src/digivoice/pixel_hero.py` | 7×10 DIGIVOICE glyph map. The home header paints those glyphs as five half-block rows in `tui.py`. |
| `src/digivoice/catalog.py` | Suggested local STT ggml + rewrite GGUF list; download + wire into models/. |
| `src/digivoice/home.py` | Bare-`digivoice` home shell: fullscreen centered menu on a TTY, printed overview otherwise. |
| `src/digivoice/reload.py` | `reload`: CLI path, settings, Lua adapter tip, bounded Hammerspoon reload; clears stale status on failure. |
| `src/digivoice/rewrite.py` | Optional local post-STT rewrite (ollama / llama.cpp); fail soft. |
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
| `doctor` | 0 ready, 1 not ready | Report below. |
| `dict [--hold\|--toggle] [--seconds N] [--stop-file PATH] [--cancel-file PATH] [--no-paste] [--no-rewrite]` | 0 dictated, 1 capture / transcribe failed or nothing recognized, 3 cancelled | Record, transcribe, optional rewrite, append, paste. |
| `speak [text\|--clipboard\|--selection\|--clipboard-or-history]` | 0 spoken, 1 Piper/player/source failed | Piper playback; append `kind:speak`. |
| `history [--last N] [--grep PATTERN] [--copy-last] [--json]` | 0 (1 if copy-last empty) | Lists / copies last dict. |
| `cancel [--cancel-file PATH]` | 0 | Create the cancel-file; a running `dict` discards its take. |
| `status` | 0 shown, 1 none yet | Print the `status.json` the banner reads. |
| `banner show [--text T]` / `hide` / `toggle` | 0 | Write the `banner.show` spawn flag the adapter polls; shows a preview without dictation. |
| `settings` / `setup` [`get`/`set`/`path`] [`--json`] | 0 / 2 | `settings` shows or changes settings.json. `setup` is the interactive wizard (Models / Post-process / Features / Hotkeys docs / Hardware stub / Review & save / Doctor / Quit); `--print` or `DIGIVOICE_SETUP_NONINTERACTIVE=1` prints values + menu tree with no prompts (exit 0, also when stdin is not a TTY); `--json` dumps settings + menu + hardware stub. Detection flags (`word_detection`, `spelling_detection`) default off; stubs only, not wired to STT yet. Rewrite timeout is off by default and cycles 15/30/60s only. Post-process and STT menus offer a suggested local catalog; select downloads and wires the file. No user-hosted / cloud endpoints. |
| `update` / `uninstall` | 0 | Thin stubs: not wired yet (reinstall via uv / brew; remove tool + data dir manually). |
| `reload [--json]` | 0 refreshed, 1 settings invalid or Hammerspoon reload failed | Re-resolve CLI path, validate settings, check the installed Lua adapter (symlink realpath proves the tip), `hs -c hs.reload()` with an 8s timeout; on failure clear stale `status.json`. `hs` absent is a skip, not an error. |
| bare `digivoice` (no args) | 0 | TTY: fullscreen home. Centered DIGIVOICE half-block wordmark (five rows, one foreground, block V) that builds in over a voice-block field, mono fact line, status strip (models / banner / health / control), step-rail actions. The selected row is `[*]` in the terminal foreground; other rows are `[ ]` (doctor, settings, history, reload, update, uninstall, setup wizard submenu, quit). On macOS the same launch opens Hammerspoon if it is down (background-only: hide Dock icon, no digivoice menubar, no launch toast), loads `require("digivoice")` when the adapter is installed, and shows the banner (`M.ensure_banner`) unless a take is in progress or `live_banner` is false. A running Hammerspoon is reloaded once when this launch added the require line, or when the loaded adapter has no `ensure_banner`; a take is never reloaded. Budget 4s; failure is a status line, not a hang. TUI Quit stops the adapter and quits Hammerspoon; closing the Terminal alone leaves HS running. Setup returns to home. No TTY: print the home overview (including that control line) and exit 0. `--help` / `-h` / `help` still show argparse help. |
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
   model is a local GGUF from the suggested catalog under the models
   dir (multilingual Qwen2.5 instruct Q4_K_M variants). URLs, OpenRouter, and
   ollama registry tags are rejected. Setup lists the catalog; select
   downloads and wires the file. Auto-route from the focused app when enabled
   (match table is `rewrite_app_routes` in settings). Timeout is off by
   default; when enabled it cycles 15 / 30 / 60 seconds only. Fail soft —
   raw transcript on error. Disabled by default. `--no-rewrite` skips.
4. **History** (`history.py`). One JSON object appended to `history.jsonl` (rewritten text when applied).
5. **Paste** (`paste.py`). darwin only, and never fatal. Skipped when `paste_on_stop` is false.

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
| `settings` | `ok` when settings.json parses and validates (reports banner_density etc.); `info` when absent (defaults); `missing` when corrupt |
| `hotkeys` | `ok` — compiled-in sample binds (Right Option / Esc / double-tap Left Option); see `hammerspoon/README.md` |
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

The file is only ever appended to. Reads skip lines that do not parse and report how many
were skipped rather than failing the listing. `--grep` matches the entry text
case-insensitively and applies before `--last`, so `--last 5 --grep invoice` is the last five
matching entries. A missing history file is not an error: `history` prints that and exits 0.

## Hammerspoon sample

Under `digivoice/hammerspoon/` (not imported by the Python package):

- Right Option (61) → `dict --toggle --stop-file …`. A custom canvas banner (5x5 square status grid, ported from digichat) shows the take from record through paste. Its text comes from `status.json`. No chrome on the banner (no titles/hints); click toggles density retract → full. No digivoice menubar mark; background HS only (no Dock icon, no launch toast — TUI Quit tears HS down).
- The banner hugs content (no min-width gutter; equal 10px pad, no leftover header row) with the grid top-left. The first transcript line is centered on that icon row. Chrome follows the system appearance: dark ground is the digiquant remock canvas (`#000`), light ground is the ivory paper (`#F9F8F6`); RYG status colors stay. Dictated text appears at once. Full caps near half the screen height and wheel-scrolls with no scrollbar; lines share one uniform width and the width locks from the longest line up front. Cancelled, empty, and error stay on the grid — no status sentence beside it.
- Hover reveals icon-only copy + close below the banner (the digichat copy and close marks; stacked when retracted, right-aligned row when full). Drag moves it freely; release near one of the 9 anchors snaps and persists to `banner_pos.json`. Center pins keep the center on expand; edge pins grow outward. Close hides instantly (never discards); Esc still discards a take.
- The banner is hidden by default: `banner show [--text T]` (or the adapter's `spawn_preview()`) reveals a preview with no dictation; `banner hide` / `toggle` flips the flag; Esc on a preview only hides it.
- Esc → writes the cancel-file while a dictation is recording/transcribing/rewriting (swallowed only then). Nothing is pasted or saved.
- Double-tap Left Option (58) → `speak --selection` (banner shows the selected text, or why there is none; no clipboard/history)
- No digivoice menubar mark and no Hammerspoon launch toast (background ship; TUI is chrome for customize / Quit).
- Banner settings (`live_banner`, `banner_position`, `banner_density`, `banner_animations`) are read from `settings.json` at the start of every take. Retract (default) is the grid and auto-dismisses a few seconds after idle/done; full stays until collapsed or removed.

See `hammerspoon/README.md` for install and Mic + Accessibility TCC.

## Out of this package

- Cloud STT/TTS or cloud rewrite backends
- OpenRouter / user-hosted URL rewrite models (blocked; post-process is local GGUF from the suggested catalog)
- Super Whisper
- A required OpenCode plugin
- Hammerspoon as a Python dependency (sample adapter only)
- Screen OCR
