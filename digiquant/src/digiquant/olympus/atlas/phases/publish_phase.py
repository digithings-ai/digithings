"""Publish phase — upsert fresh segments, digest, and optional 7C/7D to Supabase.

Skips carried slots. Monthly runs omit this phase.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.inspectable_io import (
    publish_bias_row_document,
    publish_inputs_document,
)
from digiquant.olympus.atlas.segments import compose_legacy_digest_body
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Phase7DigestPayload,
    PublishedArtifact,
    SegmentSlot,
)
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    publish_daily_snapshot,
    publish_document,
    publish_document_delta,
)
from digiquant.olympus.attention_plan_graph import maybe_publish_attention_plan_shadow
from digiquant.olympus.attention_plan_io import ATTENTION_PLAN_DOCUMENT_KEY
from digiquant.olympus.overlay.persist import is_private_workspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishDeps:
    """Wiring deps for the publish node (injected Supabase client)."""

    client: SupabaseClient
    research_state_store: Any | None = None
    """Optional WP12 store for dual-write of compiled prose views (#2877)."""


# ``documents.category`` must satisfy the ``chk_documents_category`` CHECK
# constraint (migration 002/011/053): one of synthesis, macro, asset-class,
# equity, sector, alt-data, institutional, portfolio, delta, output, rollup,
# deep-dive, learning.
# Map each segment slug to its phase's category; unmapped slugs fall back to the
# catch-all "output". (Passing the old default "research" violated the
# constraint and failed every publish — issue #628.)
_ASSET_CLASS_SLUGS = frozenset({"bonds", "commodities", "forex", "crypto", "international"})


def _segment_category(slug: str) -> str:
    """Return a constraint-valid ``documents.category`` for a segment slug."""
    if slug.startswith("alt-"):
        return "alt-data"
    if slug.startswith("inst-"):
        return "institutional"
    if slug == "macro":
        return "macro"
    if slug in _ASSET_CLASS_SLUGS:
        return "asset-class"
    if slug == "equity":
        return "equity"
    if slug.startswith("sector-"):
        return "sector"
    return "output"


def render_digest_markdown(snapshot: Phase7DigestPayload | dict[str, Any]) -> str:
    """Render a human-readable markdown string from the digest/snapshot payload.

    Prefer the stitched ``body``. Historical JSON slots fall back to
    :func:`compose_legacy_digest_body` (no Overall bias / fake metrics).
    """
    data: dict[str, Any] = dict(snapshot) if isinstance(snapshot, Mapping) else dict(snapshot)
    body = str(data.get("body") or "").strip()
    if body:
        continuity = data.get("continuity")
        if continuity and str(continuity) not in body:
            return f"{body.rstrip()}\n\n*Note: {continuity}*\n"
        return body if body.endswith("\n") else f"{body}\n"
    return compose_legacy_digest_body(data)


def _is_degenerate(body: Any) -> bool:
    """A content-free segment is suppressed rather than published empty.

    New memos: empty ``body`` and no leftover findings/headline.
    Legacy: ``data_quality == "absent"`` and no material findings (Pillar 1E).
    """
    if not isinstance(body, dict):
        return False
    md = str(body.get("body") or "").strip()
    if md:
        return False
    findings = body.get("material_findings") or []
    headline = str(body.get("headline") or "").strip()
    if body.get("data_quality") == "absent" and not findings:
        return True
    return not findings and not headline


def _log_suppressed(slug: str, body: dict[str, Any]) -> None:
    """Emit a per-segment line when a degenerate segment is dropped (observability)."""
    logger.info(
        "publish: suppressing degenerate segment %s (data_quality=%r, %d findings)",
        slug,
        body.get("data_quality"),
        len(body.get("material_findings") or []),
    )


def _publish_segment_bag(
    *,
    client: SupabaseClient,
    bag: dict[str, SegmentSlot],
    run_type: str,
    date_str: str,
    workspace_id: str | None = None,
) -> list[PublishedArtifact]:
    """Publish all fresh ('today') slots in a phase output dict (skipping degenerate ones)."""
    published: list[PublishedArtifact] = []
    for slug, slot in bag.items():
        if slot.payload.source != "today":
            continue
        if _is_degenerate(slot.payload.body):
            _log_suppressed(slug, slot.payload.body)
            continue
        artifact = publish_document(
            client=client,
            document_key=slug,
            payload=dict(slot.payload.body),
            doc_type=None,
            run_type=run_type,
            title=f"{slug} {date_str}",
            date_str=date_str,
            category=_segment_category(slug),
            segment=slug,
            workspace_id=workspace_id,
        )
        published.append(artifact)
    return published


def _publish_document_deltas(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    run_type: str,
    date_str: str,
) -> list[PublishedArtifact]:
    """Publish ``document_delta`` audit rows for edit-mode artifacts (§5.4)."""
    published: list[PublishedArtifact] = []
    for target_key, patch in (state.document_deltas or {}).items():
        if not isinstance(patch, dict) or not patch:
            continue
        published.append(
            publish_document_delta(
                client=client,
                date_str=date_str,
                target_document_key=target_key,
                patch=patch,
                run_type=run_type,
                workspace_id=getattr(state.config, "workspace_id", None),
            )
        )
    return published


def _carry_incomplete_snapshot(
    state: AtlasResearchState,
) -> Phase7DigestPayload | None:
    """Build a carried-incomplete snapshot from the most recent prior snapshot.

    Returns ``None`` when no prior snapshot exists (first-ever run / fresh
    tenant). The returned dict is the prior snapshot's content plus a
    ``continuity`` marker so downstream consumers know this is not a fresh
    synthesis.
    """
    if not state.prior_context.last_snapshots:
        return None
    prior_row = state.prior_context.last_snapshots[0]
    prior_snap = prior_row.get("snapshot") if isinstance(prior_row, dict) else None
    if not isinstance(prior_snap, dict):
        return None
    carried: dict[str, Any] = dict(prior_snap)
    carried["continuity"] = "carried_incomplete"
    carried["date"] = state.run_date.isoformat()
    # Machine-readable provenance (#1559): the source date this content was carried
    # from, uniform with the synthesis-carry path (_carry_prior_digest). JSONB column,
    # no migration. ``prior_row`` carries the source snapshot's own date.
    prior_date = prior_row.get("date") if isinstance(prior_row, dict) else None
    if prior_date:
        carried["carried_from"] = str(prior_date)
    return carried  # type: ignore[return-value]


def _append_house_daily_snapshot(
    artifacts: list[PublishedArtifact],
    *,
    deps: PublishDeps,
    workspace_id: str | None,
    date_str: str,
    snapshot: Phase7DigestPayload | dict[str, Any],
    run_type: str,
    baseline_date: str | None,
    digest_markdown: str,
) -> bool:
    """Write ``daily_snapshots`` for the house path only.

    Overlay private books live in ``documents`` (workspace-scoped). This table
    is unique on ``date`` with no ``workspace_id`` — an overlay upsert would
    last-writer-wins over the house Brief.
    """
    if is_private_workspace(workspace_id):
        logger.info("publish: overlay workspace skips daily_snapshots (house-only table)")
        return False
    artifacts.append(
        publish_daily_snapshot(
            client=deps.client,
            date_str=date_str,
            snapshot=snapshot,
            run_type=run_type,
            baseline_date=baseline_date,
            digest_markdown=digest_markdown,
            workspace_id=workspace_id,
        )
    )
    return True


def _maybe_publish_compiled_research_views(
    *,
    deps: PublishDeps,
    state: AtlasResearchState,
    run_type: str,
    date_str: str,
) -> list[PublishedArtifact]:
    """Dual-write WP12.5 compiled prose views when structured persistence is safe.

    Retains incumbent digest/segment writers. Skips (fail-closed) when the
    research-state pin is unavailable, the store is unwired, exact load fails,
    or ``publish_compiled_views`` refuses a failed structured write.
    """
    if state.research_state_status != "pinned" or not state.research_state_pin:
        return []
    store = deps.research_state_store
    if store is None:
        return []

    from digiquant.olympus.research_retrieval.models import ResearchStatePin
    from digiquant.olympus.research_retrieval.store import ResearchStateStore
    from digiquant.olympus.research_retrieval.views import (
        compile_views_from_store,
        document_key_for_view,
        publish_compiled_views,
    )

    if not isinstance(store, ResearchStateStore):
        logger.warning(
            "publish: research_state_store must be ResearchStateStore; got %s",
            type(store).__name__,
        )
        return []

    try:
        pin = ResearchStatePin.model_validate(state.research_state_pin)
        brief, digest = compile_views_from_store(store, pin.state_version_id, strict=True)
    except Exception:
        logger.exception(
            "publish: refusing compiled research views for %s (exact state unavailable)",
            date_str,
        )
        return []

    published: list[PublishedArtifact] = []

    def _publisher(view: Any) -> None:
        key = document_key_for_view(view.kind)
        published.append(
            publish_document(
                client=deps.client,
                document_key=key,
                payload={
                    "kind": view.kind.value,
                    "state_version_id": str(view.state_version_id),
                    "state_content_hash": view.state_content_hash,
                    "state_schema_version": view.state_schema_version,
                    "manifest_content_hash": view.manifest_content_hash,
                    "view_schema_version": view.view_schema_version,
                    "content_hash": view.content_hash,
                    "markdown": view.markdown,
                },
                doc_type=None,
                run_type=run_type,
                title=f"research-state {view.kind.value} {date_str}",
                date_str=date_str,
                category="output",
                segment=key,
                workspace_id=getattr(state.config, "workspace_id", None),
            )
        )

    try:
        # Structured path is safe only when exact pin load succeeded above.
        publish_compiled_views(
            views=(brief, digest),
            structured_write_ok=True,
            publisher=_publisher,
        )
    except Exception:
        logger.exception(
            "publish: compiled research-view dual-write failed for %s; "
            "incumbent documents retained",
            date_str,
        )
        return []
    return published


def build_publish_node(deps: PublishDeps) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return the publish node bound to ``deps``."""

    def publish(state: AtlasResearchState) -> dict[str, Any]:
        date_str = state.run_date.isoformat()
        run_type = state.run_type
        workspace_id = getattr(state.config, "workspace_id", None)
        artifacts: list[PublishedArtifact] = []

        # Track C glass-box (#2622): shadow AttentionPlan for Pipeline Inputs.
        # Fail-soft — a planner/publish miss must not block segment/digest writes.
        try:
            attention = maybe_publish_attention_plan_shadow(client=deps.client, state=state)
        except Exception:
            logger.exception(
                "publish: attention-plan shadow failed for %s; continuing",
                date_str,
            )
            attention = None
        if attention is not None:
            artifacts.append(attention)

        # WP-B: inspectable Inputs + bias-row. Fail-soft — a miss must not
        # block segment/digest writes (same policy as attention-plan).
        attention_key = ATTENTION_PLAN_DOCUMENT_KEY if attention is not None else None
        try:
            artifacts.append(
                publish_inputs_document(
                    client=deps.client,
                    state=state,
                    attention_plan_key=attention_key,
                )
            )
        except Exception:
            logger.exception(
                "publish: inputs document failed for %s; continuing",
                date_str,
            )
        try:
            bias_row = publish_bias_row_document(client=deps.client, state=state)
        except Exception:
            logger.exception(
                "publish: bias-row document failed for %s; continuing",
                date_str,
            )
            bias_row = None
        if bias_row is not None:
            artifacts.append(bias_row)

        for bag in (
            state.phase1_outputs,
            state.phase2_outputs,
            state.phase4_outputs,
            state.phase5_outputs,
        ):
            artifacts.extend(
                _publish_segment_bag(
                    client=deps.client,
                    bag=bag,
                    run_type=run_type,
                    date_str=date_str,
                    workspace_id=workspace_id,
                )
            )

        macro_slot = state.phase3_output
        if macro_slot is not None and macro_slot.payload.source == "today":
            if _is_degenerate(macro_slot.payload.body):
                _log_suppressed("macro", macro_slot.payload.body)
            else:
                artifacts.append(
                    publish_document(
                        client=deps.client,
                        document_key="macro",
                        payload=dict(macro_slot.payload.body),
                        doc_type=None,
                        run_type=run_type,
                        title=f"macro {date_str}",
                        date_str=date_str,
                        category="macro",
                        segment="macro",
                        workspace_id=workspace_id,
                    )
                )

        if state.phase7_digest is not None:
            # Custom research routing (#313). A one-off user prompt routes
            # to ``Custom Research`` under ``custom-research/<run_id>`` and
            # skips ``daily_snapshots`` (that table holds only the canonical
            # baseline / delta cadence).
            if state.custom_prompt:
                digest_key = f"custom-research/{state.run_id}"
                digest_doc_type: str | None = "Custom Research"
                title = f"Atlas Custom Research {date_str}"
                digest_category = "output"
            elif run_type == "delta":
                digest_key = "digest-delta"
                digest_doc_type = "Daily Delta"
                title = f"Atlas Daily Delta {date_str}"
                digest_category = "delta"
            else:
                # ``monthly`` never reaches publish (deps=None for monthly);
                # baseline is the only remaining ``run_type`` that lands here.
                digest_key = "digest"
                digest_doc_type = "Daily Digest"
                title = f"Atlas Daily Digest {date_str}"
                digest_category = "synthesis"

            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key=digest_key,
                    payload=dict(state.phase7_digest),
                    doc_type=digest_doc_type,
                    run_type=run_type,
                    title=title,
                    date_str=date_str,
                    category=digest_category,
                    workspace_id=workspace_id,
                )
            )
            if not state.custom_prompt:
                _append_house_daily_snapshot(
                    artifacts,
                    deps=deps,
                    workspace_id=workspace_id,
                    date_str=date_str,
                    snapshot=dict(state.phase7_digest),
                    run_type=run_type,
                    baseline_date=state.baseline_date.isoformat() if state.baseline_date else None,
                    digest_markdown=render_digest_markdown(state.phase7_digest),
                )
        elif not state.custom_prompt:
            # Continuity (#952): no fresh digest (partial/failed run) — carry
            # the most recent prior snapshot forward so ``load_prior_context``
            # always sees a row for the run date.
            carried = _carry_incomplete_snapshot(state)
            if carried is not None:
                wrote = _append_house_daily_snapshot(
                    artifacts,
                    deps=deps,
                    workspace_id=workspace_id,
                    date_str=date_str,
                    snapshot=carried,
                    run_type=run_type,
                    baseline_date=state.baseline_date.isoformat() if state.baseline_date else None,
                    digest_markdown=render_digest_markdown(carried),
                )
                if wrote:
                    logger.warning(
                        "publish: no fresh digest for %s; wrote carried-incomplete "
                        "snapshot from prior context",
                        date_str,
                    )

        # WP12.5: dual-write compiled views from exact pinned state (incumbent retained).
        artifacts.extend(
            _maybe_publish_compiled_research_views(
                deps=deps,
                state=state,
                run_type=run_type,
                date_str=date_str,
            )
        )

        return {
            "published": artifacts
            + _publish_document_deltas(
                client=deps.client,
                state=state,
                run_type=run_type,
                date_str=date_str,
            )
        }

    return publish


def build_publish_phase(deps: PublishDeps) -> PipelinePhase:
    """Wrap the publish node into a single-node ``PipelinePhase``."""
    return PipelinePhase(
        name="publish",
        nodes=[NodeSpec(name="publish-supabase", run=build_publish_node(deps))],
    )


__all__ = [
    "PublishDeps",
    "build_publish_node",
    "build_publish_phase",
    "render_digest_markdown",
]
