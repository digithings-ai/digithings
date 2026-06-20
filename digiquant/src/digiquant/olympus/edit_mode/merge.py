"""Patch merge — wraps :func:`digiquant.olympus.edit_mode.ops.apply_ops`."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.edit_mode.models import DocumentPatch, MergeResult, MergeStats
from digiquant.olympus.edit_mode.ops import apply_ops


class MergeError(ValueError):
    """Raised when patch ops cannot be applied deterministically."""


def _assert_no_duplicate_set_paths(patch: DocumentPatch) -> None:
    seen: set[str] = set()
    for op in patch.ops:
        if op.op != "set":
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
    else:
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
