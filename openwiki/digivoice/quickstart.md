---
type: quickstart
title: digivoice Quickstart
description: Local dictation and speech on this machine. whisper.cpp and Piper. No cloud STT or TTS, and no network port.
tags: [digivoice, cli, speech]
sources:
  - id: openwiki-source-digivoice-readme
    resource: repo://digivoice/README.md
  - id: openwiki-source-digivoice-cli
    resource: repo://digivoice/src/digivoice/cli.py
  - id: openwiki-source-digivoice-pyproject
    resource: repo://digivoice/pyproject.toml
generated: { by: "DIG-3433", at: "2026-10-14T05:10:00.000Z" }
---

# digivoice Quickstart

digivoice is a local CLI. Speech stays on the machine. It does not call a
cloud STT or TTS service. There is no HTTP port.

## Install

From the repository root, on macOS:

```bash
uv tool install --editable ./digivoice && export PATH="$HOME/.local/bin:$PATH" && digivoice install --auto
```

`digivoice install --auto` installs the local toolchain (whisper-cli, Piper,
sox, the default `ggml-base.en` model, a Piper voice) and reloads the
Hammerspoon adapter. It does not open the wizard and it does not download a
rewrite model. A terminal without `--auto` still runs the wizard. A pipe or
`DIGIVOICE_INSTALL_NONINTERACTIVE=1` takes the same auto set.

Python 3.12+ is required. Hotkeys and paste go through Hammerspoon on macOS.
There is no Windows or Linux package for those hotkeys.

## Try it

```bash
digivoice doctor
digivoice dict --seconds 5
digivoice speak "hello"
digivoice history
```

`dict` records the microphone, runs `whisper-cli`, pastes the transcript, and
appends history. `speak` plays through Piper. `doctor` checks the binaries
and the model file and does not create directories.

## Tests

```bash
pytest tests/dvo -m unit
ruff check digivoice && ruff format --check digivoice
```
