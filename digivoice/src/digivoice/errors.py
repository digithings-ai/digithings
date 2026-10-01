"""Failures the CLI turns into a one-line message and a non-zero exit code."""

from __future__ import annotations


class VoiceError(Exception):
    """A digivoice step failed. `message` is already user-facing."""


class CaptureError(VoiceError):
    """Microphone capture failed: no tool, no device, or a tool that errored."""


class TranscribeError(VoiceError):
    """whisper-cli was missing, errored, or recognized no speech."""


class SpeakError(VoiceError):
    """Piper was missing, the voice file was missing, or playback failed."""
