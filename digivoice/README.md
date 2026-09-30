# digivoice

Local speech tools for digithings. Mac-first command line for dictation (whisper.cpp), speech (Piper), and an append-only session history. Any terminal can call it. Hotkeys are a later adapter, not this package.

Speech stays on the machine. digivoice does not call a cloud STT or TTS service, and it does not depend on Super Whisper. OpenCode's `@renjfk/opencode-voice` plugin is optional convenience only.

This scaffold ships the CLI surface and `digivoice doctor`. Recording, transcription, paste, and Piper playback land in later PRs.

## Requirements

- Python 3.12+
- macOS for real microphone, paste, and TCC prompts
- `whisper-cli` on `PATH` (whisper.cpp)
- `piper` on `PATH`, or an executable at `~/.local/bin/piper`
- `sox` or `ffmpeg` for microphone capture
- Default dictation model `ggml-base.en` (snappy push-to-talk), stored as `ggml-base.en.bin`

Linux can run `doctor` and the stubs. Microphone capture and focused-app paste are macOS work.

## Paths

Runtime data stays under Application Support on macOS. Linux uses the XDG data home.

| | macOS | Linux |
| --- | --- | --- |
| Data directory | `~/Library/Application Support/digivoice/` | `${XDG_DATA_HOME:-~/.local/share}/digivoice/` |
| Models | `~/Library/Application Support/digivoice/models/` | `~/.local/share/digivoice/models/` |
| History | `~/Library/Application Support/digivoice/history.jsonl` | `~/.local/share/digivoice/history.jsonl` |
| Default model file | `.../models/ggml-base.en.bin` | same filename under the Linux models directory |

`DIGIVOICE_DATA_DIR`, when set, replaces the data directory on every platform. Models are `models/` inside it, and history is `history.jsonl` inside it.

Put `ggml-base.en.bin` in the models directory (a symlink to a whisper.cpp checkout is enough). Piper voice files (`.onnx` plus the matching `.onnx.json`) can live there too. Model files stay out of git.

Planned history records (written in a later PR):

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":null}
{"ts":"2026-09-30T12:00:01.000Z","kind":"speak","text":"…"}
```

## Commands

From the repo root, after the workspace install (`uv sync --all-packages` or `pip install -e ./digivoice`):

```bash
digivoice doctor
digivoice dict --hold
digivoice speak --clipboard
digivoice history --last 20
```

Without an install, the module entry is `PYTHONPATH=digivoice/src python -m digivoice doctor`.

| Command | This PR |
| --- | --- |
| `digivoice doctor` | Checks `whisper-cli`, `piper`, `sox`, `ffmpeg`, and `ggml-base.en.bin` in the models directory. Prints the history path plus the macOS and Linux defaults. Exit 0 when whisper-cli, piper, sox or ffmpeg, and the default model file are all present. |
| `digivoice dict [--hold\|--toggle]` | Stub. Exit 2. PR1 records audio. |
| `digivoice speak [text\|--clipboard\|--selection]` | Stub. Exit 2. PR2 calls Piper. |
| `digivoice history [--last N] [--grep PATTERN]` | Prints the JSONL path and acknowledges the filters. Exit 0. PR1 appends entries and applies the filters. |

`doctor` also prints a note that Mic and Accessibility grants are documented in PR3. It does not prompt for them.

## Develop

```bash
pytest tests/dvo/ -m unit -v --tb=short
ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo
```

## Later PRs

- PR1 — microphone to wav, `whisper-cli` with `ggml-base.en`, stdout, paste into the focused app, append `{ts, kind:"dict", text, wav?}` to the history file.
- PR2 — `speak` via Piper for argv text, `--clipboard`, and `--selection`; append `{kind:"speak", text}`.
- PR3 — sample Hammerspoon bindings and the Mic + Accessibility runbook. Suggested binds live there (Right Option hold for dictation, Ctrl+Shift+S for speak) so they stay clear of other local leaders.
