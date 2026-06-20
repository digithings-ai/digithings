"""Pydantic models for Olympus edit-mode continuity (spec §5.2)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
