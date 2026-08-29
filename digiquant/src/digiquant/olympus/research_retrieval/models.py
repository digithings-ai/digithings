"""Frozen Phase 3 research-state contracts (#2841 / WP12.1) and ticker
evidence-bundle contracts (#2844 / WP11.1).

Prose ``documents`` / digests are deterministic *views*. Authoritative research
memory is these structured, append-only entities. Persistence (WP12.2) and
preflight pins (WP12.3) consume this surface; this module defines contracts only.

WP11.1 adds immutable H5 :class:`TickerEvidenceBundle` plus append-only
:class:`MissingFactRequest` / :class:`EvidenceBundleAmendment` vocabulary.
H6 selection cutover is WP11.3 (`research_retrieval/planner.py`) — these
contracts do not own fan-out; selection consumes bundle IDs as features.

Distinct from Track B ``research_corpus`` (#2613): corpus pins are tenant-agnostic
theme/asset/segment identity. These models are versioned claim/event/evidence
state with temporal provenance and supersession.

Style mirrors ``hermes.models.forecast`` / ``accounting.models``: frozen,
``extra="forbid"``, UTC-only aware datetimes, UUID5 content identity, immutable
tuples. Canonical IDs and content hashes are independent of input list ordering.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Stable UUID5 namespaces — do not change; persisted IDs would diverge.
_EVIDENCE_ID_NS = UUID("c1a0e501-4b8d-5f2a-9c17-3d6e8f0a1b22")
_BELIEF_VERSION_ID_NS = UUID("c1a0e502-4b8d-5f2a-9c17-3d6e8f0a1b22")
_EXPECTED_EVENT_VERSION_ID_NS = UUID("c1a0e503-4b8d-5f2a-9c17-3d6e8f0a1b22")
_PATCH_ID_NS = UUID("c1a0e504-4b8d-5f2a-9c17-3d6e8f0a1b22")
_STATE_VERSION_ID_NS = UUID("c1a0e505-4b8d-5f2a-9c17-3d6e8f0a1b22")
_LEGACY_REF_ID_NS = UUID("c1a0e506-4b8d-5f2a-9c17-3d6e8f0a1b22")
_TICKER_EVIDENCE_BUNDLE_ID_NS = UUID("c1a0e507-4b8d-5f2a-9c17-3d6e8f0a1b22")
_MISSING_FACT_REQUEST_ID_NS = UUID("c1a0e508-4b8d-5f2a-9c17-3d6e8f0a1b22")
_EVIDENCE_BUNDLE_AMENDMENT_ID_NS = UUID("c1a0e509-4b8d-5f2a-9c17-3d6e8f0a1b22")

# Identifiers / short keys aligned with DB CHECK (length … BETWEEN 1 AND 500).
NonEmptyStr: TypeAlias = Annotated[str, Field(min_length=1, max_length=500)]
# Free-text prose (evidence/belief/patch summaries). No max_length — silent
# truncation and 500-char caps crashed H5 on long web_grounding (#3063).
NonEmptyText: TypeAlias = Annotated[str, Field(min_length=1)]
Confidence: TypeAlias = Annotated[
    Decimal, Field(ge=0, le=1, allow_inf_nan=False, max_digits=16, decimal_places=8)
]
PositiveSessions: TypeAlias = Annotated[int, Field(gt=0)]
SchemaVersion: TypeAlias = Annotated[int, Field(ge=1)]


class ResearchStateModel(BaseModel):
    """Strict immutable base for every research-state contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BeliefStatus(StrEnum):
    """Lifecycle of one belief version (append-only; never mutate in place)."""

    ACTIVE = "active"
    CHALLENGED = "challenged"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ExpectedEventStatus(StrEnum):
    """Resolution state of an expected-event version."""

    OPEN = "open"
    OCCURRED = "occurred"
    MISSED = "missed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class PatchTargetKind(StrEnum):
    """What a structured research patch addresses."""

    BELIEF = "belief"
    EXPECTED_EVENT = "expected_event"
    SECTION = "section"
    METRIC = "metric"
    EVIDENCE = "evidence"


