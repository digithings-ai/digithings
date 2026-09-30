# Agent Guide: digivoice

## Purpose

digivoice is a local CLI for dictation and speech on macOS. It shells out to whisper.cpp (`whisper-cli`) and Piper. The default dictation model is `ggml-base.en` (`ggml-base.en.bin`). Session history is an append-only JSONL file under the data directory. The package lives at `digivoice/` and is a uv workspace member, sibling to digiclaw and digigraph.

PR0 is the scaffold: `doctor` plus stubs for `dict`, `speak`, and `history`. Do not add recording, transcription, paste, or Piper playback in a drive-by on this package.

## Read first

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — paths, CLI, doctor checks, what is still a stub
2. [`README.md`](README.md) — install paths and how to run `doctor`
3. [`../AGENTS.md`](../AGENTS.md) — stack-wide rules

## Pre-flight

Before editing `digivoice/`:

- [ ] Read `ARCHITECTURE.md` for the command you are changing
- [ ] `pytest tests/dvo/ -m unit -v --tb=short`
- [ ] `ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo`
- [ ] Confirm the diff does not download model weights or commit audio
- [ ] Confirm the diff does not call a cloud STT or TTS endpoint

## Rules

- Product name is lowercase `digivoice` in prose, docs, and the package name.
- Speech stays local: `whisper-cli` and Piper only. No cloud STT/TTS client, API key, or SaaS SDK.
- Super Whisper is not a dependency. Do not shell out to it or read its config.
- OpenCode `@renjfk/opencode-voice` is optional for people who want a TUI binding. digivoice must keep working when that plugin is absent.
- The default model id is `ggml-base.en`. The file doctor requires is `ggml-base.en.bin` inside the models directory.
- Model files and history JSONL stay under the data directory in the README. Do not commit them.
- `doctor` looks up executables with filesystem checks. Do not pass `shell=True` and do not interpolate argv into a shell string.
- Public results are Pydantic v2 models in `models.py`. Do not return bare dicts from `doctor` or `run`.
- Hotkeys belong in the PR3 adapter, not in this CLI.

## Tests

```bash
pytest tests/dvo/ -m unit -v --tb=short
ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo
PYTHONPATH=digivoice/src python -m digivoice doctor
```

## More

Paths, check ids, and the planned JSONL shape are in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that file when a command's behavior changes.
