"""Deterministic role-specific context capsules and manifests (#2938 / WP14.1).

Compiles bounded, inspectable role inputs from one exact pinned
:class:`~digiquant.dashboard.research_retrieval.models.ResearchStateVersion`
plus optional bundle/amendment/attention artifacts. Prose and raw transcripts
are never authoritative — structured entity IDs and content hashes are.

WP14.2–14.4 wire these capsules into H5/H6/H7 provider calls; this module is
models + compiler entrypoints only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid5

from pydantic import Field, field_validator, model_validator

from digiquant.dashboard.research_retrieval.models import (
    EvidenceBundleAmendment,
    NonEmptyStr,
    ResearchStateModel,
    SchemaVersion,
    TickerEvidenceBundle,
    content_digest,
)
from digiquant.dashboard.research_retrieval.planner import AttentionPlan
from digiquant.dashboard.research_retrieval.store import LoadedResearchState

_CONTEXT_MANIFEST_ID_NS = UUID("c1a0e50a-4b8d-5f2a-9c17-3d6e8f0a1b22")
_CONTEXT_CAPSULE_ID_NS = UUID("c1a0e50b-4b8d-5f2a-9c17-3d6e8f0a1b22")

CONTEXT_SCHEMA_VERSION: int = 1
_TOKEN_BYTES_DIVISOR: int = 4
CapsuleBody = Annotated[str, Field(min_length=0)]


class ContextRole(StrEnum):
    """portfolio/research roles that receive compiled context capsules."""

    H5_ANALYST = "h5_analyst"
    H6_DELIBERATION = "h6_deliberation"
    H7_PM = "h7_pm"


class ContextItemKind(StrEnum):
    """Structured entity kinds referenced in a context capsule."""

    EVIDENCE = "evidence"
    BELIEF = "belief"
    EXPECTED_EVENT = "expected_event"
    PATCH = "patch"
    TICKER_BUNDLE = "ticker_bundle"
    BUNDLE_AMENDMENT = "bundle_amendment"
    ATTENTION_DECISION = "attention_decision"
    LEGACY_REF = "legacy_ref"


class ContextOmissionReason(StrEnum):
    """Typed reason an entity was excluded from a role capsule."""

    ROLE_NOT_ALLOWED = "role_not_allowed"
    BYTE_BUDGET_EXCEEDED = "byte_budget_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    UNPINNED = "unpinned"
    CROSS_TICKER = "cross_ticker"
    NOT_IN_DELTA = "not_in_delta"
    LEGACY_MANIFEST_ONLY = "legacy_manifest_only"
    UNVERSIONED_BUNDLE = "unversioned_bundle"


_DEFAULT_POLICIES: dict[ContextRole, dict[str, object]] = {
    ContextRole.H5_ANALYST: {
        "allowed_kinds": (
            ContextItemKind.EVIDENCE,
            ContextItemKind.BELIEF,
            ContextItemKind.EXPECTED_EVENT,
            ContextItemKind.PATCH,
            ContextItemKind.TICKER_BUNDLE,
        ),
        "max_bytes": 32_000,
        "max_estimated_tokens": 8_000,
        "requires_ticker": True,
        "delta_evidence_only": True,
    },
    ContextRole.H6_DELIBERATION: {
        "allowed_kinds": (
            ContextItemKind.TICKER_BUNDLE,
            ContextItemKind.BUNDLE_AMENDMENT,
            ContextItemKind.EVIDENCE,
        ),
        "max_bytes": 24_000,
        "max_estimated_tokens": 6_000,
        "requires_ticker": True,
        "delta_evidence_only": False,
    },
    ContextRole.H7_PM: {
        "allowed_kinds": (
            ContextItemKind.BELIEF,
            ContextItemKind.EXPECTED_EVENT,
            ContextItemKind.PATCH,
            ContextItemKind.ATTENTION_DECISION,
        ),
        "max_bytes": 48_000,
        "max_estimated_tokens": 12_000,
        "requires_ticker": False,
        "delta_evidence_only": False,
    },
}


class RoleContextPolicy(ResearchStateModel):
    """Versioned allowlist and budget for one role's context compiler."""

    role: ContextRole
    allowed_kinds: tuple[ContextItemKind, ...]
    max_bytes: Annotated[int, Field(ge=1)]
    max_estimated_tokens: Annotated[int, Field(ge=1)]
    requires_ticker: bool = False
    delta_evidence_only: bool = False
    schema_version: SchemaVersion = CONTEXT_SCHEMA_VERSION
    content_hash: NonEmptyStr

    @field_validator("allowed_kinds", mode="before")
    @classmethod
    def _coerce_allowed_kinds(cls, value: object) -> tuple[ContextItemKind, ...]:
        if isinstance(value, (list, tuple)):
            kinds = tuple(ContextItemKind(str(item)) for item in value)
            return tuple(sorted(set(kinds), key=lambda item: item.value))
        return value  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_policy_hash(self) -> RoleContextPolicy:
        expected = role_context_policy_content_hash(
            self.role,
            allowed_kinds=self.allowed_kinds,
            max_bytes=self.max_bytes,
            max_estimated_tokens=self.max_estimated_tokens,
            requires_ticker=self.requires_ticker,
            delta_evidence_only=self.delta_evidence_only,
            schema_version=self.schema_version,
        )
        if self.content_hash != expected:
            raise ValueError("content_hash must match canonical RoleContextPolicy digest")
        return self


