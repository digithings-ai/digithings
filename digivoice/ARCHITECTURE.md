# digivoice architecture

Local CLI package at `digivoice/`. No network service and no port. Python 3.12. Console script `digivoice` and `python -m digivoice`.

## Layout

| Path | Role |
| --- | --- |
| `src/digivoice/cli.py` | Argv dispatch and process entry. |
| `src/digivoice/doctor.py` | Host checks and the text report. |
| `src/digivoice/paths.py` | Data, models, and history locations. Default model id. |
| `src/digivoice/probe.py` | `PATH` lookup and file checks. No shell. |
| `src/digivoice/models.py` | Pydantic v2 `VoicePaths`, `DoctorReport`, `CliResult`. |

## Data locations

macOS defaults:

- models: `~/Library/Application Support/digivoice/models/`
- history: `~/Library/Application Support/digivoice/history.jsonl`
- default model file: `~/Library/Application Support/digivoice/models/ggml-base.en.bin`

Linux fallback (also what `doctor` prints when reporting the other platform):

- models: `${XDG_DATA_HOME:-~/.local/share}/digivoice/models/`
- history: `${XDG_DATA_HOME:-~/.local/share}/digivoice/history.jsonl`
- same filename: `ggml-base.en.bin`

`DIGIVOICE_DATA_DIR` overrides the data directory on every platform. `doctor` does not create directories.

`ggml-base.en` is the snappy push-to-talk default. whisper.cpp ships that model as `ggml-base.en.bin`.

## CLI

| Command | Exit | Behavior in this scaffold |
| --- | --- | --- |
| `doctor` | 0 ready, 1 not ready | Report below. |
| `dict [--hold\|--toggle]` | 2 | Stub. Does not open the microphone. |
| `speak [text\|--clipboard\|--selection]` | 2 | Stub. Does not call Piper. |
| `history [--last N] [--grep PATTERN]` | 0 | Prints the JSONL path. Does not read or append. |
| unknown / bad flags | 2 | Usage on stderr. |

`--hold` and `--toggle` cannot be combined. `speak` takes text or exactly one of `--clipboard` / `--selection`.

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
| `paths` | Active data directory, macOS models path, and Linux models path |
| `tcc` | Mic and Accessibility are not probed yet |

## Planned history records

PR1 and PR2 append one JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":null}
{"ts":"2026-09-30T12:00:01.000Z","kind":"speak","text":"…"}
```

`ts` is ISO-8601 UTC. `kind` is `dict` or `speak`. `wav` is optional and only for dictation.

## Out of this package

- Cloud STT/TTS
- Super Whisper
- A required OpenCode plugin
- Hammerspoon / Shortcuts bindings (PR3)
- Screen OCR
