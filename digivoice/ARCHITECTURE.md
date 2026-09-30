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
| `src/digivoice/capture.py` | Microphone to wav. `sox` first, then `ffmpeg`. |
| `src/digivoice/transcribe.py` | `whisper-cli` over a wav, transcript cleanup. |
| `src/digivoice/history.py` | JSONL append, tolerant read, `--last` / `--grep` filters. |
| `src/digivoice/paste.py` | Clipboard plus Command-V into the focused app. Fails soft. |
| `src/digivoice/errors.py` | `VoiceError` and the capture / transcribe subclasses. |
| `src/digivoice/models.py` | Pydantic v2 `VoicePaths`, `DoctorReport`, `CliResult`, `HistoryEntry`, `CaptureResult`, `Transcript`, `PasteResult`. |

Every external binary — `sox`, `ffmpeg`, `whisper-cli`, `pbcopy`, `osascript` — is reached
through a `CommandRunner`, and every argv is a list. `shell=True` is never used and user text
is never interpolated into a command string. `Runtime.runner` is the injection point: `None`
means the real subprocess runner, and tests pass a fake, so no test needs a microphone, a
sound card, a model, or a clipboard.

## Data locations

macOS defaults:

- models: `~/Library/Application Support/digivoice/models/`
- recordings: `~/Library/Application Support/digivoice/recordings/`
- history: `~/Library/Application Support/digivoice/history.jsonl`
- default model file: `~/Library/Application Support/digivoice/models/ggml-base.en.bin`

Linux fallback (also what `doctor` prints when reporting the other platform):

- models: `${XDG_DATA_HOME:-~/.local/share}/digivoice/models/`
- recordings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/recordings/`
- history: `${XDG_DATA_HOME:-~/.local/share}/digivoice/history.jsonl`
- same filename: `ggml-base.en.bin`

`DIGIVOICE_DATA_DIR` overrides the data directory on every platform. `doctor` does not create
directories; `dict` and `history` do, because those commands write.

`ggml-base.en` is the snappy push-to-talk default. whisper.cpp ships that model as
`ggml-base.en.bin`.

## CLI

| Command | Exit | Behavior |
| --- | --- | --- |
| `doctor` | 0 ready, 1 not ready | Report below. |
| `dict [--hold\|--toggle] [--seconds N] [--no-paste]` | 0 dictated, 1 capture or transcribe failed | Record, transcribe, append, paste. |
| `speak [text\|--clipboard\|--selection]` | 2 | Stub until PR2. Does not call Piper. |
| `history [--last N] [--grep PATTERN]` | 0 | Lists matching entries. |
| unknown / bad flags | 2 | Usage on stderr. |

`--hold` and `--toggle` cannot be combined. `speak` takes text or exactly one of
`--clipboard` / `--selection`.

## dict

1. **Capture** (`capture.py`). `sox` if it is on `PATH`, otherwise `ffmpeg`. 16 kHz mono
   16-bit, which is what whisper.cpp wants, so nothing has to resample. The file is
   `recordings/dict-<UTC stamp>-<8 hex>.wav`.
2. **Transcribe** (`transcribe.py`). `whisper-cli` (or the `whisper-cpp` alias) with
   `-m <models_dir>/ggml-base.en.bin -f <wav> -l en -nt`. stdout is the transcript; the
   banner chatter goes to stderr. Segment timestamps are stripped and whitespace is
   collapsed into one line.
3. **History** (`history.py`). One JSON object appended to `history.jsonl`.
4. **Paste** (`paste.py`). darwin only, and never fatal.

The recording cap is set by the mode, because PR1 has no key listener to release on —
PR3 owns that:

| Mode | Cap | Override |
| --- | --- | --- |
| `--hold` | 15s | `--seconds N` |
| `--toggle` | 60s | `--seconds N` |
| neither | 30s | `--seconds N` |

Both recorders bound themselves and then exit normally — `sox … rec trim 0 N` and
`ffmpeg … -t N` — so the wav header is valid rather than truncated. A recorder that is
still running after the cap plus 10s of slack is treated as a timeout.

**Failure behavior.** Missing `sox` and `ffmpeg`, a locked-down microphone, a missing
`ggml-base.en.bin`, a whisper failure, and silence are all exit 1 with a one-line message on
stderr — never a hang. A failed capture leaves nothing behind. A failed transcribe keeps the
wav and prints where it is. Nothing is appended to history for either, so silence never
becomes an empty entry.

**stdout is the transcript and nothing else**, so `digivoice dict | pbcopy` works. Progress,
the wav path, the paste result, and the history path all go to stderr.

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
| `tcc` | Mic and Accessibility are not probed; paste degrades to stdout |

## History records

PR1 appends one JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":"/…/recordings/dict-20260930T120000Z-1a2b3c4d.wav"}
{"ts":"2026-09-30T12:00:01.000Z","kind":"dict","text":"…","wav":null}
```

`ts` is ISO-8601 UTC with milliseconds and a `Z` suffix. `kind` is `dict`, or `speak` once
PR2 lands. `wav` is the recording path for dictation and `null` when there is none.

The file is only ever appended to. Reads skip lines that do not parse and report how many
were skipped rather than failing the listing. `--grep` matches the entry text
case-insensitively and applies before `--last`, so `--last 5 --grep invoice` is the last five
matching entries. A missing history file is not an error: `history` prints that and exits 0.

## Out of this package

- Cloud STT/TTS
- Super Whisper
- A required OpenCode plugin
- Piper playback (PR2)
- Hammerspoon / Shortcuts bindings and the Mic + Accessibility runbook (PR3)
- Screen OCR
