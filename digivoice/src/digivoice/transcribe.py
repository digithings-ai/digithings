"""Transcribe a wav with whisper-cli and the ggml-base.en weights.

`whisper-cpp` is accepted as an alias because distributions disagree on the
binary name. stdout carries the transcript; the banner and model loading chatter
go to stderr, so only stdout is parsed.
"""

from __future__ import annotations

import re
from pathlib import Path

from digivoice.errors import TranscribeError
from digivoice.models import Transcript
from digivoice.paths import DEFAULT_MODEL, DEFAULT_MODEL_FILE, VoicePaths
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

WHISPER_BINARIES = ("whisper-cli", "whisper-cpp")
LANGUAGE = "en"
TRANSCRIBE_TIMEOUT = 300.0
# `[00:00:00.000 --> 00:00:02.500]` when a build ignores -nt.
_SEGMENT_PREFIX = re.compile(r"\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*")


def whisper_argv(binary: str, model: Path, wav: Path) -> list[str]:
    return [
        binary,
        "-m",
        str(model),
        "-f",
        str(wav),
        "-l",
        LANGUAGE,
        "-nt",
    ]


def select_whisper(probe: CommandProbe) -> str | None:
    for name in WHISPER_BINARIES:
        found = probe.lookup(name)
        if found:
            return found
    return None


def clean_transcript(raw: str) -> str:
    """Strip segment timestamps and collapse the remaining line breaks."""
    without_prefixes = _SEGMENT_PREFIX.sub(" ", raw)
    return " ".join(without_prefixes.split())


def model_file(paths: VoicePaths) -> Path:
    return Path(paths.models_dir) / DEFAULT_MODEL_FILE


def transcribe(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    wav_path: str,
) -> Transcript:
    """Run whisper-cli over `wav_path` and return the transcript text."""
    binary = select_whisper(probe)
    if binary is None:
        raise TranscribeError(
            "whisper-cli not on PATH (whisper.cpp binary name is whisper-cli, "
            "whisper-cpp also accepted)"
        )
    model = model_file(paths)
    if not model.is_file():
        raise TranscribeError(f"default model {DEFAULT_MODEL} missing: {model}")
    argv = whisper_argv(binary, model, Path(wav_path))
    result = runner(argv, timeout=TRANSCRIBE_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise TranscribeError(f"whisper-cli failed ({reason})")
    text = clean_transcript(result.stdout)
    if not text:
        raise TranscribeError("whisper-cli returned no text; nothing was recognized")
    return Transcript(
        text=text,
        model=DEFAULT_MODEL,
        model_path=str(model),
        wav_path=wav_path,
        argv=list(argv),
    )
