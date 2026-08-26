"""Private append-only research-state store (#2854 / WP12.2).

Persists frozen WP12.1 contracts into one store boundary (in-memory for unit
tests; migration ``088_olympus_research_state.sql`` is the durable schema).

Semantics:
- **Content idempotency:** same primary key + same ``content_hash`` is a no-op.
- **Changed content appends:** a new content-addressed id inserts a new row —
  never UPDATE. Same PK with a different hash raises
  :class:`ResearchStateConflict`.
- **As-of selection** (pre-pin only): ``effective_as_of <= requested_as_of`` and
  ``known_at <= knowledge_cutoff_at``.
- **Strict reads** exclude future-known rows and legacy-null-``known_at`` refs.
- **Exact load** returns byte-equivalent typed state even after newer rows exist.
- **No ``load_latest``** after a run pin — callers must use the pin or an exact id.

WP11.1 ticker evidence bundles live beside this store as
:class:`EvidenceBundleStore` (migration ``090_olympus_evidence_bundles.sql``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from digiquant.olympus.research_retrieval.models import (
    BeliefVersion,
    EvidenceBundleAmendment,
    EvidenceRecord,
    ExpectedEventVersion,
    LegacyDocumentRef,
    MissingFactRequest,
    ResearchPatch,
    ResearchStatePin,
    ResearchStateVersion,
    TickerEvidenceBundle,
)
from digiquant.olympus.temporal import require_utc_datetime

T = TypeVar("T", bound=BaseModel)


class ResearchStateConflict(RuntimeError):
    """Same identity already stored with a different content hash."""


class ResearchStateError(RuntimeError):
    """Store refused a write or could not resolve exact state."""


class ResearchStateMissingError(LookupError):
    """Exact version / entity / pin not found."""


@dataclass(frozen=True)
class LoadedResearchState:
    """Exact typed reconstruction of one :class:`ResearchStateVersion`."""

    version: ResearchStateVersion
    evidence: tuple[EvidenceRecord, ...]
    beliefs: tuple[BeliefVersion, ...]
    expected_events: tuple[ExpectedEventVersion, ...]
    patches: tuple[ResearchPatch, ...]
    legacy_refs: tuple[LegacyDocumentRef, ...]


def _payload_bytes(model: BaseModel) -> bytes:
    return model.model_dump_json().encode("utf-8")


def _require_parent(*, label: str, parent_id: UUID | None, present: bool) -> None:
    if parent_id is not None and not present:
        raise ResearchStateError(f"{label} references missing parent {parent_id}")


def _require_known_by(
    *,
    label: str,
    entity_id: UUID,
    known_at: datetime,
    bound_at: datetime,
    bound_name: str,
) -> None:
    if known_at > bound_at:
        raise ResearchStateError(f"{label} {entity_id} known_at is after {bound_name}")


class ResearchStateStore:
    """Append-only research-state boundary (no upsert / update / delete)."""

    def __init__(self) -> None:
        self._evidence: dict[UUID, EvidenceRecord] = {}
        self._beliefs: dict[UUID, BeliefVersion] = {}
        self._expected_events: dict[UUID, ExpectedEventVersion] = {}
        self._patches: dict[UUID, ResearchPatch] = {}
        self._legacy_refs: dict[UUID, LegacyDocumentRef] = {}
        self._versions: dict[UUID, ResearchStateVersion] = {}
        self._pins: dict[tuple[str, str], ResearchStatePin] = {}

    def _require_strict_manifest_known_by(
        self,
        version: ResearchStateVersion,
        *,
        bound_at: datetime,
        bound_name: str,
    ) -> None:
        """Fail closed when any strict child outranks ``bound_at``."""
        manifest = version.manifest
        for evidence_id in manifest.evidence_ids:
            record = self._evidence.get(evidence_id)
            if record is not None:
                _require_known_by(
                    label="evidence",
                    entity_id=evidence_id,
                    known_at=record.known_at,
                    bound_at=bound_at,
                    bound_name=bound_name,
                )
        for belief_id in manifest.belief_version_ids:
            belief = self._beliefs.get(belief_id)
            if belief is not None:
                _require_known_by(
                    label="belief",
                    entity_id=belief_id,
                    known_at=belief.known_at,
                    bound_at=bound_at,
                    bound_name=bound_name,
                )
        for event_id in manifest.expected_event_version_ids:
            event = self._expected_events.get(event_id)
            if event is not None:
                _require_known_by(
                    label="expected_event",
                    entity_id=event_id,
                    known_at=event.known_at,
                    bound_at=bound_at,
                    bound_name=bound_name,
                )
        for patch_id in manifest.patch_ids:
            patch = self._patches.get(patch_id)
            if patch is not None:
                _require_known_by(
                    label="patch",
                    entity_id=patch_id,
                    known_at=patch.known_at,
                    bound_at=bound_at,
                    bound_name=bound_name,
                )

    # --- append helpers -----------------------------------------------------

    def _append_idempotent(
        self,
        *,
        store: dict[UUID, T],
        key: UUID,
        value: T,
        content_hash: str,
        existing_hash: str | None,
        label: str,
    ) -> T:
        if key in store:
            if existing_hash == content_hash:
                return store[key]
            raise ResearchStateConflict(f"{label} {key} exists with different content_hash")
        store[key] = value
        return value

    def append_evidence(self, record: EvidenceRecord) -> EvidenceRecord:
        """Insert evidence; exact retry is a no-op; changed content needs a new id."""
        _require_parent(
            label="EvidenceRecord",
            parent_id=record.supersedes_evidence_id,
            present=(
                record.supersedes_evidence_id is None
                or record.supersedes_evidence_id in self._evidence
            ),
        )
        existing = self._evidence.get(record.evidence_id)
        return self._append_idempotent(
            store=self._evidence,
            key=record.evidence_id,
            value=record,
            content_hash=record.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="evidence_id",
        )

    def append_belief(self, belief: BeliefVersion) -> BeliefVersion:
        _require_parent(
            label="BeliefVersion",
            parent_id=belief.supersedes_version_id,
            present=(
                belief.supersedes_version_id is None
                or belief.supersedes_version_id in self._beliefs
            ),
        )
        for evidence_id in (*belief.supporting_evidence_ids, *belief.counter_evidence_ids):
            if evidence_id not in self._evidence:
                raise ResearchStateError(
                    f"BeliefVersion {belief.belief_version_id} references "
                    f"missing evidence {evidence_id}"
                )
        existing = self._beliefs.get(belief.belief_version_id)
        return self._append_idempotent(
            store=self._beliefs,
            key=belief.belief_version_id,
            value=belief,
            content_hash=belief.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="belief_version_id",
        )

    def append_expected_event(self, event: ExpectedEventVersion) -> ExpectedEventVersion:
        _require_parent(
            label="ExpectedEventVersion",
            parent_id=event.supersedes_version_id,
            present=(
                event.supersedes_version_id is None
                or event.supersedes_version_id in self._expected_events
            ),
        )
        for evidence_id in event.supporting_evidence_ids:
            if evidence_id not in self._evidence:
                raise ResearchStateError(
                    f"ExpectedEventVersion {event.expected_event_version_id} "
                    f"references missing evidence {evidence_id}"
                )
        existing = self._expected_events.get(event.expected_event_version_id)
        return self._append_idempotent(
            store=self._expected_events,
            key=event.expected_event_version_id,
            value=event,
            content_hash=event.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="expected_event_version_id",
        )

    def append_patch(self, patch: ResearchPatch) -> ResearchPatch:
        _require_parent(
            label="ResearchPatch",
            parent_id=patch.supersedes_patch_id,
            present=(
                patch.supersedes_patch_id is None or patch.supersedes_patch_id in self._patches
            ),
        )
        existing = self._patches.get(patch.patch_id)
        return self._append_idempotent(
            store=self._patches,
            key=patch.patch_id,
            value=patch,
            content_hash=patch.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="patch_id",
        )

    def get_legacy_ref(self, legacy_ref_id: UUID) -> LegacyDocumentRef | None:
        """Return an inventory legacy ref by id, or ``None`` if absent."""
        return self._legacy_refs.get(legacy_ref_id)

    def append_legacy_ref(self, ref: LegacyDocumentRef) -> LegacyDocumentRef:
        """Inventory-only append. Strict readers never surface these rows."""
        if ref.known_at is not None:
            raise ResearchStateError("LegacyDocumentRef.known_at must be None")
        existing = self._legacy_refs.get(ref.legacy_ref_id)
        if existing is not None:
            if (
                existing.source_hash == ref.source_hash
                and existing.document_key == ref.document_key
                and existing.as_of_date == ref.as_of_date
            ):
                return existing
            raise ResearchStateConflict(
                f"legacy_ref_id {ref.legacy_ref_id} exists with different content"
            )
        self._legacy_refs[ref.legacy_ref_id] = ref
        return ref

    def append_state_version(self, version: ResearchStateVersion) -> ResearchStateVersion:
        """Persist a content-addressed state version after child-parent checks."""
        _require_parent(
            label="ResearchStateVersion",
            parent_id=version.parent_state_version_id,
            present=(
                version.parent_state_version_id is None
                or version.parent_state_version_id in self._versions
            ),
        )
        manifest = version.manifest
        for evidence_id in manifest.evidence_ids:
            if evidence_id not in self._evidence:
                raise ResearchStateError(
                    f"state version {version.state_version_id} missing evidence {evidence_id}"
                )
        for belief_id in manifest.belief_version_ids:
            if belief_id not in self._beliefs:
                raise ResearchStateError(
                    f"state version {version.state_version_id} missing belief {belief_id}"
                )
        for event_id in manifest.expected_event_version_ids:
            if event_id not in self._expected_events:
                raise ResearchStateError(
                    f"state version {version.state_version_id} missing event {event_id}"
                )
        for patch_id in manifest.patch_ids:
            if patch_id not in self._patches:
                raise ResearchStateError(
                    f"state version {version.state_version_id} missing patch {patch_id}"
                )
        for legacy_id in manifest.legacy_ref_ids:
            if legacy_id not in self._legacy_refs:
                raise ResearchStateError(
                    f"state version {version.state_version_id} missing legacy ref {legacy_id}"
                )

        # Strict children cannot outrank the version envelope's known_at.
        self._require_strict_manifest_known_by(
            version,
            bound_at=version.known_at,
            bound_name="state version known_at",
        )

        existing = self._versions.get(version.state_version_id)
        return self._append_idempotent(
            store=self._versions,
            key=version.state_version_id,
            value=version,
            content_hash=version.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="state_version_id",
        )

    # --- selection / pin / exact load ---------------------------------------

    def select_state_as_of(
        self,
        *,
        requested_as_of: datetime,
        knowledge_cutoff_at: datetime,
    ) -> ResearchStateVersion | None:
        """Pick the newest eligible state version before a run pin.

        Eligibility: ``effective_as_of <= requested_as_of`` and
        ``known_at <= knowledge_cutoff_at``. Versions whose manifests contain
        only legacy refs (or no strict entities) are skipped for strict as-of.
        """
        cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
        as_of = require_utc_datetime(requested_as_of, field_name="requested_as_of")
        candidates: list[ResearchStateVersion] = []
        for version in self._versions.values():
            if version.effective_as_of > as_of:
                continue
            if version.known_at > cutoff:
                continue
            if not self._version_has_strict_entities(version):
                continue
            candidates.append(version)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (item.effective_as_of, item.known_at, item.recorded_at),
            reverse=True,
        )
        return candidates[0]

    def _version_has_strict_entities(self, version: ResearchStateVersion) -> bool:
        manifest = version.manifest
        if (
            manifest.evidence_ids
            or manifest.belief_version_ids
            or manifest.expected_event_version_ids
            or manifest.patch_ids
        ):
            return True
        return False

    def pin_state_for_run(self, pin: ResearchStatePin) -> ResearchStatePin:
        """Append an exact run/attempt pin. Idempotent on identical pin content."""
        cutoff = require_utc_datetime(pin.knowledge_cutoff_at, field_name="knowledge_cutoff_at")
        as_of = require_utc_datetime(pin.requested_as_of, field_name="requested_as_of")
        version = self._versions.get(pin.state_version_id)
        if version is None:
            raise ResearchStateMissingError(
                f"cannot pin missing state_version_id {pin.state_version_id}"
            )
        if version.effective_as_of > as_of:
            raise ResearchStateError(
                f"state_version {pin.state_version_id} effective_as_of is after requested_as_of"
            )
        if version.known_at > cutoff:
            raise ResearchStateError(
                f"state_version {pin.state_version_id} known_at is after knowledge_cutoff_at"
            )
        # Defense in depth: reject look-ahead children even if envelope passed.
        self._require_strict_manifest_known_by(
            version,
            bound_at=cutoff,
            bound_name="knowledge_cutoff_at",
        )
        key = (pin.run_id, pin.attempt_id)
        existing = self._pins.get(key)
        if existing is not None:
            if (
                existing.state_version_id == pin.state_version_id
                and existing.knowledge_cutoff_at == pin.knowledge_cutoff_at
                and existing.requested_as_of == pin.requested_as_of
            ):
                return existing
            raise ResearchStateConflict(
                f"pin ({pin.run_id}, {pin.attempt_id}) exists with different content"
            )
        self._pins[key] = pin
        return pin

    def get_pin(self, *, run_id: str, attempt_id: str) -> ResearchStatePin | None:
        return self._pins.get((run_id, attempt_id))

    def load_state_version(
        self,
        state_version_id: UUID,
        *,
        strict: bool = True,
        knowledge_cutoff_at: datetime | None = None,
    ) -> LoadedResearchState:
        """Exact-version load. Never falls back to latest.

        When ``strict`` is true (default), legacy-null-known refs are omitted and
        entity rows with ``known_at`` after ``knowledge_cutoff_at`` (when provided)
        are excluded from the entity bags. The version envelope itself is always
        the exact stored :class:`ResearchStateVersion`.
        """
        version = self._versions.get(state_version_id)
        if version is None:
            raise ResearchStateMissingError(f"state_version_id {state_version_id} not found")

        cutoff: datetime | None = None
        if knowledge_cutoff_at is not None:
            cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")

        def _visible_known(known_at: datetime) -> bool:
            if cutoff is None:
                return True
            return known_at <= cutoff

        evidence = tuple(
            self._evidence[eid]
            for eid in version.manifest.evidence_ids
            if eid in self._evidence and _visible_known(self._evidence[eid].known_at)
        )
        beliefs = tuple(
            self._beliefs[bid]
            for bid in version.manifest.belief_version_ids
            if bid in self._beliefs and _visible_known(self._beliefs[bid].known_at)
        )
        events = tuple(
            self._expected_events[eid]
            for eid in version.manifest.expected_event_version_ids
            if eid in self._expected_events and _visible_known(self._expected_events[eid].known_at)
        )
        patches = tuple(
            self._patches[pid]
            for pid in version.manifest.patch_ids
            if pid in self._patches and _visible_known(self._patches[pid].known_at)
        )
        if strict:
            legacy: tuple[LegacyDocumentRef, ...] = ()
        else:
            legacy = tuple(
                self._legacy_refs[lid]
                for lid in version.manifest.legacy_ref_ids
                if lid in self._legacy_refs
            )

        return LoadedResearchState(
            version=version,
            evidence=evidence,
            beliefs=beliefs,
            expected_events=events,
            patches=patches,
            legacy_refs=legacy,
        )

    def exact_version_bytes(self, state_version_id: UUID) -> bytes:
        """Canonical JSON bytes of the stored version envelope (round-trip check)."""
        version = self._versions.get(state_version_id)
        if version is None:
            raise ResearchStateMissingError(f"state_version_id {state_version_id} not found")
        return _payload_bytes(version)


class EvidenceBundleConflict(RuntimeError):
    """Same evidence-bundle identity already stored with incompatible content."""


class EvidenceBundleError(RuntimeError):
    """Store refused an evidence-bundle write (missing lineage / ticker mismatch)."""


class EvidenceBundleMissingError(LookupError):
    """Exact evidence bundle / request / amendment not found."""


class EvidenceBundleStore:
    """Append-only H5 base + H6 amendment boundary (no upsert / update / delete).

    Dark-launch companion to :class:`ResearchStateStore`. SQL schema:
    ``090_olympus_evidence_bundles.sql``. Does not cut over H6 selection (WP11.3+).
    """

    def __init__(self) -> None:
        self._bases: dict[UUID, TickerEvidenceBundle] = {}
        self._run_ticker: dict[tuple[str, str], UUID] = {}
        self._requests: dict[UUID, MissingFactRequest] = {}
        self._amendments: dict[UUID, EvidenceBundleAmendment] = {}

    def _append_idempotent(
        self,
        *,
        store: dict[UUID, T],
        key: UUID,
        value: T,
        content_hash: str,
        existing_hash: str | None,
        label: str,
    ) -> T:
        if key in store:
            if existing_hash == content_hash:
                return store[key]
            raise EvidenceBundleConflict(f"{label} {key} exists with different content_hash")
        store[key] = value
        return value

    def append_base_bundle(self, bundle: TickerEvidenceBundle) -> TickerEvidenceBundle:
        """Insert immutable H5 base; exact retry is a no-op; one base per run/ticker."""
        run_key = (bundle.source_run_id, bundle.ticker)
        existing_id = self._run_ticker.get(run_key)
        if existing_id is not None and existing_id != bundle.bundle_id:
            raise EvidenceBundleConflict(
                f"base bundle already exists for run/ticker {bundle.source_run_id}/{bundle.ticker}"
            )
        existing = self._bases.get(bundle.bundle_id)
        stored = self._append_idempotent(
            store=self._bases,
            key=bundle.bundle_id,
            value=bundle,
            content_hash=bundle.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="bundle_id",
        )
        self._run_ticker[run_key] = stored.bundle_id
        return stored

    def append_missing_fact_request(self, request: MissingFactRequest) -> MissingFactRequest:
        """Insert a named missing-fact request linked to an existing base bundle."""
        base = self._bases.get(request.base_bundle_id)
        if base is None:
            raise EvidenceBundleError(
                f"missing base bundle {request.base_bundle_id} for MissingFactRequest"
            )
        if request.ticker != base.ticker:
            raise EvidenceBundleError(
                f"MissingFactRequest ticker {request.ticker} must match base {base.ticker}"
            )
        existing = self._requests.get(request.request_id)
        return self._append_idempotent(
            store=self._requests,
            key=request.request_id,
            value=request,
            content_hash=request.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="request_id",
        )

    def append_amendment(self, amendment: EvidenceBundleAmendment) -> EvidenceBundleAmendment:
        """Append H6 amendment; requires existing base + matching missing-fact request."""
        base = self._bases.get(amendment.base_bundle_id)
        if base is None:
            raise EvidenceBundleError(
                f"missing base bundle {amendment.base_bundle_id} for amendment"
            )
        request = self._requests.get(amendment.missing_fact_request_id)
        if request is None:
            raise EvidenceBundleError(
                f"missing missing-fact request {amendment.missing_fact_request_id} for amendment"
            )
        if request.base_bundle_id != amendment.base_bundle_id:
            raise EvidenceBundleError(
                "amendment missing-fact request is not linked to the named base bundle"
            )
        if amendment.ticker != base.ticker:
            raise EvidenceBundleError(
                f"amendment ticker {amendment.ticker} must match base {base.ticker}"
            )
        existing = self._amendments.get(amendment.amendment_id)
        return self._append_idempotent(
            store=self._amendments,
            key=amendment.amendment_id,
            value=amendment,
            content_hash=amendment.content_hash,
            existing_hash=None if existing is None else existing.content_hash,
            label="amendment_id",
        )

    def load_base_bundle(self, bundle_id: UUID) -> TickerEvidenceBundle:
        bundle = self._bases.get(bundle_id)
        if bundle is None:
            raise EvidenceBundleMissingError(f"bundle_id {bundle_id} not found")
        return bundle

    def base_bundle_count_for(self, *, run_id: str, ticker: str, content_hash: str) -> int:
        """Metric helper: count bases matching run/ticker/content (0 or 1)."""
        return sum(
            1
            for bundle in self._bases.values()
            if bundle.source_run_id == run_id
            and bundle.ticker == ticker.strip().upper()
            and bundle.content_hash == content_hash
        )

    def unlinked_amendment_count(self) -> int:
        """Metric helper: amendments whose base or request is absent (always 0 if healthy)."""
        return sum(
            1
            for amendment in self._amendments.values()
            if amendment.base_bundle_id not in self._bases
            or amendment.missing_fact_request_id not in self._requests
        )


__all__ = [
    "EvidenceBundleConflict",
    "EvidenceBundleError",
    "EvidenceBundleMissingError",
    "EvidenceBundleStore",
    "LoadedResearchState",
    "ResearchStateConflict",
    "ResearchStateError",
    "ResearchStateMissingError",
    "ResearchStateStore",
]
