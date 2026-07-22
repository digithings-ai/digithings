"""Patch merge — wraps :func:`digiquant.olympus.edit_mode.ops.apply_ops`."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes

from pydantic import BaseModel

from digiquant.olympus.edit_mode.models import DocumentPatch, MergeResult, MergeStats
from digiquant.olympus.edit_mode.ops import apply_ops


class MergeError(ValueError):
    """Raised when patch ops cannot be applied deterministically."""


def coerce_document_patch(result: BaseModel | DocumentPatch) -> DocumentPatch:
    """Normalize LLM output to a :class:`DocumentPatch`."""
    if isinstance(result, DocumentPatch):
        return result
    return DocumentPatch.model_validate(result.model_dump(mode="json"))


def section_index(body: dict[str, Any]) -> dict[str, str]:
    """Compact top-level index for edit-mode hybrid prompts."""
    index: dict[str, str] = {}
    for key, val in body.items():
        if isinstance(val, str) and val:
            index[key] = val[:120]
        elif isinstance(val, list):
            index[key] = f"list(len={len(val)})"
        elif isinstance(val, dict):
            index[key] = f"object(keys={len(val)})"
    return index


def _assert_no_duplicate_set_paths(patch: DocumentPatch) -> None:
    seen: set[str] = set()
    for op in patch.ops:
        if op.op != "set":
            continue
        # ``/-`` is the RFC 6901 append position: repeated sets there are sequential
        # appends, not conflicting writes on one element (#1641).
        if op.path.split("/")[-1] == "-":
            continue
        if op.path in seen:
            msg = f"duplicate set on path {op.path!r} in one patch"
            raise MergeError(msg)
        seen.add(op.path)


def merge_document_patch(
    prior: dict[str, Any],
    patch: DocumentPatch,
    *,
    schema_validator: Callable[[dict[str, Any]], None] | None = None,
) -> MergeResult:
    """Apply *patch* to *prior* and return materialized body + telemetry."""
    if patch.status == "skipped":
        materialized = deepcopy(prior)
        stats = MergeStats(ops_applied=0, paths_touched=[])
        if schema_validator is not None:
            schema_validator(materialized)
        return MergeResult(materialized=materialized, delta=patch, merge_stats=stats)

    _assert_no_duplicate_set_paths(patch)
    ops_payload = [op.model_dump(mode="json", exclude_none=True) for op in patch.ops]
    try:
        materialized = apply_ops(prior, ops_payload)
    except ValueError as exc:
        raise MergeError(str(exc)) from exc
    paths = [op.path for op in patch.ops]
    stats = MergeStats(ops_applied=len(patch.ops), paths_touched=paths)

    if schema_validator is not None:
        schema_validator(materialized)

    return MergeResult(materialized=materialized, delta=patch, merge_stats=stats)