class ContextItem(ResearchStateModel):
    """One pinned structured entity included in a role capsule."""

    kind: ContextItemKind
    entity_id: UUID
    state_version_id: UUID
    content_hash: NonEmptyStr
    ticker: NonEmptyStr | None = None
    byte_size: Annotated[int, Field(ge=0)]

    @property
    def entity_ref(self) -> str:
        return f"{self.kind.value}:{self.entity_id}"


class ContextOmission(ResearchStateModel):
    """Audit record for an excluded entity or class of entities."""

    reason: ContextOmissionReason
    kind: ContextItemKind | None = None
    entity_id: NonEmptyStr | None = None
    detail: NonEmptyStr | None = None


class ContextManifest(ResearchStateModel):
    """Exact manifest of included entity IDs and omissions for one role compile."""

    manifest_id: UUID
    role: ContextRole
    state_version_id: UUID
    policy_content_hash: NonEmptyStr
    included_entity_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    omissions: tuple[ContextOmission, ...] = Field(default_factory=tuple)
    content_hash: NonEmptyStr
    byte_size: Annotated[int, Field(ge=0)]
    estimated_tokens: Annotated[int, Field(ge=0)]
    schema_version: SchemaVersion = CONTEXT_SCHEMA_VERSION

    @field_validator("included_entity_ids", "omissions", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("included_entity_ids")
    @classmethod
    def _sort_included(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))

    @model_validator(mode="after")
    def _validate_manifest(self) -> ContextManifest:
        expected_hash = context_manifest_content_hash(
            role=self.role,
            state_version_id=self.state_version_id,
            policy_content_hash=self.policy_content_hash,
            included_entity_ids=self.included_entity_ids,
            omissions=self.omissions,
            byte_size=self.byte_size,
            estimated_tokens=self.estimated_tokens,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ContextManifest digest")
        expected_id = context_manifest_id(
            role=self.role,
            state_version_id=self.state_version_id,
            policy_content_hash=self.policy_content_hash,
            included_entity_ids=self.included_entity_ids,
        )
        if self.manifest_id != expected_id:
            raise ValueError("manifest_id must match role/state/policy/included IDs")
        return self


class ContextCapsule(ResearchStateModel):
    """Bounded structured body compiled for one role under one state pin."""

    capsule_id: UUID
    manifest_id: UUID
    role: ContextRole
    state_version_id: UUID
    items: tuple[ContextItem, ...] = Field(default_factory=tuple)
    body: CapsuleBody
    content_hash: NonEmptyStr
    byte_size: Annotated[int, Field(ge=0)]
    estimated_tokens: Annotated[int, Field(ge=0)]
    schema_version: SchemaVersion = CONTEXT_SCHEMA_VERSION

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_capsule(self) -> ContextCapsule:
        expected_hash = context_capsule_content_hash(
            manifest_id=self.manifest_id,
            role=self.role,
            state_version_id=self.state_version_id,
            items=self.items,
            body=self.body,
        )
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical ContextCapsule digest")
        expected_id = context_capsule_id(manifest_content_hash=self.content_hash)
        if self.capsule_id != expected_id:
            raise ValueError("capsule_id must be UUID5 of manifest content_hash")
        return self


@dataclass(frozen=True)
class ContextCompileInput:
    """Inputs for one deterministic role context compile."""

    role: ContextRole
    state: LoadedResearchState
    ticker: str | None = None
    bundle: TickerEvidenceBundle | None = None
    amendment: EvidenceBundleAmendment | None = None
    attention_plan: AttentionPlan | None = None
    changed_evidence_ids: frozenset[UUID] | None = None
    policy: RoleContextPolicy | None = None


@dataclass(frozen=True)
class _Candidate:
    kind: ContextItemKind
    entity_id: UUID
    content_hash: str
    ticker: str | None
    payload: str
    h6_bundle_evidence: bool = False


def role_context_policy_content_hash(
    role: ContextRole,
    *,
    allowed_kinds: Sequence[ContextItemKind],
    max_bytes: int,
    max_estimated_tokens: int,
    requires_ticker: bool,
    delta_evidence_only: bool,
    schema_version: int = CONTEXT_SCHEMA_VERSION,
) -> str:
    """Canonical SHA-256 digest for a role policy body."""
    return content_digest(
        {
            "role": role.value,
            "allowed_kinds": sorted(kind.value for kind in allowed_kinds),
            "max_bytes": max_bytes,
            "max_estimated_tokens": max_estimated_tokens,
            "requires_ticker": requires_ticker,
            "delta_evidence_only": delta_evidence_only,
            "schema_version": schema_version,
        }
    )


def default_role_context_policy(role: ContextRole) -> RoleContextPolicy:
    """Return the bundled default policy for *role*."""
    body = _DEFAULT_POLICIES[role]
    allowed = tuple(ContextItemKind(str(item)) for item in body["allowed_kinds"])  # type: ignore[index]
    digest = role_context_policy_content_hash(
        role,
        allowed_kinds=allowed,
        max_bytes=int(body["max_bytes"]),  # type: ignore[arg-type]
        max_estimated_tokens=int(body["max_estimated_tokens"]),  # type: ignore[arg-type]
        requires_ticker=bool(body["requires_ticker"]),
        delta_evidence_only=bool(body["delta_evidence_only"]),
    )
    return RoleContextPolicy(
        role=role,
        allowed_kinds=allowed,
        max_bytes=int(body["max_bytes"]),  # type: ignore[arg-type]
        max_estimated_tokens=int(body["max_estimated_tokens"]),  # type: ignore[arg-type]
        requires_ticker=bool(body["requires_ticker"]),
        delta_evidence_only=bool(body["delta_evidence_only"]),
        content_hash=digest,
    )


def context_manifest_id(
    *,
    role: ContextRole,
    state_version_id: UUID,
    policy_content_hash: str,
    included_entity_ids: Sequence[str],
) -> UUID:
    joined = "|".join(sorted(included_entity_ids))
    return uuid5(
        _CONTEXT_MANIFEST_ID_NS,
        f"{role.value}:{state_version_id.hex}:{policy_content_hash}:{joined}",
    )


def context_manifest_content_hash(
    *,
    role: ContextRole,
    state_version_id: UUID,
    policy_content_hash: str,
    included_entity_ids: Sequence[str],
    omissions: Sequence[ContextOmission],
    byte_size: int,
    estimated_tokens: int,
) -> str:
    return content_digest(
        {
            "role": role.value,
            "state_version_id": state_version_id.hex,
            "policy_content_hash": policy_content_hash,
            "included_entity_ids": sorted(included_entity_ids),
            "omissions": [item.model_dump(mode="json") for item in omissions],
            "byte_size": byte_size,
            "estimated_tokens": estimated_tokens,
            "schema_version": CONTEXT_SCHEMA_VERSION,
        }
    )


def context_capsule_id(*, manifest_content_hash: str) -> UUID:
    return uuid5(_CONTEXT_CAPSULE_ID_NS, manifest_content_hash.strip())


def context_capsule_content_hash(
    *,
    manifest_id: UUID,
    role: ContextRole,
    state_version_id: UUID,
    items: Sequence[ContextItem],
    body: str,
) -> str:
    return content_digest(
        {
            "manifest_id": manifest_id.hex,
            "role": role.value,
            "state_version_id": state_version_id.hex,
            "items": [
                {
                    "kind": item.kind.value,
                    "entity_id": item.entity_id.hex,
                    "content_hash": item.content_hash,
                }
                for item in items
            ],
            "body": body,
            "schema_version": CONTEXT_SCHEMA_VERSION,
        }
    )


def _estimate_tokens(byte_size: int) -> int:
    return max(1, byte_size // _TOKEN_BYTES_DIVISOR)


def _item_byte_size(payload: str) -> int:
    return len(payload.encode("utf-8"))


def _serialize_item(candidate: _Candidate, *, state_version_id: UUID) -> str:
    return (
        f'{{"kind":"{candidate.kind.value}","entity_id":"{candidate.entity_id}",'
        f'"state_version_id":"{state_version_id}",'
        f'"content_hash":"{candidate.content_hash}"}}'
    )


def _require_pinned_bundle(
    bundle: TickerEvidenceBundle,
    *,
    state_version_id: UUID,
    ticker: str | None,
) -> None:
    if bundle.state_version_id != state_version_id:
        raise ValueError(
            "bundle.state_version_id must match pinned state_version_id "
            f"({bundle.state_version_id} != {state_version_id})"
        )
    if ticker is not None and bundle.ticker != ticker.strip().upper():
        raise ValueError(f"bundle ticker {bundle.ticker!r} does not match {ticker!r}")


def _collect_candidates(inp: ContextCompileInput) -> tuple[list[_Candidate], list[ContextOmission]]:
    state = inp.state
    state_version_id = state.version.state_version_id
    policy = inp.policy or default_role_context_policy(inp.role)
    allowed = frozenset(policy.allowed_kinds)

    omissions: list[ContextOmission] = []
    candidates: list[_Candidate] = []

    def maybe_add(
        *,
        kind: ContextItemKind,
        entity_id: UUID,
        content_hash: str,
        ticker: str | None,
        payload: str,
        h6_bundle_evidence: bool = False,
    ) -> None:
        ref = f"{kind.value}:{entity_id}"
        if kind is ContextItemKind.LEGACY_REF:
            omissions.append(
                ContextOmission(
                    kind=kind,
                    entity_id=ref,
                    reason=ContextOmissionReason.LEGACY_MANIFEST_ONLY,
                )
            )
            return
        if kind not in allowed:
            omissions.append(
                ContextOmission(
                    kind=kind,
                    entity_id=ref,
                    reason=ContextOmissionReason.ROLE_NOT_ALLOWED,
                )
            )
            return
        if inp.role is ContextRole.H6_DELIBERATION and kind is ContextItemKind.EVIDENCE:
            if not h6_bundle_evidence:
                omissions.append(
                    ContextOmission(
                        kind=kind,
                        entity_id=ref,
                        reason=ContextOmissionReason.ROLE_NOT_ALLOWED,
                        detail="h6_evidence_must_come_from_bundle_or_amendment",
                    )
                )
                return
        if (
            inp.policy is not None
            and inp.policy.delta_evidence_only
            and kind is ContextItemKind.EVIDENCE
        ):
            changed = inp.changed_evidence_ids or frozenset()
            if entity_id not in changed:
                omissions.append(
                    ContextOmission(
                        kind=kind,
                        entity_id=ref,
                        reason=ContextOmissionReason.NOT_IN_DELTA,
                    )
                )
                return
        if ticker is not None and inp.ticker is not None:
            if ticker.strip().upper() != inp.ticker.strip().upper():
                omissions.append(
                    ContextOmission(
                        kind=kind,
                        entity_id=ref,
                        reason=ContextOmissionReason.CROSS_TICKER,
                    )
                )
                return
        candidates.append(
            _Candidate(
                kind=kind,
                entity_id=entity_id,
                content_hash=content_hash,
                ticker=ticker,
                payload=payload,
                h6_bundle_evidence=h6_bundle_evidence,
            )
        )

    for record in state.evidence:
        maybe_add(
            kind=ContextItemKind.EVIDENCE,
            entity_id=record.evidence_id,
            content_hash=record.content_hash,
            ticker=inp.ticker,
            payload=record.summary,
        )

    for belief in state.beliefs:
        maybe_add(
            kind=ContextItemKind.BELIEF,
            entity_id=belief.belief_version_id,
            content_hash=belief.content_hash,
            ticker=inp.ticker,
            payload=belief.statement,
        )

    for event in state.expected_events:
        maybe_add(
            kind=ContextItemKind.EXPECTED_EVENT,
            entity_id=event.expected_event_version_id,
            content_hash=event.content_hash,
            ticker=inp.ticker,
            payload=event.label,
        )

    for patch in state.patches:
        maybe_add(
            kind=ContextItemKind.PATCH,
            entity_id=patch.patch_id,
            content_hash=patch.content_hash,
            ticker=inp.ticker,
            payload=patch.summary,
        )

    for legacy in state.legacy_refs:
        maybe_add(
            kind=ContextItemKind.LEGACY_REF,
            entity_id=legacy.legacy_ref_id,
            content_hash=legacy.source_hash,
            ticker=None,
            payload=legacy.document_key,
        )

    if inp.bundle is not None:
        _require_pinned_bundle(inp.bundle, state_version_id=state_version_id, ticker=inp.ticker)
        maybe_add(
            kind=ContextItemKind.TICKER_BUNDLE,
            entity_id=inp.bundle.bundle_id,
            content_hash=inp.bundle.content_hash,
            ticker=inp.bundle.ticker,
            payload=inp.bundle.source,
        )
        if inp.role is ContextRole.H6_DELIBERATION:
            for evidence_id in inp.bundle.evidence_ids:
                record = next(
                    (item for item in state.evidence if item.evidence_id == evidence_id), None
                )
                if record is None:
                    continue
                maybe_add(
                    kind=ContextItemKind.EVIDENCE,
                    entity_id=record.evidence_id,
                    content_hash=record.content_hash,
                    ticker=inp.bundle.ticker,
                    payload=record.summary,
                    h6_bundle_evidence=True,
                )

    if inp.amendment is not None:
        if inp.bundle is None or inp.amendment.base_bundle_id != inp.bundle.bundle_id:
            raise ValueError("amendment must reference the supplied base bundle")
        maybe_add(
            kind=ContextItemKind.BUNDLE_AMENDMENT,
            entity_id=inp.amendment.amendment_id,
            content_hash=inp.amendment.content_hash,
            ticker=inp.amendment.ticker,
            payload=inp.amendment.source,
        )
        if inp.role is ContextRole.H6_DELIBERATION:
            for evidence_id in inp.amendment.evidence_ids:
                record = next(
                    (item for item in state.evidence if item.evidence_id == evidence_id), None
                )
                if record is None:
                    continue
                maybe_add(
                    kind=ContextItemKind.EVIDENCE,
                    entity_id=record.evidence_id,
                    content_hash=record.content_hash,
                    ticker=inp.amendment.ticker,
                    payload=record.summary,
                    h6_bundle_evidence=True,
                )

    if inp.attention_plan is not None:
        if inp.attention_plan.state_version_id is None:
            raise ValueError("attention_plan.state_version_id is required for context compile")
        if inp.attention_plan.state_version_id != state_version_id:
            raise ValueError("attention_plan.state_version_id must match pinned state")
        for decision in inp.attention_plan.decisions:
            decision_key = decision.target_key
            digest = content_digest(
                {
                    "target_key": decision.target_key,
                    "mode": decision.mode.value,
                    "reason": decision.reason.value,
                }
            )
            maybe_add(
                kind=ContextItemKind.ATTENTION_DECISION,
                entity_id=uuid5(_CONTEXT_MANIFEST_ID_NS, decision_key),
                content_hash=digest,
                ticker=decision.target_key if ":" not in decision.target_key else None,
                payload=decision_key,
            )

    candidates.sort(key=lambda item: (item.kind.value, item.entity_id.hex))
    omissions.sort(key=lambda item: (item.reason.value, item.entity_id or "", item.kind or ""))
    return candidates, omissions


def _apply_budget(
    candidates: Sequence[_Candidate],
    omissions: list[ContextOmission],
    *,
    policy: RoleContextPolicy,
    state_version_id: UUID,
) -> tuple[tuple[ContextItem, ...], tuple[str, ...], int]:
    included_items: list[ContextItem] = []
    included_refs: list[str] = []
    total_bytes = 0
    total_tokens = 0

    for candidate in candidates:
        payload = _serialize_item(candidate, state_version_id=state_version_id)
        item_bytes = _item_byte_size(payload)
        item_tokens = _estimate_tokens(item_bytes)
        next_bytes = total_bytes + item_bytes
        next_tokens = total_tokens + item_tokens
        ref = f"{candidate.kind.value}:{candidate.entity_id}"
        if next_bytes > policy.max_bytes:
            omissions.append(
                ContextOmission(
                    kind=candidate.kind,
                    entity_id=ref,
                    reason=ContextOmissionReason.BYTE_BUDGET_EXCEEDED,
                )
            )
            continue
        if next_tokens > policy.max_estimated_tokens:
            omissions.append(
                ContextOmission(
                    kind=candidate.kind,
                    entity_id=ref,
                    reason=ContextOmissionReason.TOKEN_BUDGET_EXCEEDED,
                )
            )
            continue
        included_items.append(
            ContextItem(
                kind=candidate.kind,
                entity_id=candidate.entity_id,
                state_version_id=state_version_id,
                content_hash=candidate.content_hash,
                ticker=candidate.ticker,
                byte_size=item_bytes,
            )
        )
        included_refs.append(ref)
        total_bytes = next_bytes
        total_tokens = next_tokens

    return tuple(included_items), tuple(sorted(included_refs)), total_bytes


def compile_context_manifest(inp: ContextCompileInput) -> ContextManifest:
    """Compile the manifest for *inp* without building the capsule body."""
    policy = inp.policy or default_role_context_policy(inp.role)
    if policy.requires_ticker and not inp.ticker:
        raise ValueError(f"{inp.role.value} requires ticker")
    state_version_id = inp.state.version.state_version_id
    candidates, omissions = _collect_candidates(
        ContextCompileInput(
            role=inp.role,
            state=inp.state,
            ticker=inp.ticker,
            bundle=inp.bundle,
            amendment=inp.amendment,
            attention_plan=inp.attention_plan,
            changed_evidence_ids=inp.changed_evidence_ids,
            policy=policy,
        )
    )
    items, included_refs, byte_size = _apply_budget(
        candidates,
        omissions,
        policy=policy,
        state_version_id=state_version_id,
    )
    body = "\n".join(
        _serialize_item(c, state_version_id=state_version_id)
        for c in candidates
        if f"{c.kind.value}:{c.entity_id}" in included_refs
    )
    # body not used in manifest; recompute bytes/tokens from items
    del body
    estimated_tokens = _estimate_tokens(byte_size) if byte_size else 0
    if items:
        estimated_tokens = sum(_estimate_tokens(item.byte_size) for item in items)
    manifest_id = context_manifest_id(
        role=inp.role,
        state_version_id=state_version_id,
        policy_content_hash=policy.content_hash,
        included_entity_ids=included_refs,
    )
    content_hash = context_manifest_content_hash(
        role=inp.role,
        state_version_id=state_version_id,
        policy_content_hash=policy.content_hash,
        included_entity_ids=included_refs,
        omissions=tuple(omissions),
        byte_size=byte_size,
        estimated_tokens=estimated_tokens,
    )
    return ContextManifest(
        manifest_id=manifest_id,
        role=inp.role,
        state_version_id=state_version_id,
        policy_content_hash=policy.content_hash,
        included_entity_ids=tuple(included_refs),
        omissions=tuple(omissions),
        content_hash=content_hash,
        byte_size=byte_size,
        estimated_tokens=estimated_tokens,
    )


def compile_context_capsule(inp: ContextCompileInput) -> tuple[ContextCapsule, ContextManifest]:
    """Compile a bounded role capsule and its manifest from *inp*."""
    manifest = compile_context_manifest(inp)
    policy = inp.policy or default_role_context_policy(inp.role)
    state_version_id = inp.state.version.state_version_id
    candidates, _ = _collect_candidates(
        ContextCompileInput(
            role=inp.role,
            state=inp.state,
            ticker=inp.ticker,
            bundle=inp.bundle,
            amendment=inp.amendment,
            attention_plan=inp.attention_plan,
            changed_evidence_ids=inp.changed_evidence_ids,
            policy=policy,
        )
    )
    included = set(manifest.included_entity_ids)
    items: list[ContextItem] = []
    body_lines: list[str] = []
    for candidate in candidates:
        ref = f"{candidate.kind.value}:{candidate.entity_id}"
        if ref not in included:
            continue
        serialized = _serialize_item(candidate, state_version_id=state_version_id)
        body_lines.append(serialized)
        items.append(
            ContextItem(
                kind=candidate.kind,
                entity_id=candidate.entity_id,
                state_version_id=state_version_id,
                content_hash=candidate.content_hash,
                ticker=candidate.ticker,
                byte_size=_item_byte_size(serialized),
            )
        )
    body = "\n".join(body_lines)
    content_hash = context_capsule_content_hash(
        manifest_id=manifest.manifest_id,
        role=inp.role,
        state_version_id=state_version_id,
        items=tuple(items),
        body=body,
    )
    capsule = ContextCapsule(
        capsule_id=context_capsule_id(manifest_content_hash=content_hash),
        manifest_id=manifest.manifest_id,
        role=inp.role,
        state_version_id=state_version_id,
        items=tuple(items),
        body=body,
        content_hash=content_hash,
        byte_size=manifest.byte_size,
        estimated_tokens=manifest.estimated_tokens,
    )
    return capsule, manifest


__all__ = [
    "CONTEXT_SCHEMA_VERSION",
    "ContextCapsule",
    "ContextCompileInput",
    "ContextItem",
    "ContextItemKind",
    "ContextManifest",
    "ContextOmission",
    "ContextOmissionReason",
    "ContextRole",
    "RoleContextPolicy",
    "compile_context_capsule",
    "compile_context_manifest",
    "context_capsule_content_hash",
    "context_capsule_id",
    "context_manifest_content_hash",
    "context_manifest_id",
    "default_role_context_policy",
    "role_context_policy_content_hash",
]
