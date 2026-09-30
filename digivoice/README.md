# digivoice

Local speech tools for digithings. Mac-first command line for dictation (whisper.cpp), speech (Piper), and an append-only session history. Any terminal can call it. Hotkeys are a later adapter, not this package.

Speech stays on the machine. digivoice does not call a cloud STT or TTS service, and it does not depend on Super Whisper. OpenCode's `@renjfk/opencode-voice` plugin is optional convenience only.

Dictation is live: microphone to wav, `whisper-cli` with `ggml-base.en`, the transcript on stdout, a paste into the focused app, and a history entry. Speech is still a stub — Piper playback lands in PR2.

## Requirements

- Python 3.12+
- macOS for real microphone capture, paste, and TCC prompts
- `whisper-cli` on `PATH` (whisper.cpp); `whisper-cpp` is accepted as an alias
- `piper` on `PATH`, or an executable at `~/.local/bin/piper` — needed by PR2, not by `dict`
- `sox` or `ffmpeg` for microphone capture
- Default dictation model `ggml-base.en` (snappy push-to-talk), stored as `ggml-base.en.bin`

Linux runs `doctor`, `dict`, and `history` with a sound card and ALSA. Paste is skipped there — the transcript is on stdout. A Linux box with no microphone fails with a message and exit 1 instead of hanging.

## Paths

Runtime data stays under Application Support on macOS. Linux uses the XDG data home.

| | macOS | Linux |
| --- | --- | --- |
| Data directory | `~/Library/Application Support/digivoice/` | `${XDG_DATA_HOME:-~/.local/share}/digivoice/` |
| Models | `~/Library/Application Support/digivoice/models/` | `~/.local/share/digivoice/models/` |
| Recordings | `~/Library/Application Support/digivoice/recordings/` | `~/.local/share/digivoice/recordings/` |
| History | `~/Library/Application Support/digivoice/history.jsonl` | `~/.local/share/digivoice/history.jsonl` |
| Default model file | `.../models/ggml-base.en.bin` | same filename under the Linux models directory |

`DIGIVOICE_DATA_DIR`, when set, replaces the data directory on every platform. Models are `models/` inside it, recordings are `recordings/`, and history is `history.jsonl`.

Put `ggml-base.en.bin` in the models directory (a symlink to a whisper.cpp checkout is enough). Piper voice files (`.onnx` plus the matching `.onnx.json`) can live there too. Model files and recorded wavs stay out of git.

History records, one JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":".../recordings/dict-20260930T120000Z-1a2b3c4d.wav"}
{"ts":"2026-09-30T12:00:01.000Z","kind":"dict","text":"…","wav":null}
```

## Commands

From the repo root, after the workspace install (`uv sync --all-packages` or `pip install -e ./digivoice`):

```bash
digivoice doctor
digivoice dict --hold
digivoice dict --toggle --no-paste
digivoice speak --clipboard
digivoice history --last 20
digivoice history --grep invoice
```

Without an install, the module entry is `PYTHONPATH=digivoice/src python -m digivoice doctor`.

| Command | Behavior |
| --- | --- |
| `digivoice doctor` | Checks `whisper-cli`, `piper`, `sox`, `ffmpeg`, and `ggml-base.en.bin` in the models directory. Prints the history path, the recordings directory, and the macOS and Linux defaults. Exit 0 when whisper-cli, piper, sox or ffmpeg, and the default model file are all present. |
| `digivoice dict [--hold\|--toggle] [--seconds N] [--no-paste]` | Records the microphone to `recordings/*.wav`, runs `whisper-cli`, prints the transcript on stdout, appends `{ts, kind:"dict", text, wav}` to the history file, and pastes into the focused app on macOS. Exit 0 once a transcript exists. |
| `digivoice speak [text\|--clipboard\|--selection]` | Stub. Exit 2. PR2 calls Piper. |
| `digivoice history [--last N] [--grep PATTERN]` | Lists entries, newest last. `--grep` matches the text case-insensitively and applies before `--last`. Exit 0, including when the file does not exist yet. |

`doctor` also prints a note that Mic and Accessibility grants are documented in PR3. It does not prompt for them.

### dict

`--hold` and `--toggle` pick a recording length cap — 15s and 60s, 30s with neither — and `--seconds N` overrides it. PR3 replaces the cap with a real key release. The cap keeps a stuck microphone from hanging the CLI, and both recorders close the wav themselves at the cap so the header stays valid.

stdout is the transcript and nothing else:

```bash
digivoice dict --hold | pbcopy     # skip the paste entirely
digivoice dict --hold > note.txt   # progress is on stderr
```

stderr carries the recording length, the model used, the paste result, and the history path. A denied Accessibility grant, a missing `pbcopy`, or a non-macOS host is a note, not a failure — the transcript is already on stdout and `pbcopy` left it in the clipboard. Missing capture tools, a locked-down microphone, a missing model file, a whisper failure, and silence all exit 1 with one line on stderr.

`doctor` documents that Mic and Accessibility grants are documented in PR3. It does not prompt for them.

## Develop

```bash
pytest tests/dvo/ -m unit -v --tb=short
ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo
```

Tests inject a fake probe and a fake command runner, plus two tiny shell scripts standing in for `sox` and `whisper-cli`, so the suite never needs a microphone, a sound card, model weights, or a clipboard.

## Later PRs

- PR2 — `speak` via Piper for argv text, `--clipboard`, and `--selection`; append `{kind:"speak", text}`.
- PR3 — sample Hammerspoon bindings, key-release stopping for `--hold`, and the Mic + Accessibility runbook. Suggested binds live there (Right Option hold for dictation, Ctrl+Shift+S for speak) so they stay clear of other local leaders.