class PatchMode(StrEnum):
    """Planner-aligned patch modes (Phase 3); no prose parsing."""

    METRIC_PATCH = "metric_patch"
    SECTION_PATCH = "section_patch"


class TypedProvenance(ResearchStateModel):
    """Typed source lineage — reconstructable without raw dict blobs."""

    source_run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    artifact_id: NonEmptyStr
    writer_role: NonEmptyStr = "olympus"


def _require_utc(value: AwareDatetime, *, field_name: str) -> AwareDatetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_digest(payload: object) -> str:
    """SHA-256 over canonical JSON (ordering-independent for sorted structures)."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _coerce_uuid_tuple(value: object) -> object:
    if isinstance(value, list):
        return tuple(value)
    return value


def _sorted_uuids(ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
    """Sort and dedupe UUID tuples (manifest / link sets are unordered sets)."""
    return tuple(sorted(set(ids), key=lambda item: item.hex))


def _reject_self_supersession(*, self_id: UUID, supersedes_id: UUID | None, label: str) -> None:
    if supersedes_id is not None and supersedes_id == self_id:
        raise ValueError(f"{label} cannot supersede itself")


def _validate_temporal_order(
    *,
    event_time: AwareDatetime,
    effective_as_of: AwareDatetime,
    known_at: AwareDatetime,
    recorded_at: AwareDatetime,
    allow_future_event: bool = False,
) -> None:
    for name, stamp in (
        ("event_time", event_time),
        ("effective_as_of", effective_as_of),
        ("known_at", known_at),
        ("recorded_at", recorded_at),
    ):
        _require_utc(stamp, field_name=name)
    if effective_as_of < event_time and not allow_future_event:
        raise ValueError("effective_as_of must be >= event_time")
    if known_at < event_time and not allow_future_event:
        raise ValueError("known_at must be >= event_time")
    if recorded_at < known_at:
        raise ValueError("recorded_at must be >= known_at")
    if known_at < effective_as_of and not allow_future_event:
        raise ValueError("known_at must be >= effective_as_of")


def evidence_record_id(*, source: str, authority: str, content_hash: str) -> UUID:
    """Deterministic evidence identity from source + authority + content hash."""
    if not source.strip() or not authority.strip() or not content_hash.strip():
        raise ValueError("source, authority, and content_hash are required")
    return uuid5(
        _EVIDENCE_ID_NS,
        f"{source.strip()}:{authority.strip()}:{content_hash.strip()}",
    )


def belief_version_id(
    *,
    belief_id: UUID,
    content_hash: str,
    supersedes_version_id: UUID | None,
) -> UUID:
    """Deterministic belief-version identity (independent of evidence list order)."""
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    parent = "" if supersedes_version_id is None else supersedes_version_id.hex
    return uuid5(
        _BELIEF_VERSION_ID_NS,
        f"{belief_id.hex}:{parent}:{content_hash.strip()}",
    )


def expected_event_version_id(
    *,
    expected_event_id: UUID,
    content_hash: str,
    supersedes_version_id: UUID | None,
) -> UUID:
    """Deterministic expected-event version identity."""
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    parent = "" if supersedes_version_id is None else supersedes_version_id.hex
    return uuid5(
        _EXPECTED_EVENT_VERSION_ID_NS,
        f"{expected_event_id.hex}:{parent}:{content_hash.strip()}",
    )


def research_patch_id(
    *,
    target_kind: str,
    target_id: str,
    content_hash: str,
    supersedes_patch_id: UUID | None,
) -> UUID:
    """Deterministic patch identity from target + parent + content hash."""
    if not target_kind.strip() or not target_id.strip() or not content_hash.strip():
        raise ValueError("target_kind, target_id, and content_hash are required")
    parent = "" if supersedes_patch_id is None else supersedes_patch_id.hex
    return uuid5(
        _PATCH_ID_NS,
        f"{target_kind.strip()}:{target_id.strip()}:{parent}:{content_hash.strip()}",
    )


def research_state_version_id(
    *,
    manifest_content_hash: str,
    parent_id: UUID | None,
    schema_version: int = 1,
) -> UUID:
    """Content-addressed state version id from parent + manifest digest + schema."""
    if not manifest_content_hash.strip():
        raise ValueError("manifest_content_hash is required")
    if schema_version < 1:
        raise ValueError("schema_version must be >= 1")
    parent = "" if parent_id is None else parent_id.hex
    return uuid5(
        _STATE_VERSION_ID_NS,
        f"{parent}:{manifest_content_hash.strip()}:{schema_version}",
    )


def legacy_document_ref_id(*, document_key: str, as_of_date: str, source_hash: str) -> UUID:
    """Deterministic legacy document reference id (inventory only)."""
    if not document_key.strip() or not as_of_date.strip() or not source_hash.strip():
        raise ValueError("document_key, as_of_date, and source_hash are required")
    return uuid5(
        _LEGACY_REF_ID_NS,
        f"{document_key.strip()}:{as_of_date.strip()}:{source_hash.strip()}",
    )


class EvidenceRecord(ResearchStateModel):
    """Immutable observation / evidence leaf with temporal provenance."""

    evidence_id: UUID
    source: NonEmptyStr
    authority: NonEmptyStr
    summary: NonEmptyText
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance
    affected_belief_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    novelty_of: tuple[UUID, ...] = Field(default_factory=tuple)
    contradiction_of: tuple[UUID, ...] = Field(default_factory=tuple)
    supersedes_evidence_id: UUID | None = None

    @field_validator("affected_belief_ids", "novelty_of", "contradiction_of", mode="before")
    @classmethod
    def _coerce_evidence_id_lists(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator("affected_belief_ids", "novelty_of", "contradiction_of")
    @classmethod
    def _canonicalize_evidence_id_lists(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @model_validator(mode="after")
    def _validate_evidence(self) -> EvidenceRecord:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        _reject_self_supersession(
            self_id=self.evidence_id,
            supersedes_id=self.supersedes_evidence_id,
            label="EvidenceRecord",
        )
        expected_hash = evidence_content_hash(
            source=self.source,
            authority=self.authority,
            summary=self.summary,
            affected_belief_ids=self.affected_belief_ids,
            novelty_of=self.novelty_of,
            contradiction_of=self.contradiction_of,
            supersedes_evidence_id=self.supersedes_evidence_id,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical EvidenceRecord digest")
        expected_id = evidence_record_id(
            source=self.source,
            authority=self.authority,
            content_hash=self.content_hash,
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id must be UUID5 of source+authority+content_hash")
        return self


def evidence_content_hash(
    *,
    source: str,
    authority: str,
    summary: str,
    affected_belief_ids: tuple[UUID, ...] = (),
    novelty_of: tuple[UUID, ...] = (),
    contradiction_of: tuple[UUID, ...] = (),
    supersedes_evidence_id: UUID | None = None,
) -> str:
    """Canonical digest for evidence body (ID lists sorted; lineage included)."""
    return content_digest(
        {
            "source": source.strip(),
            "authority": authority.strip(),
            "summary": summary.strip(),
            "affected_belief_ids": [item.hex for item in _sorted_uuids(affected_belief_ids)],
            "novelty_of": [item.hex for item in _sorted_uuids(novelty_of)],
            "contradiction_of": [item.hex for item in _sorted_uuids(contradiction_of)],
            "supersedes_evidence_id": (
                None if supersedes_evidence_id is None else supersedes_evidence_id.hex
            ),
        }
    )


class BeliefVersion(ResearchStateModel):
    """Append-only belief claim version with evidence links and supersession."""

    belief_version_id: UUID
    belief_id: UUID
    statement: NonEmptyText
    confidence: Confidence
    horizon_sessions: PositiveSessions
    status: BeliefStatus
    supporting_evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    counter_evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    invalidation_rules: tuple[str, ...] = Field(default_factory=tuple)
    supersedes_version_id: UUID | None = None
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @field_validator("supporting_evidence_ids", "counter_evidence_ids", mode="before")
    @classmethod
    def _coerce_belief_evidence(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator("invalidation_rules", mode="before")
    @classmethod
    def _coerce_rules(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("supporting_evidence_ids", "counter_evidence_ids")
    @classmethod
    def _canonicalize_belief_evidence(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @field_validator("invalidation_rules")
    @classmethod
    def _canonicalize_rules(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(rule.strip() for rule in value if rule.strip())
        return tuple(sorted(cleaned))

    @model_validator(mode="after")
    def _validate_belief(self) -> BeliefVersion:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        _reject_self_supersession(
            self_id=self.belief_version_id,
            supersedes_id=self.supersedes_version_id,
            label="BeliefVersion",
        )
        expected_hash = belief_content_hash(
            belief_id=self.belief_id,
            statement=self.statement,
            confidence=self.confidence,
            horizon_sessions=self.horizon_sessions,
            status=self.status,
            supporting_evidence_ids=self.supporting_evidence_ids,
            counter_evidence_ids=self.counter_evidence_ids,
            invalidation_rules=self.invalidation_rules,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical BeliefVersion digest")
        expected_id = belief_version_id(
            belief_id=self.belief_id,
            content_hash=self.content_hash,
            supersedes_version_id=self.supersedes_version_id,
        )
        if self.belief_version_id != expected_id:
            raise ValueError("belief_version_id must be UUID5 of belief_id+parent+content_hash")
        return self


def belief_content_hash(
    *,
    belief_id: UUID,
    statement: str,
    confidence: Decimal,
    horizon_sessions: int,
    status: BeliefStatus | str,
    supporting_evidence_ids: tuple[UUID, ...] = (),
    counter_evidence_ids: tuple[UUID, ...] = (),
    invalidation_rules: tuple[str, ...] = (),
) -> str:
    status_value = status.value if isinstance(status, BeliefStatus) else str(status)
    return content_digest(
        {
            "belief_id": belief_id.hex,
            "statement": statement.strip(),
            "confidence": str(confidence),
            "horizon_sessions": horizon_sessions,
            "status": status_value,
            "supporting_evidence_ids": [
                item.hex for item in _sorted_uuids(supporting_evidence_ids)
            ],
            "counter_evidence_ids": [item.hex for item in _sorted_uuids(counter_evidence_ids)],
            "invalidation_rules": sorted(
                rule.strip() for rule in invalidation_rules if rule.strip()
            ),
        }
    )


class ExpectedEventVersion(ResearchStateModel):
    """Append-only expected catalyst / event version."""

    expected_event_version_id: UUID
    expected_event_id: UUID
    label: NonEmptyText
    status: ExpectedEventStatus
    event_time: AwareDatetime
    supporting_evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    supersedes_version_id: UUID | None = None
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @field_validator("supporting_evidence_ids", mode="before")
    @classmethod
    def _coerce_event_evidence(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator("supporting_evidence_ids")
    @classmethod
    def _canonicalize_event_evidence(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @model_validator(mode="after")
    def _validate_expected_event(self) -> ExpectedEventVersion:
        # Expected events may sit in the future relative to known_at.
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
            allow_future_event=True,
        )
        if self.recorded_at < self.known_at:
            raise ValueError("recorded_at must be >= known_at")
        if self.effective_as_of > self.known_at:
            raise ValueError("effective_as_of must be <= known_at for expected events")
        _reject_self_supersession(
            self_id=self.expected_event_version_id,
            supersedes_id=self.supersedes_version_id,
            label="ExpectedEventVersion",
        )
        expected_hash = expected_event_content_hash(
            expected_event_id=self.expected_event_id,
            label=self.label,
            status=self.status,
            event_time=self.event_time,
            supporting_evidence_ids=self.supporting_evidence_ids,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ExpectedEventVersion digest")
        expected_id = expected_event_version_id(
            expected_event_id=self.expected_event_id,
            content_hash=self.content_hash,
            supersedes_version_id=self.supersedes_version_id,
        )
        if self.expected_event_version_id != expected_id:
            raise ValueError(
                "expected_event_version_id must be UUID5 of event_id+parent+content_hash"
            )
        return self


def expected_event_content_hash(
    *,
    expected_event_id: UUID,
    label: str,
    status: ExpectedEventStatus | str,
    event_time: AwareDatetime,
    supporting_evidence_ids: tuple[UUID, ...] = (),
) -> str:
    status_value = status.value if isinstance(status, ExpectedEventStatus) else str(status)
    return content_digest(
        {
            "expected_event_id": expected_event_id.hex,
            "label": label.strip(),
            "status": status_value,
            "event_time": event_time.isoformat(),
            "supporting_evidence_ids": [
                item.hex for item in _sorted_uuids(supporting_evidence_ids)
            ],
        }
    )


class ResearchPatch(ResearchStateModel):
    """Structured state patch (metric/section) — never derived from prose parsing."""

    patch_id: UUID
    target_kind: PatchTargetKind
    target_id: NonEmptyStr
    mode: PatchMode
    summary: NonEmptyText
    supersedes_patch_id: UUID | None = None
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @model_validator(mode="after")
    def _validate_patch(self) -> ResearchPatch:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        _reject_self_supersession(
            self_id=self.patch_id,
            supersedes_id=self.supersedes_patch_id,
            label="ResearchPatch",
        )
        expected_hash = research_patch_content_hash(
            target_kind=self.target_kind,
            target_id=self.target_id,
            mode=self.mode,
            summary=self.summary,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ResearchPatch digest")
        expected_id = research_patch_id(
            target_kind=self.target_kind.value,
            target_id=self.target_id,
            content_hash=self.content_hash,
            supersedes_patch_id=self.supersedes_patch_id,
        )
        if self.patch_id != expected_id:
            raise ValueError("patch_id must be UUID5 of target_kind+target_id+parent+content_hash")
        return self


def research_patch_content_hash(
    *,
    target_kind: PatchTargetKind | str,
    target_id: str,
    mode: PatchMode | str,
    summary: str,
) -> str:
    kind = target_kind.value if isinstance(target_kind, PatchTargetKind) else str(target_kind)
    mode_value = mode.value if isinstance(mode, PatchMode) else str(mode)
    return content_digest(
        {
            "target_kind": kind,
            "target_id": target_id.strip(),
            "mode": mode_value,
            "summary": summary.strip(),
        }
    )


class LegacyDocumentRef(ResearchStateModel):
    """Inventory pointer to legacy prose — no fabricated known_at or evidence.

    Strict readers (WP12.2+) exclude these; they never participate in exact replay.
    """

    legacy_ref_id: UUID
    document_key: NonEmptyStr
    as_of_date: NonEmptyStr
    source_table: NonEmptyStr
    source_hash: NonEmptyStr
    known_at: None = None
    legacy_manifest_only: Annotated[bool, Field(default=True)] = True

    @model_validator(mode="after")
    def _validate_legacy_ref(self) -> LegacyDocumentRef:
        if self.known_at is not None:
            raise ValueError("LegacyDocumentRef.known_at must be None")
        if self.legacy_manifest_only is not True:
            raise ValueError("LegacyDocumentRef.legacy_manifest_only must be True")
        expected_id = legacy_document_ref_id(
            document_key=self.document_key,
            as_of_date=self.as_of_date,
            source_hash=self.source_hash,
        )
        if self.legacy_ref_id != expected_id:
            raise ValueError("legacy_ref_id must be UUID5 of document_key+as_of_date+source_hash")
        return self


class ResearchStateManifest(ResearchStateModel):
    """Exact set of entity version IDs that compose one research-state version."""

    evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    belief_version_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    expected_event_version_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    patch_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    legacy_ref_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    content_hash: NonEmptyStr

    @field_validator(
        "evidence_ids",
        "belief_version_ids",
        "expected_event_version_ids",
        "patch_ids",
        "legacy_ref_ids",
        mode="before",
    )
    @classmethod
    def _coerce_manifest_lists(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator(
        "evidence_ids",
        "belief_version_ids",
        "expected_event_version_ids",
        "patch_ids",
        "legacy_ref_ids",
    )
    @classmethod
    def _canonicalize_manifest_lists(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @model_validator(mode="after")
    def _validate_manifest(self) -> ResearchStateManifest:
        expected = manifest_content_hash(
            evidence_ids=self.evidence_ids,
            belief_version_ids=self.belief_version_ids,
            expected_event_version_ids=self.expected_event_version_ids,
            patch_ids=self.patch_ids,
            legacy_ref_ids=self.legacy_ref_ids,
        )
        if self.content_hash != expected:
            raise ValueError("content_hash must match canonical ResearchStateManifest digest")
        return self


def manifest_content_hash(
    *,
    evidence_ids: tuple[UUID, ...] = (),
    belief_version_ids: tuple[UUID, ...] = (),
    expected_event_version_ids: tuple[UUID, ...] = (),
    patch_ids: tuple[UUID, ...] = (),
    legacy_ref_ids: tuple[UUID, ...] = (),
) -> str:
    return content_digest(
        {
            "evidence_ids": [item.hex for item in _sorted_uuids(evidence_ids)],
            "belief_version_ids": [item.hex for item in _sorted_uuids(belief_version_ids)],
            "expected_event_version_ids": [
                item.hex for item in _sorted_uuids(expected_event_version_ids)
            ],
            "patch_ids": [item.hex for item in _sorted_uuids(patch_ids)],
            "legacy_ref_ids": [item.hex for item in _sorted_uuids(legacy_ref_ids)],
        }
    )


class ResearchStateVersion(ResearchStateModel):
    """Content-addressed research-state snapshot with optional parent lineage."""

    state_version_id: UUID
    parent_state_version_id: UUID | None = None
    manifest: ResearchStateManifest
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @model_validator(mode="after")
    def _validate_state_version(self) -> ResearchStateVersion:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        _reject_self_supersession(
            self_id=self.state_version_id,
            supersedes_id=self.parent_state_version_id,
            label="ResearchStateVersion",
        )
        expected_hash = content_digest(
            {
                "manifest_content_hash": self.manifest.content_hash,
                "parent_state_version_id": (
                    None
                    if self.parent_state_version_id is None
                    else self.parent_state_version_id.hex
                ),
                "schema_version": self.schema_version,
            }
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ResearchStateVersion digest")
        expected_id = research_state_version_id(
            manifest_content_hash=self.manifest.content_hash,
            parent_id=self.parent_state_version_id,
            schema_version=self.schema_version,
        )
        if self.state_version_id != expected_id:
            raise ValueError(
                "state_version_id must be UUID5 of parent+manifest_content_hash+schema_version"
            )
        return self


def ticker_evidence_bundle_id(
    *,
    source_run_id: str,
    ticker: str,
    content_hash: str,
) -> UUID:
    """Deterministic base-bundle identity: run + ticker + content hash."""
    if not source_run_id.strip() or not ticker.strip() or not content_hash.strip():
        raise ValueError("source_run_id, ticker, and content_hash are required")
    return uuid5(
        _TICKER_EVIDENCE_BUNDLE_ID_NS,
        f"{source_run_id.strip()}:{ticker.strip().upper()}:{content_hash.strip()}",
    )


def ticker_evidence_bundle_content_hash(
    *,
    ticker: str,
    state_version_id: UUID,
    evidence_ids: tuple[UUID, ...],
    source: str,
) -> str:
    """Canonical digest for an H5 base ticker evidence bundle body."""
    return content_digest(
        {
            "ticker": ticker.strip().upper(),
            "state_version_id": state_version_id.hex,
            "evidence_ids": [item.hex for item in _sorted_uuids(evidence_ids)],
            "source": source.strip(),
        }
    )


def missing_fact_request_id(
    *,
    base_bundle_id: UUID,
    fact_key: str,
    content_hash: str,
) -> UUID:
    """Deterministic missing-fact request identity bound to one base bundle."""
    if not fact_key.strip() or not content_hash.strip():
        raise ValueError("fact_key and content_hash are required")
    return uuid5(
        _MISSING_FACT_REQUEST_ID_NS,
        f"{base_bundle_id.hex}:{fact_key.strip()}:{content_hash.strip()}",
    )


def missing_fact_request_content_hash(
    *,
    base_bundle_id: UUID,
    fact_key: str,
    rationale: str,
) -> str:
    """Canonical digest for a named missing-fact request."""
    return content_digest(
        {
            "base_bundle_id": base_bundle_id.hex,
            "fact_key": fact_key.strip(),
            "rationale": rationale.strip(),
        }
    )


def evidence_bundle_amendment_id(
    *,
    base_bundle_id: UUID,
    missing_fact_request_id: UUID,
    content_hash: str,
) -> UUID:
    """Deterministic H6 amendment identity bound to one base + one request."""
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    return uuid5(
        _EVIDENCE_BUNDLE_AMENDMENT_ID_NS,
        f"{base_bundle_id.hex}:{missing_fact_request_id.hex}:{content_hash.strip()}",
    )


def evidence_bundle_amendment_content_hash(
    *,
    base_bundle_id: UUID,
    missing_fact_request_id: UUID,
    evidence_ids: tuple[UUID, ...],
    source: str,
) -> str:
    """Canonical digest for an append-only evidence-bundle amendment body."""
    return content_digest(
        {
            "base_bundle_id": base_bundle_id.hex,
            "missing_fact_request_id": missing_fact_request_id.hex,
            "evidence_ids": [item.hex for item in _sorted_uuids(evidence_ids)],
            "source": source.strip(),
        }
    )


class TickerEvidenceBundle(ResearchStateModel):
    """Immutable H5 base evidence bundle for one ticker in one run.

    WP11.1 contract — H6 selection (WP11.3) may cite ``bundle_id`` as a
    selection feature. Base rows never mutate; H6 may only append
    :class:`EvidenceBundleAmendment` rows (WP11.4).
    """

    bundle_id: UUID
    ticker: NonEmptyStr
    source_run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    state_version_id: UUID
    evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    source: NonEmptyStr
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def _coerce_bundle_evidence(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator("evidence_ids")
    @classmethod
    def _canonicalize_bundle_evidence(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _validate_bundle(self) -> TickerEvidenceBundle:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        if self.provenance.source_run_id != self.source_run_id:
            raise ValueError("provenance.source_run_id must match source_run_id")
        expected_hash = ticker_evidence_bundle_content_hash(
            ticker=self.ticker,
            state_version_id=self.state_version_id,
            evidence_ids=self.evidence_ids,
            source=self.source,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical TickerEvidenceBundle digest")
        expected_id = ticker_evidence_bundle_id(
            source_run_id=self.source_run_id,
            ticker=self.ticker,
            content_hash=self.content_hash,
        )
        if self.bundle_id != expected_id:
            raise ValueError("bundle_id must be UUID5 of source_run_id+ticker+content_hash")
        return self


class MissingFactRequest(ResearchStateModel):
    """Named missing-fact request H6 may answer — always linked to one base bundle."""

    request_id: UUID
    base_bundle_id: UUID
    ticker: NonEmptyStr
    fact_key: NonEmptyStr
    rationale: NonEmptyText
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @field_validator("ticker")
    @classmethod
    def _normalize_request_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _validate_request(self) -> MissingFactRequest:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        expected_hash = missing_fact_request_content_hash(
            base_bundle_id=self.base_bundle_id,
            fact_key=self.fact_key,
            rationale=self.rationale,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical MissingFactRequest digest")
        expected_id = missing_fact_request_id(
            base_bundle_id=self.base_bundle_id,
            fact_key=self.fact_key,
            content_hash=self.content_hash,
        )
        if self.request_id != expected_id:
            raise ValueError("request_id must be UUID5 of base_bundle_id+fact_key+content_hash")
        return self


class EvidenceBundleAmendment(ResearchStateModel):
    """Append-only H6 supplement for one missing-fact request on one base bundle.

    Never mutates :class:`TickerEvidenceBundle`. Unlinked amendments are refused
    by the store (WP11.1 metric: zero unlinked amendments).
    """

    amendment_id: UUID
    base_bundle_id: UUID
    missing_fact_request_id: UUID
    ticker: NonEmptyStr
    evidence_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    source: NonEmptyStr
    event_time: AwareDatetime
    effective_as_of: AwareDatetime
    known_at: AwareDatetime
    recorded_at: AwareDatetime
    schema_version: SchemaVersion = 1
    content_hash: NonEmptyStr
    provenance: TypedProvenance

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def _coerce_amendment_evidence(cls, value: object) -> object:
        return _coerce_uuid_tuple(value)

    @field_validator("evidence_ids")
    @classmethod
    def _canonicalize_amendment_evidence(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _sorted_uuids(value)

    @field_validator("ticker")
    @classmethod
    def _normalize_amendment_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _validate_amendment(self) -> EvidenceBundleAmendment:
        _validate_temporal_order(
            event_time=self.event_time,
            effective_as_of=self.effective_as_of,
            known_at=self.known_at,
            recorded_at=self.recorded_at,
        )
        expected_hash = evidence_bundle_amendment_content_hash(
            base_bundle_id=self.base_bundle_id,
            missing_fact_request_id=self.missing_fact_request_id,
            evidence_ids=self.evidence_ids,
            source=self.source,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical EvidenceBundleAmendment digest")
        expected_id = evidence_bundle_amendment_id(
            base_bundle_id=self.base_bundle_id,
            missing_fact_request_id=self.missing_fact_request_id,
            content_hash=self.content_hash,
        )
        if self.amendment_id != expected_id:
            raise ValueError("amendment_id must be UUID5 of base_bundle_id+request_id+content_hash")
        return self


class ResearchStatePin(ResearchStateModel):
    """Exact state version selected once for a run/attempt (preflight WP12.3)."""

    run_id: NonEmptyStr
    attempt_id: NonEmptyStr
    state_version_id: UUID
    knowledge_cutoff_at: AwareDatetime
    requested_as_of: AwareDatetime
    pinned_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_pin(self) -> ResearchStatePin:
        for name, stamp in (
            ("knowledge_cutoff_at", self.knowledge_cutoff_at),
            ("requested_as_of", self.requested_as_of),
            ("pinned_at", self.pinned_at),
        ):
            _require_utc(stamp, field_name=name)
        if self.requested_as_of > self.knowledge_cutoff_at:
            raise ValueError("requested_as_of must be <= knowledge_cutoff_at")
        if self.pinned_at < self.knowledge_cutoff_at:
            raise ValueError("pinned_at must be >= knowledge_cutoff_at")
        if self.pinned_at < self.requested_as_of:
            raise ValueError("pinned_at must be >= requested_as_of")
        return self


__all__ = [
    "BeliefStatus",
    "BeliefVersion",
    "EvidenceBundleAmendment",
    "EvidenceRecord",
    "ExpectedEventStatus",
    "ExpectedEventVersion",
    "LegacyDocumentRef",
    "MissingFactRequest",
    "PatchMode",
    "PatchTargetKind",
    "ResearchPatch",
    "ResearchStateManifest",
    "ResearchStateModel",
    "ResearchStatePin",
    "ResearchStateVersion",
    "TickerEvidenceBundle",
    "TypedProvenance",
    "belief_content_hash",
    "belief_version_id",
    "content_digest",
    "evidence_bundle_amendment_content_hash",
    "evidence_bundle_amendment_id",
    "evidence_content_hash",
    "evidence_record_id",
    "expected_event_content_hash",
    "expected_event_version_id",
    "legacy_document_ref_id",
    "manifest_content_hash",
    "missing_fact_request_content_hash",
    "missing_fact_request_id",
    "research_patch_content_hash",
    "research_patch_id",
    "research_state_version_id",
    "ticker_evidence_bundle_content_hash",
    "ticker_evidence_bundle_id",
]
