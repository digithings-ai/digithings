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


class InstallStamp(BaseModel):
    """Record of the last `digivoice install` / `update` on this machine."""

    tip_sha: str
    adapter_source: str
    adapter_target: str
    cli: str = "digivoice"
