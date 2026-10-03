# digivoice

Local speech tools for digithings. Mac-first command line for dictation (whisper.cpp), speech (Piper), and an append-only session history. Any terminal can call it. Sample Hammerspoon hotkeys live under [`hammerspoon/`](hammerspoon/) — not inside the Python package core.

Speech stays on the machine. digivoice does not call a cloud STT or TTS service, and it does not depend on Super Whisper. OpenCode's `@renjfk/opencode-voice` plugin is optional convenience only.

Dictation and speech are live: microphone → wav → `whisper-cli` with `ggml-base.en` → paste + history; Piper playback for `speak` with history `kind:speak`.

## Install

macOS is the desktop this app runs on. Hotkeys and paste go through Hammerspoon. There is no Windows or Linux package for those hotkeys.

From the repository root, one command installs the tool, the auto toolchain, and reloads Hammerspoon. It exits 0 when that finishes. It does not open the wizard and it does not leave a TUI running:

```bash
uv tool install --editable ./digivoice && export PATH="$HOME/.local/bin:$PATH" && digivoice install --auto
```

`uv tool install --editable` puts `digivoice` on `PATH` from this checkout (`~/.local/bin`), which is required because the Hammerspoon adapter is copied from that tree. `digivoice install --auto` is the existing non-interactive install: bun, OpenTUI, whisper-cli, Piper, sox, `ggml-base.en.bin`, the Lessac voice, and the Hammerspoon adapter, then `hs.reload()` so the hotkeys are live. On an arm64 Mac it installs the native arm64 Piper build and a same-arch `libespeak-ng.1.dylib` beside that binary. A missing same-arch library is `brew install espeak-ng`. It also places a same-arch `libpiper_phonemize.1.dylib` beside that binary, copying it out of the Piper archive when the archive contains it and otherwise from the arm64 piper-jni build. An x86_64 library is not used. It does not download a rewrite model, and it does not call a cloud STT or TTS service.

Once a GitHub release tag exists, the same auto install uses that tag. `<tag>` is the release tag, not a moving branch. The package name is `digivoice` (`digivoice/pyproject.toml`). The repository root is the workspace, so the git URL names `subdirectory=digivoice`. The `digivoice` binary lands in `~/.local/bin`:

```bash
uv tool install --from "git+https://github.com/digithings-ai/digithings.git@<tag>#subdirectory=digivoice" digivoice && digivoice install --auto
```

`digivoice install` on a terminal is still the wizard. `--auto` is the non-interactive path in both lines above. **Auto** there is the same default set. **Pick** asks which local speech, voice, and rewrite models to download. Models already on disk stay. Choosing a model does not delete one you did not choose. A pipe or `DIGIVOICE_INSTALL_NONINTERACTIVE=1` skips the wizard and installs the auto set, the same path as `--auto`. `digivoice update` refreshes that same default set and does not open the wizard.

## Requirements

- Python 3.12+
- macOS for real microphone capture, paste, and TCC prompts
- `whisper-cli` on `PATH` (whisper.cpp); `whisper-cpp` is accepted as an alias
- `piper` on `PATH`, or an executable at `~/.local/bin/piper`
- A Piper voice `.onnx` (set `DIGIVOICE_PIPER_VOICE`, or place under the models directory)
- `sox` or `ffmpeg` for microphone capture; `afplay` (macOS) or `aplay`/`ffplay` (Linux) for playback
- Default dictation model `ggml-base.en` (snappy push-to-talk), stored as `ggml-base.en.bin`

`digivoice install` fetches that local set when you choose auto, or when a script runs it with no terminal: bun and the OpenTUI packages, whisper-cli, Piper, sox, `ggml-base.en.bin`, and the Lessac voice. On macOS, a same-arch `libespeak-ng.1.dylib` is copied beside the real Piper binary; a missing one is `brew install espeak-ng`. A library of a different architecture is not used. It does not download a rewrite model on that path and it does not call a cloud STT or TTS service. A failed step does not stop the rest; the command exits 1 when any step failed. The wizard's pick path can also download a local rewrite file you choose, and it leaves models already on disk in place.

Linux runs `doctor`, `dict`, `speak`, and `history` with a sound card and ALSA. Paste is skipped there — the transcript is on stdout. A Linux box with no microphone fails with a message and exit 1 instead of hanging.

## Paths

Runtime data stays under Application Support on macOS. Linux uses the XDG data home.

| | macOS | Linux |
| --- | --- | --- |
| Data directory | `~/Library/Application Support/digivoice/` | `${XDG_DATA_HOME:-~/.local/share}/digivoice/` |
| Models | `~/Library/Application Support/digivoice/models/` | `~/.local/share/digivoice/models/` |
| Recordings | `~/Library/Application Support/digivoice/recordings/` | `~/.local/share/digivoice/recordings/` |
| History | `~/Library/Application Support/digivoice/history.jsonl` | `~/.local/share/digivoice/history.jsonl` |
| Toggle stop-file | `…/digivoice/dict.stop` | same under the Linux data directory |
| Default model file | `.../models/ggml-base.en.bin` | same filename under the Linux models directory |

