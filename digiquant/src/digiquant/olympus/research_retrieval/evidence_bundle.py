"""Build and publish one H5 base ticker evidence bundle (#2892 / WP11.2).

Canonicalizes H5 inputs into a :class:`TickerEvidenceBundle` before the
provider call, optionally persists via :class:`EvidenceBundleStore`, and cites
bundle/evidence IDs on new forecast materializations. Does **not** cut over H6
selection (WP11.3+). Reuses WP11.1 / WP12 identity helpers only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from digiquant.olympus.envcompat import EVIDENCE_BUNDLE_WRITER, env_lookup
from digiquant.olympus.hermes.models.forecast import ForecastTerms
from digiquant.olympus.research_retrieval.models import (
    EvidenceRecord,
    NonEmptyStr,
    NonEmptyText,
    TickerEvidenceBundle,
    TypedProvenance,
    evidence_content_hash,
    evidence_record_id,
    ticker_evidence_bundle_content_hash,
    ticker_evidence_bundle_id,
)
from digiquant.olympus.research_retrieval.store import EvidenceBundleStore

OLYMPUS_EVIDENCE_BUNDLE_WRITER_ENV = "OLYMPUS_EVIDENCE_BUNDLE_WRITER"
_H5_BASE_SOURCE = "h5:base"
# source / authority columns are CHECK (length BETWEEN 1 AND 500) in WP11/WP12 stores.
_SOURCE_MAX_LEN = 500

# Keys that must never become evidence authorities (H5 blinding / anti-leak).
_PORTFOLIO_LEAK_AUTHORITIES = frozenset(
    {
        "held_in_prior_book",
        "active_theses",
        "prior_book",
        "prior_analyst",
        "query_portfolio",
        "portfolio",
    }
)

NonEmptyField: TypeAlias = Annotated[str, Field(min_length=1, max_length=500)]


class H5EvidenceFact(BaseModel):
    """One pre-provider observation eligible for the H5 base bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: NonEmptyStr
    authority: NonEmptyStr
    summary: NonEmptyText
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime

    @field_validator("summary")
    @classmethod
    def _summary_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary must be non-empty")
        return stripped


class EvidenceConflict(BaseModel):
    """Two leaves share source+authority but diverge on summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    left_evidence_id: UUID
    right_evidence_id: UUID
    reason: NonEmptyField = "same_source_authority_divergent_summary"


class MissingEvidenceField(BaseModel):
    """Named input field absent from the H5 acquisition pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: NonEmptyField
    reason: NonEmptyField = "absent_from_h5_inputs"


