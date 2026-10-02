"""Pydantic models for digivoice paths and the doctor report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["ok", "missing", "info"]
HistoryKind = Literal["dict", "speak"]


class VoicePaths(BaseModel):
    data_dir: str
    models_dir: str
    recordings_dir: str
    history_file: str


class DoctorCheck(BaseModel):
    id: str
    status: CheckStatus
    detail: str


class DoctorReport(BaseModel):
    ok: bool
    checks: list[DoctorCheck] = Field(default_factory=list)
    text: str


class CliResult(BaseModel):
    code: int
    stdout: str
    stderr: str


InstallStatus = Literal["present", "installed", "failed"]


class InstallStep(BaseModel):
    """One piece of a local digivoice install. Never a cloud STT or TTS host."""

    id: str
    status: InstallStatus
    detail: str


class InstallReport(BaseModel):
    steps: list[InstallStep] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(step.status != "failed" for step in self.steps)


class InstallStamp(BaseModel):
    """Versions `digivoice install` last wrote. Update refreshes a step that differs."""

    bun: str = ""
    opentui: str = ""
    whisper: str = ""
    piper: str = ""
    sox: str = ""
    stt: str = ""
    voice: str = ""


class HistoryEntry(BaseModel):
    """One JSONL line. `ts` is ISO-8601 UTC; `wav` is null when there is no file."""

    ts: str
    kind: HistoryKind
    text: str
    wav: str | None = None


class HistoryRead(BaseModel):
    entries: list[HistoryEntry] = Field(default_factory=list)
    skipped: int = 0
    present: bool = True


class CaptureResult(BaseModel):
    wav_path: str
    tool: str
    seconds: int
    argv: list[str] = Field(default_factory=list)
    stopped_early: bool = False


class Transcript(BaseModel):
    text: str
    model: str
    model_path: str
    wav_path: str
    argv: list[str] = Field(default_factory=list)


class PasteResult(BaseModel):
    attempted: bool
    pasted: bool
    detail: str


class SpeakResult(BaseModel):
    text: str
    voice_path: str
    wav_path: str
    player: str
    argv_piper: list[str] = Field(default_factory=list)
    argv_play: list[str] = Field(default_factory=list)


class RewriteResult(BaseModel):
    """Post-STT local rewrite outcome. `applied` is False when disabled or failed soft."""

    text: str
    applied: bool
    preset: str
    detail: str
    runner: str | None = None
    app_name: str | None = None
