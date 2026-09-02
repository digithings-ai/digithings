"""Deterministic prose views from exact research-state versions (#2877 / WP12.5).

Compiled briefs/digests are presentation only. The pinned
:class:`~digiquant.dashboard.research_retrieval.models.ResearchStateVersion`
remains authoritative. Never parse prose into claims; never ``load_latest``.

Entity order is canonical (sorted by UUID hex). Every view embeds
``state_version_id``, state ``content_hash``, and ``schema_version``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Annotated, TypeVar
from uuid import UUID

from pydantic import Field

from digiquant.dashboard.research_retrieval.models import (
    BeliefVersion,
    EvidenceRecord,
    ExpectedEventVersion,
    NonEmptyStr,
    ResearchPatch,
    ResearchStateModel,
    SchemaVersion,
    content_digest,
)
from digiquant.dashboard.research_retrieval.store import (
    LoadedResearchState,
    ResearchStateStore,
)

T = TypeVar("T")

# Markdown views exceed NonEmptyStr's 500-char identity-field bound.
MarkdownBody = Annotated[str, Field(min_length=1)]

VIEW_SCHEMA_VERSION: int = 1
COMPILED_BRIEF_DOCUMENT_KEY = "research-state-brief"
COMPILED_DIGEST_DOCUMENT_KEY = "research-state-digest"


class ResearchViewKind(StrEnum):
    """Compiled prose surface kind."""

    BRIEF = "brief"
    DIGEST = "digest"


class CompiledResearchView(ResearchStateModel):
    """One deterministic markdown view of an exact research-state version."""

    kind: ResearchViewKind
    state_version_id: UUID
    state_content_hash: NonEmptyStr
    state_schema_version: SchemaVersion
    manifest_content_hash: NonEmptyStr
    view_schema_version: SchemaVersion = VIEW_SCHEMA_VERSION
    markdown: MarkdownBody
    content_hash: NonEmptyStr


class ResearchViewPublishBlocked(RuntimeError):
    """Structured write failed — refuse misleading compiled-view publication."""


def _sorted_by_id(items: Sequence[T], *, key: Callable[[T], UUID]) -> tuple[T, ...]:
    return tuple(sorted(items, key=lambda item: key(item).hex))


def _front_matter(
    *,
    kind: ResearchViewKind,
    state_version_id: UUID,
    state_content_hash: str,
    state_schema_version: int,
    manifest_content_hash: str,
    view_schema_version: int,
) -> list[str]:
    return [
        "---",
        f"dashboard_research_view: {kind.value}",
        f"view_schema_version: {view_schema_version}",
        f"state_version_id: {state_version_id}",
        f"state_content_hash: {state_content_hash}",
        f"state_schema_version: {state_schema_version}",
        f"manifest_content_hash: {manifest_content_hash}",
        "---",
        "",
    ]


def _render_belief(belief: BeliefVersion) -> str:
    return (
        f"- `{belief.belief_version_id}` "
        f"(belief_id=`{belief.belief_id}`, status={belief.status.value}, "
        f"confidence={belief.confidence}, horizon={belief.horizon_sessions}): "
        f"{belief.statement}"
    )


def _render_event(event: ExpectedEventVersion) -> str:
    return (
        f"- `{event.expected_event_version_id}` "
        f"(event_id=`{event.expected_event_id}`, status={event.status.value}, "
        f"event_time={event.event_time.isoformat()}): {event.label}"
    )


def _render_evidence(record: EvidenceRecord) -> str:
    return (
        f"- `{record.evidence_id}` "
        f"(source={record.source}, authority={record.authority}): {record.summary}"
    )


def _render_patch(patch: ResearchPatch) -> str:
    return (
        f"- `{patch.patch_id}` "
        f"(kind={patch.target_kind.value}, mode={patch.mode.value}, "
        f"target={patch.target_id}): {patch.summary}"
    )


def _section(title: str, lines: Sequence[str]) -> list[str]:
    if not lines:
        return [f"## {title}", "", "_(none)_", ""]
    return [f"## {title}", "", *lines, ""]


def _compile_markdown(
    loaded: LoadedResearchState,
    *,
    kind: ResearchViewKind,
) -> str:
    version = loaded.version
    beliefs = _sorted_by_id(loaded.beliefs, key=lambda item: item.belief_version_id)
    events = _sorted_by_id(loaded.expected_events, key=lambda item: item.expected_event_version_id)
    evidence = _sorted_by_id(loaded.evidence, key=lambda item: item.evidence_id)
    patches = _sorted_by_id(loaded.patches, key=lambda item: item.patch_id)

    lines = _front_matter(
        kind=kind,
        state_version_id=version.state_version_id,
        state_content_hash=version.content_hash,
        state_schema_version=version.schema_version,
        manifest_content_hash=version.manifest.content_hash,
        view_schema_version=VIEW_SCHEMA_VERSION,
    )

    if kind is ResearchViewKind.BRIEF:
        lines.append("# Research state brief")
        lines.append("")
        lines.append(
            "Deterministic view of pinned structured research state. "
            "Not an independent source of truth."
        )
        lines.append("")
        lines.extend(_section("Beliefs", [_render_belief(item) for item in beliefs]))
        lines.extend(_section("Expected events", [_render_event(item) for item in events]))
        lines.extend(_section("Evidence", [_render_evidence(item) for item in evidence]))
        lines.extend(_section("Patches", [_render_patch(item) for item in patches]))
    else:
        lines.append("# Research state digest")
        lines.append("")
        lines.append(
            "Compact deterministic digest of pinned structured research state. "
            "Not an independent source of truth."
        )
        lines.append("")
        lines.append("## Counts")
        lines.append("")
        lines.append(f"- beliefs: {len(beliefs)}")
        lines.append(f"- expected_events: {len(events)}")
        lines.append(f"- evidence: {len(evidence)}")
        lines.append(f"- patches: {len(patches)}")
        lines.append("")
        lines.extend(
            _section(
                "Beliefs",
                [_render_belief(item) for item in beliefs],
            )
        )
        lines.extend(
            _section(
                "Expected events",
                [_render_event(item) for item in events],
            )
        )

    # Stable trailing newline.
    text = "\n".join(lines).rstrip() + "\n"
    return text


def _view_content_hash(
    *,
    kind: ResearchViewKind,
    state_version_id: UUID,
    state_content_hash: str,
    state_schema_version: int,
    manifest_content_hash: str,
    view_schema_version: int,
    markdown: str,
) -> str:
    return content_digest(
        {
            "kind": kind.value,
            "state_version_id": state_version_id.hex,
            "state_content_hash": state_content_hash,
            "state_schema_version": state_schema_version,
            "manifest_content_hash": manifest_content_hash,
            "view_schema_version": view_schema_version,
            "markdown": markdown,
        }
    )


def compile_research_view(
    loaded: LoadedResearchState,
    *,
    kind: ResearchViewKind,
) -> CompiledResearchView:
    """Compile one deterministic prose view from an exact loaded state version."""
    version = loaded.version
    markdown = _compile_markdown(loaded, kind=kind)
    digest = _view_content_hash(
        kind=kind,
        state_version_id=version.state_version_id,
        state_content_hash=version.content_hash,
        state_schema_version=version.schema_version,
        manifest_content_hash=version.manifest.content_hash,
        view_schema_version=VIEW_SCHEMA_VERSION,
        markdown=markdown,
    )
    return CompiledResearchView(
        kind=kind,
        state_version_id=version.state_version_id,
        state_content_hash=version.content_hash,
        state_schema_version=version.schema_version,
        manifest_content_hash=version.manifest.content_hash,
        view_schema_version=VIEW_SCHEMA_VERSION,
        markdown=markdown,
        content_hash=digest,
    )


def compile_research_brief(loaded: LoadedResearchState) -> CompiledResearchView:
    """Full entity listing brief for one exact state version."""
    return compile_research_view(loaded, kind=ResearchViewKind.BRIEF)


def compile_research_digest(loaded: LoadedResearchState) -> CompiledResearchView:
    """Compact digest for one exact state version."""
    return compile_research_view(loaded, kind=ResearchViewKind.DIGEST)


def compile_views_from_store(
    store: ResearchStateStore,
    state_version_id: UUID,
    *,
    strict: bool = True,
) -> tuple[CompiledResearchView, CompiledResearchView]:
    """Load one exact version and compile brief + digest (no latest fallback)."""
    loaded = store.load_state_version(state_version_id, strict=strict)
    return compile_research_brief(loaded), compile_research_digest(loaded)


def require_structured_write_ok(*, structured_write_ok: bool) -> None:
    """Fail closed when structured persistence did not succeed."""
    if not structured_write_ok:
        raise ResearchViewPublishBlocked(
            "structured research-state write failed; refusing compiled view publication"
        )


def publish_compiled_views(
    *,
    views: Sequence[CompiledResearchView],
    structured_write_ok: bool,
    publisher: Callable[[CompiledResearchView], None],
) -> tuple[CompiledResearchView, ...]:
    """Publish compiled views only when structured write path is safe.

    Raises :class:`ResearchViewPublishBlocked` when ``structured_write_ok`` is
    false so callers cannot emit views that imply successful structured state.
    """
    require_structured_write_ok(structured_write_ok=structured_write_ok)
    published: list[CompiledResearchView] = []
    for view in views:
        publisher(view)
        published.append(view)
    return tuple(published)


def document_key_for_view(kind: ResearchViewKind) -> str:
    """Stable document_key for dual-write of a compiled view."""
    if kind is ResearchViewKind.BRIEF:
        return COMPILED_BRIEF_DOCUMENT_KEY
    return COMPILED_DIGEST_DOCUMENT_KEY


__all__ = [
    "COMPILED_BRIEF_DOCUMENT_KEY",
    "COMPILED_DIGEST_DOCUMENT_KEY",
    "VIEW_SCHEMA_VERSION",
    "CompiledResearchView",
    "ResearchViewKind",
    "ResearchViewPublishBlocked",
    "compile_research_brief",
    "compile_research_digest",
    "compile_research_view",
    "compile_views_from_store",
    "document_key_for_view",
    "publish_compiled_views",
    "require_structured_write_ok",
]
