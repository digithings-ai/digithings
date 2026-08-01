"""Pydantic models for Olympus edit-mode continuity (spec §5.2)."""

from __future__ import annotations

from datetime import date
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Any,
    Literal,
)

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

PatchOpType = Literal["set", "append", "remove"]
EditMode = Literal["full", "edit", "skip"]
ArtifactKey = tuple[str, str]
FullArtifactBody = dict[str, Any]


class PatchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: PatchOpType
    path: str = Field(max_length=512, description="JSON Pointer, RFC 6901")
    value: Any | None = None
    reason: str | None = Field(default=None, max_length=240)

    @field_validator("reason", mode="before")
    @classmethod
    def _truncate_reason(cls, v: object) -> object:
        """Truncate an over-long ``reason`` instead of rejecting the patch (#1740).

        ``reason`` is free prose the model writes to explain one op, and nothing
        downstream parses it. But the 240-char cap is stated in none of the 17
        ``*-edit.md`` skills, so the model overruns it by a handful of characters
        on a regular basis — and because the cap is enforced as a hard schema
        constraint, a single long ``reason`` raised ValidationError and discarded
        the ENTIRE DocumentPatch. That cost 1-4 successfully-researched segments
        per run, and on 2026-07-28 it took out the master digest itself.

        Fail-soft, matching the ``flow_direction`` idiom in
        ``phase2_institutional.py``: an informational field must never fail a
        merge.
        """
        if isinstance(v, str) and len(v) > 240:
            return v[:237] + "..."
        return v


class DocumentPatch(BaseModel):
    """LLM output when edit_mode=edit and patch is sufficient."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = "1.0"
    doc_type: Literal["document_delta"] = "document_delta"
    date: date
    prior_date: date = Field(
        validation_alias=AliasChoices("prior_date", "baseline_date"),
        serialization_alias="prior_date",
    )
    target_document_key: str
    status: Literal["updated", "skipped"]
    skip_reason: str | None = None
    ops: list[PatchOp] = Field(default_factory=list)
    one_line_summary: str | None = Field(default=None, max_length=400)
    signals_checked: list[str] = Field(default_factory=list)


class MergeStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ops_applied: int = 0
    paths_touched: list[str] = Field(default_factory=list)


class MergeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materialized: dict[str, Any]
    delta: DocumentPatch
    merge_stats: MergeStats


class PriorPublished(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    document_key: str
    payload: dict[str, Any]


class TriageSignal(BaseModel):
    """Per-artifact triage hint consumed by :func:`resolve_edit_mode`."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["quiet", "stale"]


ArtifactEditOutput = DocumentPatch | FullArtifactBody
