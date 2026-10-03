"""Transcribe a wav with whisper-cli and the configured STT weights.

Default model id is `ggml-base.en` (`ggml-base.en.bin`). `settings.stt_model`
selects another local ggml file. `whisper-cpp` is accepted as an alias because
distributions disagree on the binary name. stdout carries the transcript; the
banner and model loading chatter go to stderr, so only stdout is parsed.
"""

from __future__ import annotations

import re
from pathlib import Path

from digivoice.errors import EmptyTranscriptError, TranscribeError
from digivoice.models import Transcript
from digivoice.paths import VoicePaths, resolve_stt_model_path, stt_model_id
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
    """Strip segment timestamps and silence markers, collapse the remaining line breaks."""
    without_prefixes = _SEGMENT_PREFIX.sub(" ", raw)
    without_markers = _NON_SPEECH_MARKER.sub(" ", without_prefixes)
    return " ".join(without_markers.split())


def model_file(paths: VoicePaths, model_id: str | None = None) -> Path:
    return resolve_stt_model_path(paths, model_id)


def transcribe(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    wav_path: str,
    model_id: str | None = None,
) -> Transcript:
    """Run whisper-cli over `wav_path` and return the transcript text.

    `model_id` is `settings.stt_model` (default `ggml-base.en`).
    """
    binary = select_whisper(probe)
    if binary is None:
        raise TranscribeError(
            "whisper-cli not on PATH (whisper.cpp binary name is whisper-cli, "
            "whisper-cpp also accepted)"
        )
    label = stt_model_id(model_id)
    model = model_file(paths, model_id)
    if not model.is_file():
        raise TranscribeError(f"stt model {label} missing: {model}")
    argv = whisper_argv(binary, model, Path(wav_path))
    result = runner(argv, timeout=TRANSCRIBE_TIMEOUT)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise TranscribeError(f"whisper-cli failed ({reason})")
    text = clean_transcript(result.stdout)
    if not text:
        raise EmptyTranscriptError("whisper-cli returned no text; nothing was recognized")
    return Transcript(
        text=text,
        model=label,
        model_path=str(model),
        wav_path=wav_path,
        argv=list(argv),
    )