`DIGIVOICE_DATA_DIR`, when set, replaces the data directory on every platform. Models are `models/` inside it, recordings are `recordings/`, and history is `history.jsonl`.

Put `ggml-base.en.bin` in the models directory (a symlink to a whisper.cpp checkout is enough). Piper voice files (`.onnx` plus the matching `.onnx.json`) can live there too, or set:

```bash
export DIGIVOICE_PIPER_VOICE="$HOME/Library/Application Support/digivoice/models/en_US-lessac-medium.onnx"
```

Model files and recorded wavs stay out of git.

History records, one JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":".../recordings/dict-20260930T120000Z-1a2b3c4d.wav"}
{"ts":"2026-09-30T12:00:01.000Z","kind":"speak","text":"…","wav":null}
```

## Commands

From the repo root, after the workspace install (`uv sync --all-packages` or `pip install -e ./digivoice`):

```bash
digivoice doctor
digivoice dict --hold
digivoice dict --toggle --no-paste
digivoice speak "hello from digivoice"
digivoice speak --clipboard
digivoice speak --selection
digivoice history --last 20
digivoice history --grep invoice
digivoice history --copy-last
digivoice history --json
digivoice settings
digivoice settings get rewrite_enabled
digivoice settings set rewrite_enabled true
digivoice logs
digivoice setup --print
digivoice setup --json
digivoice doctor
```

Without an install, the module entry is `PYTHONPATH=digivoice/src python -m digivoice doctor`.

| Command | Behavior |
| --- | --- |
| `digivoice doctor` | Checks `whisper-cli`, `piper`, `sox`, `ffmpeg`, `ggml-base.en.bin`, settings validity, hotkey docs, and the Hammerspoon adapter. Prints the history path, the recordings directory, and the macOS and Linux defaults. Exit 0 when whisper-cli, piper, sox or ffmpeg, and the default model file are all present. |
| `digivoice dict [--hold\|--toggle] [--seconds N] [--stop-file PATH] [--no-paste]` | Records the microphone to `recordings/*.wav`, runs `whisper-cli`, prints the transcript on stdout, appends `{ts, kind:"dict", text, wav}` to the history file, and pastes into the focused app on macOS. `--toggle` stops early when the stop-file is touched or SIGINT/SIGTERM arrives. Exit 0 once a transcript exists. |
| `digivoice speak [text\|--clipboard\|--selection\|--clipboard-or-history]` | Piper synthesis + local playback. Appends `{kind:"speak", text}`. Exit 0 on success. |
| `digivoice history [--last N] [--grep PATTERN] [--copy-last] [--json]` | Lists entries, newest last. `--copy-last` copies the latest dict transcript to the clipboard. `digivoice history --json` prints entries and does not open the TUI. |
| `digivoice settings get KEY` / `digivoice settings set KEY VALUE` | Read or write one key in `settings.json`. Neither opens the TUI. An unknown key exits non-zero and does not write the file. |
| `digivoice logs` | Prints `system.log`. Never opens the TUI. A missing or empty log prints `No log yet` and exits 0. `digivoice /system/logs` on a TTY still opens the logs screen. |
| `digivoice settings` / `setup` | `settings` shows or changes `settings.json` (models, rewrite on/off + preset + model + runner + auto-route, paste_on_stop, word_detection / spelling_detection stubs default off, live_banner, banner_position, banner_animations). `--json` for agents. `setup` is the interactive wizard (Models / Post-process / Features / Hotkeys / Hardware stub / Review & save / Doctor / Quit, arrow keys + Enter on a TTY); `setup --print` (or `DIGIVOICE_SETUP_NONINTERACTIVE=1`) prints current values + the menu tree with no prompts, exit 0. |
| `digivoice install` | On a terminal, the install wizard. Auto installs the default toolchain, `ggml-base.en.bin`, and the Lessac voice. Pick downloads the local speech, voice, and rewrite models you choose and does not delete models already on disk. `--auto`, a pipe, or `DIGIVOICE_INSTALL_NONINTERACTIVE=1` installs the auto set with no prompts. |
| `digivoice update` | Refreshes bun, OpenTUI, whisper-cli, Piper, sox, and the default local models when they are missing or older than the pin. On an arm64 Mac it replaces an x86_64 vendor Piper with the native arm64 build, copies a same-arch `libespeak-ng.1.dylib` beside that binary, and installs espeak-ng when that library is missing. It upgrades the formula when this command installed it. Then it copies the Hammerspoon adapter into `~/.hammerspoon/digivoice` and runs `hs.reload()`. No wizard. Exit 1 when a step fails. |
| `digivoice cancel` | Creates the cancel-file: a running `dict` discards its take (no paste, no history entry, wav deleted). Esc in the Hammerspoon sample does the same. |
| `digivoice status` | Prints the `status.json` snapshot the banner reads. |

### Agents

These commands never open the TUI, including when stdin is a TTY:

```bash
digivoice install --auto
digivoice settings get KEY
digivoice settings set KEY VALUE
digivoice logs
digivoice history --json
```

`digivoice install --auto` installs the auto toolchain with no wizard. An unknown settings key exits non-zero and does not write `settings.json`. `digivoice logs` prints `No log yet` when the log is missing or empty, and exits 0.

### dict

`--hold` and `--toggle` pick a recording length cap — 15s and 60s, 30s with neither — and `--seconds N` overrides it. Toggle also watches a stop-file (default `{data_dir}/dict.stop`) and SIGINT/SIGTERM so Hammerspoon can press-to-start / press-to-stop. The cap keeps a stuck microphone from hanging the CLI.

stdout is the transcript and nothing else:

```bash
digivoice dict --hold | pbcopy     # skip the paste entirely
digivoice dict --hold > note.txt   # progress is on stderr
```

stderr carries the recording length, the model used, the paste result, and the history path. A denied Accessibility grant, a missing `pbcopy`, or a non-macOS host is a note, not a failure — the transcript is already on stdout and `pbcopy` left it in the clipboard. Missing capture tools, a locked-down microphone, a missing model file, a whisper failure, and silence all exit 1 with one line on stderr.

### speak

```bash
digivoice speak "ship the release notes"
digivoice speak --clipboard
digivoice speak --selection              # hotkey path: selection only
```

Needs `piper` and a voice file (`DIGIVOICE_PIPER_VOICE` or `*.onnx` under models) plus `afplay` / `aplay` / `ffplay`. On macOS, speak points Piper at a same-arch `libespeak-ng.1.dylib` already on the machine. stdout is the spoken text; history gets `kind:speak`.

`--selection` is the Hammerspoon speak hotkey path: speak the current selection
only (on macOS, Cmd+C via osascript counts only when the clipboard changes). Empty
selection fails soft — no clipboard and no `kind:dict` history fallback. For
OpenCode / Claude / Cursor, select the reply text then double-tap Left Option.
`--clipboard-or-history` still reads the clipboard only (no history fallback) for
CLI callers; it is not the hotkey command.

### Post-STT rewrite (optional, local only)

Disabled by default. When enabled, digivoice runs the **shipped local** GGUF
(`qwen2.5-1.5b-instruct-q4_k_m.gguf` under the models directory) via llama.cpp
(or local ollama) after whisper and before paste. The pass keeps the dictated
words and only lightly fixes grammar and spelling. A preset (`email`, `sms`,
`professional`, `coding`, `blog`, `none`) is a format, not a request to write
something new. Optional `rewrite_auto_route` picks a
preset from the focused app using `rewrite_app_routes` in settings. Fail soft:
raw transcript if the runner/model is missing or errors. No cloud LLM, no
OpenRouter, no user URL — `doctor` reports when the local GGUF is not installed.
Timeout is off by default; enable it to cycle 15 / 30 / 60 seconds.

```bash
digivoice settings set rewrite_enabled true
digivoice settings set rewrite_runner llama.cpp
digivoice settings set rewrite_model qwen2.5-1.5b-instruct-q4_k_m.gguf
digivoice settings set rewrite_preset email
digivoice settings set rewrite_auto_route true
digivoice settings set rewrite_timeout_seconds 30
```

### Cancel and empty takes

Esc (Hammerspoon sample) or `digivoice cancel` discards an active take: the recorder or `whisper-cli` is stopped, the wav is deleted, nothing is pasted, and no history line is written. `dict` exits 3. An empty recognition (silence, `[BLANK_AUDIO]`, a blank rewrite) is discarded the same way (exit 1, wav deleted) — a blank is never pasted or logged.

### Status banner

`dict` and `speak` write `status.json` for the Hammerspoon banner (display only). Settings:

```bash
digivoice settings set live_banner false          # no overlay at all (hotkeys still armed)
digivoice settings set banner_position top-right  # top-center (default), top-left, top-right,
                                                  # bottom-center, bottom-left, bottom-right, center
digivoice settings set banner_animations false    # still grid frame instead of animation
digivoice settings set banner_pinned true         # keep the icon up (default false, retracts when idle)
```

Read per take — no Hammerspoon reload needed for settings. See [`hammerspoon/README.md`](hammerspoon/README.md).

### Interrupt safety

Stopping a toggle capture (Right Option again / stop-file / SIGINT) **keeps the wav** and continues transcribe → optional rewrite → paste of what was captured. Resume-same-take is not supported — paste what you have and start a new take. There is no UX time limit on toggle (long dictation works); on the sox path ~10s of silence pauses the take instead of cutting mid-speech.

### Hotkeys (sample)

See [`hammerspoon/README.md`](hammerspoon/README.md):

- **Right Option** → dict toggle (stop-file) with a status banner for the whole capture
- **Esc** → cancel the active take (discard; no paste, no history)
- **Double-tap Left Option** → speak `--selection` (fail soft; the banner says if nothing is selected; no clipboard or dict history)

Mic + Accessibility TCC steps are documented there.

## Develop

```bash
pytest tests/dvo/ -m unit -v --tb=short
ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo
```

Tests inject a fake probe and a fake command runner, plus tiny shell scripts standing in for recorders / whisper / piper / players, so the suite never needs a microphone, a sound card, model weights, or a clipboard.