class H5EvidenceBundleBuild(BaseModel):
    """Canonical build result: immutable base + leaf records + diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle: TickerEvidenceBundle
    evidence: tuple[EvidenceRecord, ...]
    conflicts: tuple[EvidenceConflict, ...] = ()
    missing_fields: tuple[MissingEvidenceField, ...] = ()


def evidence_bundle_writer_enabled() -> bool:
    """Durable store append is on unless explicitly disabled for rollback."""
    raw = env_lookup(EVIDENCE_BUNDLE_WRITER, default="on").strip().lower()
    return raw not in {"off", "0", "false", "no"}


def facts_from_phase_inputs(
    *,
    ticker: str,
    phase_inputs: dict[str, object],
    knowledge_cutoff_at: datetime,
) -> tuple[tuple[H5EvidenceFact, ...], tuple[MissingEvidenceField, ...]]:
    """Extract ticker-scoped facts; refuse portfolio-context authorities."""
    sym = ticker.strip().upper()
    cutoff = knowledge_cutoff_at
    facts: list[H5EvidenceFact] = []
    missing: list[MissingEvidenceField] = []

    web = phase_inputs.get("web_grounding")
    if isinstance(web, dict) and str(web.get("summary") or "").strip():
        summary = str(web["summary"]).strip()
        sources = web.get("sources")
        source_list: list[str]
        if isinstance(sources, list) and sources:
            source_list = [str(item).strip() for item in sources if str(item).strip()]
        else:
            source_list = ["web_grounding"]
            missing.append(
                MissingEvidenceField(
                    field="web_grounding.sources",
                    reason="absent_from_h5_inputs",
                )
            )
        as_of_raw = web.get("as_of")
        event_time = cutoff
        if isinstance(as_of_raw, str) and as_of_raw.strip():
            try:
                # Date-only as_of → cutoff clock on that UTC day boundary awareness.
                from datetime import UTC, date

                day = date.fromisoformat(as_of_raw.strip()[:10])
                event_time = datetime(day.year, day.month, day.day, tzinfo=UTC)
                if event_time > cutoff:
                    event_time = cutoff
            except ValueError:
                event_time = cutoff
        for src in source_list:
            facts.append(
                H5EvidenceFact(
                    source=src[:_SOURCE_MAX_LEN],
                    authority="web_grounding",
                    summary=summary,
                    event_time=event_time,
                    effective_as_of=cutoff,
                    known_at=cutoff,
                )
            )
    else:
        missing.append(MissingEvidenceField(field="web_grounding", reason="absent_from_h5_inputs"))

    deltas = phase_inputs.get("price_deltas")
    if isinstance(deltas, dict):
        raw_delta = deltas.get(sym)
        if raw_delta is None:
            raw_delta = deltas.get(ticker)
        if raw_delta is not None:
            facts.append(
                H5EvidenceFact(
                    source=f"price_delta:{sym}",
                    authority="price_delta",
                    summary=f"{sym} price_delta={raw_delta}",
                    event_time=cutoff,
                    effective_as_of=cutoff,
                    known_at=cutoff,
                )
            )
        else:
            missing.append(
                MissingEvidenceField(
                    field=f"price_deltas.{sym}",
                    reason="absent_from_h5_inputs",
                )
            )
    else:
        missing.append(MissingEvidenceField(field="price_deltas", reason="absent_from_h5_inputs"))

    bias = phase_inputs.get("bias_row")
    if isinstance(bias, dict) and bias:
        # Market bias only — never holdings / portfolio keys.
        safe = {
            key: value
            for key, value in bias.items()
            if str(key).strip().lower() not in _PORTFOLIO_LEAK_AUTHORITIES
        }
        if safe:
            facts.append(
                H5EvidenceFact(
                    source="phase6_bias_row",
                    authority="bias_row",
                    summary=str(safe),
                    event_time=cutoff,
                    effective_as_of=cutoff,
                    known_at=cutoff,
                )
            )

    # Defense in depth: drop any fact that somehow used a leak authority.
    facts = [fact for fact in facts if fact.authority not in _PORTFOLIO_LEAK_AUTHORITIES]
    return tuple(facts), tuple(missing)


def build_h5_evidence_bundle(
    *,
    ticker: str,
    source_run_id: str,
    attempt_id: str,
    state_version_id: UUID,
    facts: tuple[H5EvidenceFact, ...],
    recorded_at: datetime,
    provenance: TypedProvenance,
    missing_fields: tuple[str, ...] | tuple[MissingEvidenceField, ...] = (),
) -> H5EvidenceBundleBuild:
    """Dedupe facts, link conflicts, and materialize one immutable base bundle."""
    sym = ticker.strip().upper()
    by_id: dict[UUID, EvidenceRecord] = {}
    by_source_auth: dict[tuple[str, str], list[EvidenceRecord]] = {}

    for fact in facts:
        digest = evidence_content_hash(
            source=fact.source,
            authority=fact.authority,
            summary=fact.summary,
        )
        evidence_id = evidence_record_id(
            source=fact.source,
            authority=fact.authority,
            content_hash=digest,
        )
        if evidence_id in by_id:
            continue
        record = EvidenceRecord(
            evidence_id=evidence_id,
            source=fact.source,
            authority=fact.authority,
            summary=fact.summary,
            event_time=fact.event_time,
            effective_as_of=fact.effective_as_of,
            known_at=fact.known_at,
            recorded_at=recorded_at,
            content_hash=digest,
            provenance=provenance,
        )
        by_id[evidence_id] = record
        by_source_auth.setdefault((fact.source.strip(), fact.authority.strip()), []).append(record)

    conflicts: list[EvidenceConflict] = []
    # Same source+authority with divergent summaries (different evidence_ids).
    # Reported as diagnostics only — do not mutate leaf content_hash / identity.
    for group in by_source_auth.values():
        if len(group) < 2:
            continue
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                conflicts.append(
                    EvidenceConflict(
                        left_evidence_id=left.evidence_id,
                        right_evidence_id=right.evidence_id,
                    )
                )

    evidence = tuple(sorted(by_id.values(), key=lambda item: item.evidence_id.hex))
    evidence_ids = tuple(item.evidence_id for item in evidence)

    if evidence:
        event_time = min(item.event_time for item in evidence)
        effective_as_of = max(item.effective_as_of for item in evidence)
        known_at = max(item.known_at for item in evidence)
    else:
        event_time = recorded_at
        effective_as_of = recorded_at
        known_at = recorded_at

    content_hash = ticker_evidence_bundle_content_hash(
        ticker=sym,
        state_version_id=state_version_id,
        evidence_ids=evidence_ids,
        source=_H5_BASE_SOURCE,
    )
    bundle = TickerEvidenceBundle(
        bundle_id=ticker_evidence_bundle_id(
            source_run_id=source_run_id,
            ticker=sym,
            content_hash=content_hash,
        ),
        ticker=sym,
        source_run_id=source_run_id,
        attempt_id=attempt_id,
        state_version_id=state_version_id,
        evidence_ids=evidence_ids,
        source=_H5_BASE_SOURCE,
        event_time=event_time,
        effective_as_of=effective_as_of,
        known_at=known_at,
        recorded_at=recorded_at,
        content_hash=content_hash,
        provenance=provenance,
    )

    normalized_missing: list[MissingEvidenceField] = []
    for item in missing_fields:
        if isinstance(item, MissingEvidenceField):
            normalized_missing.append(item)
        else:
            normalized_missing.append(
                MissingEvidenceField(field=str(item), reason="absent_from_h5_inputs")
            )

    return H5EvidenceBundleBuild(
        bundle=bundle,
        evidence=evidence,
        conflicts=tuple(conflicts),
        missing_fields=tuple(normalized_missing),
    )


def publish_h5_evidence_bundle(
    *,
    built: H5EvidenceBundleBuild,
    store: EvidenceBundleStore | None,
) -> TickerEvidenceBundle:
    """Persist base when writer+store are active; always return the typed bundle."""
    bundle = built.bundle
    if store is not None and evidence_bundle_writer_enabled():
        store.append_base_bundle(bundle)
    return bundle


def cite_evidence_bundle_on_forecast(
    terms: ForecastTerms,
    bundle: TickerEvidenceBundle,
) -> ForecastTerms:
    """Union LLM cites with base bundle_id + evidence_ids (deterministic order)."""
    merged: list[str] = []
    seen: set[str] = set()
    for item in (
        *terms.evidence_ids,
        str(bundle.bundle_id),
        *(str(evidence_id) for evidence_id in bundle.evidence_ids),
    ):
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return terms.model_copy(update={"evidence_ids": tuple(merged)})


# Same namespace as ticker_evidence_bundle_id — unpinned shadow lineage only.
_UNPINNED_STATE_VERSION_NS = UUID("c1a0e507-4b8d-5f2a-9c17-3d6e8f0a1b22")


def resolve_h5_state_version_id(
    research_state_pin: dict[str, object] | None,
    *,
    source_run_id: str,
) -> UUID:
    """Exact pin id when present; else deterministic unpinned UUID5 for the run."""
    if isinstance(research_state_pin, dict):
        raw = research_state_pin.get("state_version_id")
        if raw is not None and str(raw).strip():
            return UUID(str(raw))
    return uuid5(_UNPINNED_STATE_VERSION_NS, f"unpinned:{source_run_id.strip()}")


__all__ = [
    "OLYMPUS_EVIDENCE_BUNDLE_WRITER_ENV",
    "EvidenceConflict",
    "H5EvidenceBundleBuild",
    "H5EvidenceFact",
    "MissingEvidenceField",
    "build_h5_evidence_bundle",
    "cite_evidence_bundle_on_forecast",
    "evidence_bundle_writer_enabled",
    "facts_from_phase_inputs",
    "publish_h5_evidence_bundle",
    "resolve_h5_state_version_id",
]
