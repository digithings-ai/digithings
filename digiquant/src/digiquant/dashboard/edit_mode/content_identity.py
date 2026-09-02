"""Content identity for edit-mode artifacts (#1749, #1751).

An edit-mode patch can be *structurally* successful and *materially* empty: the
model emits ``set`` ops whose values already hold, or declares
``status="skipped"``, and :func:`~digiquant.olympus.edit_mode.merge.merge_document_patch`
returns a body byte-identical to the prior one. The pipeline then republishes it
under the run date marked ``source="today"``.

This module owns the one question that makes that state visible — *did the body
actually change?* — plus the two provenance keys that record the answer.

Provenance, not regeneration
----------------------------
The design spec explicitly **rejects** an auto-``full`` fallback triggered by
content identity: §5.3.1 ("Patch quality — owner decision #2 — no verbatim
guard") says "Do not implement a post-merge verbatim/drift guard that falls back
to ``full``… Rely on getting good patches consistently instead", and lists
"``unchanged_leaf_ratio`` threshold → auto-``full`` fallback" as *rejected*
(ADR-0019 open Q1, closed as **won't do**).

Nothing here triggers a rewrite, and the distinction matters. What these markers
do is give the *existing* deterministic staleness cap — §5.3.2's hard cap,
``OLYMPUS_STALE_FULL_DAYS`` (default 7, see :mod:`digiquant.olympus.edit_mode.config`)
— an honest input. ``gap_days`` is measured from the last date the content
materially changed instead of the last date a row happened to be written.

That mattered because a no-op republish *reset* the clock. ``prior.date`` comes
from the newest ``documents`` row for the key
(:func:`digiquant.olympus.atlas.supabase_io.load_prior_context`), no-op or not, so
``alt-politician-signals`` published five rows carrying one body across seven days
(2026-07-17 → 07-24) at ``gap_days=1`` every run: the documented hard cap could
never fire, and the loop only broke when the model happened to emit real ops on
07-25. The cap stays purely time-based, which is exactly what the spec
specifies — only its input is corrected.

The markers are prospective
---------------------------
No row published before this shipped carries ``unchanged_since``, so
:func:`prior_content_date` returns ``None`` for every pre-existing frozen chain
and ``gap_days`` falls back to the publish date. A segment frozen today needs a
further ``stale_full_days()`` frozen days before the cap fires. That is
deliberate: back-filling by hashing the ``documents`` window at load time would
make prior resolution O(window) and would force several simultaneous full
regenerations on the first run after deploy.
"""

from __future__ import annotations

from datetime import date
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous jsonb body shapes
)

# ── the two provenance keys ──────────────────────────────────────────────────────────────
#
# Both live in ``documents.payload`` (JSONB), so neither needs a migration — the same
# property #1559 relied on for the digest's ``carried_from`` / ``continuity`` markers. The
# segment models (:mod:`digiquant.olympus.atlas.segments`) declare no ``model_config``, so
# Pydantic's default ``extra="ignore"`` applies and ``spec.output_model.model_validate(body)``
# accepts a marked body rather than rejecting it.
#
# Deliberately NOT fields on ``DocumentPatch``: that model is the LLM's output schema, and
# whether content changed is a deterministic fact the pipeline derives, never something the
# model may assert.
UNCHANGED_FLAG_KEY = "content_unchanged"
UNCHANGED_SINCE_KEY = "unchanged_since"

# Keys excluded from the identity comparison, on BOTH sides.
#
# ``date`` because the caller overwrites it with the run date immediately after the merge —
# comparing it would make every body look changed.
#
# The two markers because ``prior`` is raw JSONB straight from the DB: once a chain is
# marked, the markers are present in ``prior`` and inherited into ``materialized`` by
# ``apply_ops``. Excluding them keeps the comparison about content, and means an op that
# happens to touch a marker path cannot masquerade as a real change and reset the chain
# (nothing rejects such an op — ``extra="ignore"`` on the segment models means the schema
# validator will not catch it either).
NON_CONTENT_KEYS = frozenset({"date", UNCHANGED_FLAG_KEY, UNCHANGED_SINCE_KEY})

__all__ = [
    "NON_CONTENT_KEYS",
    "UNCHANGED_FLAG_KEY",
    "UNCHANGED_SINCE_KEY",
    "bodies_match",
    "clear_unchanged",
    "content_fingerprint",
    "mark_unchanged",
    "prior_content_date",
]


def content_fingerprint(body: dict[str, Any]) -> dict[str, Any]:
    """*body* with :data:`NON_CONTENT_KEYS` removed — the comparable part."""
    return {k: v for k, v in body.items() if k not in NON_CONTENT_KEYS}


def bodies_match(prior: dict[str, Any], materialized: dict[str, Any]) -> bool:
    """Whether *materialized* is content-identical to *prior*.

    Plain ``==`` on the fingerprints: both sides are JSON-shaped dicts, so equality is
    structural and recursive. No hashing — a hash would only add a collision surface and
    a serialisation-order dependency to a comparison that is already exact.
    """
    return content_fingerprint(prior) == content_fingerprint(materialized)


def prior_content_date(payload: dict[str, Any], published_date: date) -> date:
    """The date *payload*'s content last materially changed.

    ``unchanged_since`` when the row carries a usable one, else *published_date* — which
    is the honest answer for a row published before these markers existed, and for a row
    whose content genuinely changed on its publish date.
    """
    raw = payload.get(UNCHANGED_SINCE_KEY)
    if isinstance(raw, str) and raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            # A malformed marker must not break prior resolution: fall back to the publish
            # date, which is the pre-#1749 behaviour.
            return published_date
    return published_date


def mark_unchanged(
    body: dict[str, Any],
    *,
    prior: dict[str, Any],
    prior_date: date,
) -> None:
    """Stamp *body* in place as content-unchanged since *prior*'s own unchanged-since date.

    Propagating — not resetting — is the whole point: a chain frozen for six days keeps the
    date it froze on, so ``gap_days`` accumulates and the §5.3.2 cap eventually fires.
    """
    body[UNCHANGED_FLAG_KEY] = True
    body[UNCHANGED_SINCE_KEY] = prior_content_date(prior, prior_date).isoformat()


def clear_unchanged(body: dict[str, Any]) -> None:
    """Strip the markers from *body* in place — content changed, so the chain is broken.

    Necessary because ``apply_ops`` copies the prior body: without this a marker set once
    would ride forward through every subsequent real edit and permanently understate the
    content date.
    """
    body.pop(UNCHANGED_FLAG_KEY, None)
    body.pop(UNCHANGED_SINCE_KEY, None)
