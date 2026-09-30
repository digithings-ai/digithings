"""Pydantic models for digivoice paths and the doctor report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["ok", "missing", "info"]


class VoicePaths(BaseModel):
    data_dir: str
    models_dir: str
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
