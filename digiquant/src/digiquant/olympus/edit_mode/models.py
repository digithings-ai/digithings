"""Pydantic models for Olympus edit-mode continuity (spec §5.2)."""

from __future__ import annotations

from datetime import date
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    Any,
    Literal,
)

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

PatchOpType = Literal["set", "append", "remove"]
# RFC 6902 names the write verb ``add``. This module's ``set`` is that verb
# (object replace-or-insert, and ``/-`` / past-end list append). House GHA
# 33426508863 rejected ``ops.6.op='add'`` and regenerated the segment.
_PATCH_OP_SYNONYMS: dict[str, PatchOpType] = {"add": "set"}
EditMode = Literal["full", "edit", "skip"]
ArtifactKey = tuple[str, str]
FullArtifactBody = dict[str, Any]


class PatchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: PatchOpType
    path: str = Field(max_length=512, description="JSON Pointer, RFC 6901")
    value: Any | None = None
    # Free prose — no max_length / soft-truncate. A 240-char hard cap used to
    # discard entire DocumentPatches (#1740); truncating just reintroduces loss.
    reason: str | None = None

    @field_validator("op", mode="before")
    @classmethod
    def _normalize_op(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        token = v.strip().lower()
        return _PATCH_OP_SYNONYMS.get(token, token)


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
    one_line_summary: str | None = None
    signals_checked: list[str] = Field(default_factory=list)


class MergeStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ops_applied: int = 0
    paths_touched: list[str] = Field(default_factory=list)
    content_changed: bool = Field(
        default=True,
        description=(
            "Whether the merge actually altered the prior body's content (#1749/#1751). "
            "``ops_applied`` counts ops SUBMITTED, so a patch can report six applied ops "
            "and change nothing — 54 of 69 frozen production rows were exactly that. "
            "Defaults True so an unset value never mislabels a real edit as frozen."
        ),
    )


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
    content_date: date | None = Field(
        default=None,
        description=(
            "The date this payload's content last materially changed, from its "
            "``unchanged_since`` marker (#1749). ``None`` when the row carries no marker — "
            "every row published before the marker existed, and every row whose content "
            "changed on its own publish date. ``resolve_edit_mode`` measures ``gap_days`` "
            "from this when present so a no-op republish cannot reset the staleness clock."
        ),
    )


class TriageSignal(BaseModel):
    """Per-artifact triage hint consumed by :func:`resolve_edit_mode`."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["quiet", "stale"]


ArtifactEditOutput = DocumentPatch | FullArtifactBody
