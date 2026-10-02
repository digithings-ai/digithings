"""Transcribe a wav with whisper-cli and the configured local ggml weights.

`whisper-cpp` is accepted as an alias because distributions disagree on the
binary name. stdout carries the transcript; the banner and model loading chatter
go to stderr, so only stdout is parsed. English `.en` models use `-l en`;
multilingual catalog models use `-l auto`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from digivoice.catalog import stt_language, stt_model_path
from digivoice.errors import EmptyTranscriptError, TranscribeError
from digivoice.installed_models import find_local_weight
from digivoice.models import Transcript
from digivoice.paths import DEFAULT_MODEL, VoicePaths, local_bin
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

WHISPER_BINARIES = ("whisper-cli", "whisper-cpp")
LANGUAGE = "en"
TRANSCRIBE_TIMEOUT = 300.0
# `[00:00:00.000 --> 00:00:02.500]` when a build ignores -nt.
_SEGMENT_PREFIX = re.compile(r"\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*")


# whisper.cpp prints these markers for silence instead of an empty string. They are
# not speech, so a take that only contains them is an empty take.
_MARKER_WORDS = r"blank[_ ]audio|silence|no speech|inaudible"
_NON_SPEECH_MARKER = re.compile(
    rf"\[\s*(?:{_MARKER_WORDS})\s*\]|\(\s*(?:{_MARKER_WORDS})\s*\)", re.IGNORECASE
)


def whisper_argv(binary: str, model: Path, wav: Path, *, language: str = LANGUAGE) -> list[str]:
    return [
        binary,
        "-m",
        str(model),
        "-f",
        str(wav),
        "-l",
        language,
        "-nt",
    ]


def select_whisper(probe: CommandProbe, home: Path | None = None) -> str | None:
    for name in WHISPER_BINARIES:
        found = probe.lookup(name)
        if found:
            return found
    if home is None:
        return None
    fallback = local_bin(home) / "whisper-cli"
    if probe.executable(str(fallback)):
        return str(fallback)
    return None


def clean_transcript(raw: str) -> str:
    """Strip segment timestamps and silence markers, collapse the remaining line breaks."""
    without_prefixes = _SEGMENT_PREFIX.sub(" ", raw)
    without_markers = _NON_SPEECH_MARKER.sub(" ", without_prefixes)
    return " ".join(without_markers.split())


def model_file(
    paths: VoicePaths,
    model_id: str | None = None,
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Weights for this model. models_dir first, then a copy already installed locally."""
    chosen = stt_model_path(paths.models_dir, model_id)
    if chosen.is_file() or home is None:
        return chosen
    raw = (model_id or "").strip()
    if raw and Path(raw).expanduser().is_absolute():
        return chosen
    found = find_local_weight(home, env, chosen.name)
    return found if found is not None else chosen


def transcribe(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    wav_path: str,
    model_id: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Transcript:
    """Run whisper-cli over `wav_path` and return the transcript text."""
    binary = select_whisper(probe, home)
    if binary is None:
        raise TranscribeError(
            "whisper-cli not on PATH (whisper.cpp binary name is whisper-cli, "
            "whisper-cpp also accepted)"
        )
    chosen = model_id or DEFAULT_MODEL
    model = model_file(paths, chosen, home=home, env=env)
    if not model.is_file():
        raise TranscribeError(f"model {chosen} is not installed locally: {model}")
    argv = whisper_argv(binary, model, Path(wav_path), language=stt_language(chosen))
    result = runner(argv, timeout=TRANSCRIBE_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise TranscribeError(f"whisper-cli failed ({reason})")
    text = clean_transcript(result.stdout)
    if not text:
        raise EmptyTranscriptError("whisper-cli returned no text; nothing was recognized")
    return Transcript(
        text=text,
        model=chosen,
        model_path=str(model),
        wav_path=wav_path,
        argv=list(argv),
    )
