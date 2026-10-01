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
| `src/digivoice/rewrite.py` | Optional local post-STT rewrite (ollama / llama.cpp); fail soft. |
| `src/digivoice/paste.py` | Clipboard plus Command-V into the focused app. Fails soft. |
| `src/digivoice/errors.py` | `VoiceError` and the capture / transcribe / speak subclasses. |
| `src/digivoice/models.py` | Pydantic v2 models including `RewriteResult` and path/doctor/history types. |
| `hammerspoon/` | Sample hotkey adapter, live dictation banner/menubar mark, TCC runbook. |

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
- settings: `~/Library/Application Support/digivoice/settings.json`
- default model file: `~/Library/Application Support/digivoice/models/ggml-base.en.bin`

Linux fallback (also what `doctor` prints when reporting the other platform):

- models: `${XDG_DATA_HOME:-~/.local/share}/digivoice/models/`
- recordings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/recordings/`
- history: `${XDG_DATA_HOME:-~/.local/share}/digivoice/history.jsonl`
- toggle stop-file: `${XDG_DATA_HOME:-~/.local/share}/digivoice/dict.stop`
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
| `dict [--hold\|--toggle] [--seconds N] [--stop-file PATH] [--no-paste] [--no-rewrite]` | 0 dictated, 1 capture or transcribe failed | Record, transcribe, optional rewrite, append, paste. |
| `speak [text\|--clipboard\|--selection\|--clipboard-or-history]` | 0 spoken, 1 Piper/player/source failed | Piper playback; append `kind:speak`. |
| `history [--last N] [--grep PATTERN] [--copy-last] [--json]` | 0 (1 if copy-last empty) | Lists / copies last dict. |
| `settings` / `setup` [`get`/`set`/`path`] [`--json`] | 0 / 2 | Show or change settings.json. |
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
3. **Rewrite** (`rewrite.py`, optional). When `rewrite_enabled`: local ollama / llama.cpp with a preset (email / SMS / professional / coding / blog). Auto-route from the focused app when enabled (match table is `rewrite_app_routes` in settings, not hard-coded paths). Fail soft — raw transcript on error. Disabled by default. `--no-rewrite` skips.
4. **History** (`history.py`). One JSON object appended to `history.jsonl` (rewritten text when applied).
5. **Paste** (`paste.py`). darwin only, and never fatal. Skipped when `paste_on_stop` is false.

Recording modes:

| Mode | Cap | Early stop |
| --- | --- | --- |
| `--hold` | 15s | No — self-bounding `trim` / `-t`. |
| `--toggle` | 60s safety | Yes — stop-file (default `{data_dir}/dict.stop`) or SIGINT/SIGTERM. |
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
| `models` | Models directory exists and contains `ggml-base.en.bin` |

Always informational:

| id | Meaning |
| --- | --- |
| `sox`, `ffmpeg` | Each binary, so a missing one is visible when the other satisfies `capture` |
| `history` | JSONL path and whether the file exists |
| `paths` | Active data directory, macOS models path, Linux models path, recordings directory |
| `tcc` | Mic and Accessibility are not probed; see `hammerspoon/README.md` |
| `rewrite` | Disabled by default (info). When enabled: ok if local runner+model ready, else missing (dict still uses raw transcript) |
| `interrupt` | Documents paste-on-stop + new-take behavior |

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

- Right Option (61) → `dict --toggle --stop-file …` with a **persistent** menubar + canvas banner for the whole capture (uses `assets/digivoice-mark.png` when present).
- Double-tap Left Option (58) → `speak --selection` (soft-fail notify if empty; no clipboard/history)

See `hammerspoon/README.md` for install and Mic + Accessibility TCC.

## Out of this package

- Cloud STT/TTS or cloud rewrite backends
- Bundled rewrite GGUF weights (wiring + doctor + presets ship; download separately under the models dir)
- Super Whisper
- A required OpenCode plugin
- Hammerspoon as a Python dependency (sample adapter only)
- Screen OCR
