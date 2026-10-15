---
type: service-architecture
title: digivoice Architecture
description: Module map of the digivoice CLI. Local whisper.cpp and Piper. No network service and no port.
tags: [digivoice, cli, architecture]
sources:
  - id: openwiki-source-digivoice-arch
    resource: repo://digivoice/ARCHITECTURE.md
  - id: openwiki-source-digivoice-paths
    resource: repo://digivoice/src/digivoice/paths.py
  - id: openwiki-source-digivoice-cli
    resource: repo://digivoice/src/digivoice/cli.py
generated: { by: "DIG-3433", at: "2026-10-14T05:10:00.000Z" }
---

# digivoice Architecture

Local CLI package at `digivoice/`. No network service and no port. Console
script `digivoice` (`python -m digivoice`). Python 3.12. Pydantic v2 models
live in `models.py`.

## Module map

| File | Role |
|------|------|
| `cli.py` | Argv dispatch. `doctor`, `dict`, `speak`, `history`, `install`, `status` |
| `capture.py` | Microphone to wav. `sox` first, then `ffmpeg` |
| `transcribe.py` | `whisper-cli` over a wav |
| `speak.py` | Piper synthesis and a local player (`afplay` / `aplay` / `ffplay`) |
| `paths.py` | Data, models, recordings, and history locations |
| `history.py` | Append-only JSONL session history |
| `install.py` | Local toolchain install. No cloud STT or TTS |
| `runner.py` | `CommandRunner`. External binaries are argv lists, not a shell |
| `hammerspoon/` | Sample hotkey adapter. Not part of the Python package core |

The full screen and menu behavior is in `digivoice/ARCHITECTURE.md`. This
page does not repeat it.

## Where data lives

On macOS the data directory is `~/Library/Application Support/digivoice/`.
The default dictation model file is `models/ggml-base.en.bin`.
`DIGIVOICE_DATA_DIR` overrides the directory on every platform.
`DIGIVOICE_PIPER_VOICE` points at a Piper `.onnx` voice. `doctor` does not
create directories. `dict`, `speak`, and `history` do, because those
commands write.

## What it will not do

digivoice does not open a socket, does not call a cloud speech API, and
does not depend on a hosted STT or TTS product. Paste and hotkeys are
macOS-only. Tests inject a fake `CommandRunner` so they do not need a
microphone, a model file, or a clipboard.
