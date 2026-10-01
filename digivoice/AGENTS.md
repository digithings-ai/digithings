# Agent Guide: digivoice

## Purpose

digivoice is a local CLI for dictation and speech on macOS. It shells out to whisper.cpp (`whisper-cli`) and Piper. The default dictation model is `ggml-base.en` (`ggml-base.en.bin`). Session history is an append-only JSONL file under the data directory. The package lives at `digivoice/` and is a uv workspace member, sibling to digiclaw and digigraph.

`doctor`, `dict`, `speak`, and `history` are live. Sample Hammerspoon hotkeys live under `digivoice/hammerspoon/` (outside the Python package import path). Do not add cloud STT/TTS or put Hammerspoon inside the installable package as a hard dependency.

## Read first

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — paths, CLI, the `dict` / `speak` pipelines, doctor checks, early-stop toggle
2. [`README.md`](README.md) — install paths and how to run commands
3. [`hammerspoon/README.md`](hammerspoon/README.md) — hotkey binds and Mic + Accessibility TCC
4. [`../AGENTS.md`](../AGENTS.md) — stack-wide rules

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
- Piper voices: set `DIGIVOICE_PIPER_VOICE` to a `.onnx` path, or place `*.onnx` (+ matching `.onnx.json`) under the models directory.
- Model files, recorded wavs, and history JSONL stay under the data directory in the README. Do not commit them.
- `doctor` looks up executables with filesystem checks. Do not pass `shell=True` and do not interpolate argv into a shell string.
- Every external binary goes through the `CommandRunner` in `runner.py` (except toggle early-stop, which uses `subprocess.Popen` so SIGINT/stop-file can finish the wav). Keep argv a list, and never interpolate the transcript into an AppleScript or shell string — that is why paste uses `pbcopy` over stdin.
- Every command that can block on hardware bounds itself and fails soft: a missing tool, a denied permission, or silence is a one-line stderr message and a non-zero exit, never a hang and never a traceback.
- `dict` and `speak` keep stdout to the text alone so they can be piped. Progress goes to stderr.
- Public results are Pydantic v2 models in `models.py`. Do not return bare dicts from `doctor`, `run`, or the pipeline stages.
- Tests inject `FakeProbe` and `FakeRunner` from `tests/dvo/fakes.py`. No test may need a real microphone, sound card, model, or clipboard.
- Hotkeys belong in `digivoice/hammerspoon/` (sample adapter), not in the installable Python package. Locked sample binds: Right Option = dict toggle; double-tap Left Option = speak `--selection` (soft-fail if empty; no clipboard/history fallback). Not hold-to-talk; not Ctrl+Shift+Option; not Ctrl+Shift+S.
- Toggle early-stop uses a stop-file (default `{data_dir}/dict.stop`) and/or SIGINT/SIGTERM — not only the length cap.

## Tests

```bash
pytest tests/dvo/ -m unit -v --tb=short
ruff check digivoice/src tests/dvo && ruff format --check digivoice/src tests/dvo
PYTHONPATH=digivoice/src python -m digivoice doctor
```

## More

Paths, check ids, the JSONL shape, and the `dict` / `speak` pipelines are in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that file when a command's behavior changes.
