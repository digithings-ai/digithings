"""Non-fabricating legacy research-state inventory backfill (#2870 / WP12.4).

Maps existing ``documents`` (or equivalent) rows into
:class:`~digiquant.olympus.research_retrieval.models.LegacyDocumentRef` inventory
pointers only. Never invents evidence, beliefs, expected events, patches, or
``known_at``. Strict readers continue to exclude the output (WP12.2).

Uses WP12.1 helpers (``content_digest``, ``legacy_document_ref_id``,
``LegacyDocumentRef``) and WP12.2 ``ResearchStateStore.append_legacy_ref`` —
does not redefine identity contracts.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.olympus.research_retrieval.models import (
    LegacyDocumentRef,
    content_digest,
    legacy_document_ref_id,
)
from digiquant.olympus.research_retrieval.store import (
    ResearchStateConflict,
    ResearchStateStore,
)

_AS_OF_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEFAULT_SOURCE_TABLE = "documents"


class LegacySourceDocument(BaseModel):
    """One legacy prose/structured document row eligible for inventory only."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    document_key: str = Field(min_length=0, max_length=500)
    as_of_date: str = Field(min_length=0, max_length=32)
    source_table: str = Field(default=_DEFAULT_SOURCE_TABLE, min_length=1, max_length=200)
    payload: Any = None


class BackfillCounts(BaseModel):
    """Reconciled inventory counters: source == inserted + skipped + unverifiable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: int = Field(ge=0)
    inserted: int = Field(ge=0)
    skipped: int = Field(ge=0)
    unverifiable: int = Field(ge=0)

    @model_validator(mode="after")
    def _reconcile(self) -> BackfillCounts:
        total = self.inserted + self.skipped + self.unverifiable
        if self.source != total:
            raise ValueError(
                f"counts must reconcile: source={self.source} != "
                f"inserted+skipped+unverifiable={total}"
            )
        return self


def _same_legacy_content(existing: LegacyDocumentRef, candidate: LegacyDocumentRef) -> bool:
    return (
        existing.source_hash == candidate.source_hash
        and existing.document_key == candidate.document_key
        and existing.as_of_date == candidate.as_of_date
        and existing.source_table == candidate.source_table
        and existing.known_at is None
        and existing.legacy_manifest_only is True
    )


def build_legacy_document_ref(source: LegacySourceDocument) -> LegacyDocumentRef | None:
    """Hash a source row into a :class:`LegacyDocumentRef`, or ``None`` if unverifiable.

    Unverifiable when key/date are blank, ``as_of_date`` is not ``YYYY-MM-DD``, or
    ``payload`` is missing (``None``). Never invents ``known_at``.
    """
    document_key = source.document_key.strip()
    as_of_date = source.as_of_date.strip()
    source_table = source.source_table.strip()
    if not document_key or not as_of_date or not source_table:
        return None
    if _AS_OF_DATE_RE.fullmatch(as_of_date) is None:
        return None
    if source.payload is None:
        return None

    source_hash = content_digest(source.payload)
    return LegacyDocumentRef(
        legacy_ref_id=legacy_document_ref_id(
            document_key=document_key,
            as_of_date=as_of_date,
            source_hash=source_hash,
        ),
        document_key=document_key,
        as_of_date=as_of_date,
        source_table=source_table,
        source_hash=source_hash,
        known_at=None,
        legacy_manifest_only=True,
    )


def backfill_legacy_manifests(
    sources: Sequence[LegacySourceDocument],
    store: ResearchStateStore,
    *,
    apply: bool,
) -> BackfillCounts:
    """Inventory legacy documents into the store without fabricating structured state.

    - Default callers should pass ``apply=False`` (dry-run): counts only, no writes.
    - ``apply=True`` appends new :class:`LegacyDocumentRef` rows via the store.
    - Never writes evidence, belief, expected-event, or patch rows.
    - Idempotent: identical re-runs increment ``skipped``, not ``inserted``.
    """
    inserted = 0
    skipped = 0
    unverifiable = 0

    for source in sources:
        ref = build_legacy_document_ref(source)
        if ref is None:
            unverifiable += 1
            continue

        existing = store.get_legacy_ref(ref.legacy_ref_id)
        if existing is not None:
            if _same_legacy_content(existing, ref):
                skipped += 1
            else:
                unverifiable += 1
            continue

        if apply:
            try:
                store.append_legacy_ref(ref)
            except ResearchStateConflict:
                unverifiable += 1
                continue
        inserted += 1

    return BackfillCounts(
        source=len(sources),
        inserted=inserted,
        skipped=skipped,
        unverifiable=unverifiable,
    )


__all__ = [
    "BackfillCounts",
    "LegacySourceDocument",
    "backfill_legacy_manifests",
    "build_legacy_document_ref",
]
