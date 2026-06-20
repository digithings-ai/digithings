"""Publish phase — upsert fresh segments, digest, and optional 7C/7D to Supabase.

Skips carried slots. Monthly runs omit this phase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState, PublishedArtifact, SegmentSlot
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    publish_daily_snapshot,
    publish_document,
    publish_document_delta,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishDeps:
    """Wiring deps for the publish node (injected Supabase client)."""

    client: SupabaseClient


# ``documents.category`` must satisfy the ``chk_documents_category`` CHECK
# constraint (migration 002/011): one of synthesis, macro, asset-class, equity,
# sector, alt-data, institutional, portfolio, delta, output, rollup, deep-dive.
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


def _is_degenerate(body: Any) -> bool:
    """A content-free segment: the analyst graded the evidence ``data_quality == "absent"``
    AND produced no material findings (Pillar 1E). Publishing it would surface a
    confident-looking empty document, so it is suppressed. A segment with findings — or one
    graded high/medium/low (or ungraded ``None``) — always publishes."""
    if not isinstance(body, dict):
        return False
    return body.get("data_quality") == "absent" and not (body.get("material_findings") or [])


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
            )
        )
    return published


def build_publish_node(deps: PublishDeps) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return the publish node bound to ``deps``."""

    def publish(state: AtlasResearchState) -> dict[str, Any]:
        date_str = state.run_date.isoformat()
        run_type = state.run_type
        artifacts: list[PublishedArtifact] = []

        for bag in (
            state.phase1_outputs,
            state.phase2_outputs,
            state.phase4_outputs,
            state.phase5_outputs,
        ):
            artifacts.extend(
                _publish_segment_bag(
                    client=deps.client, bag=bag, run_type=run_type, date_str=date_str
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
                )
            )
            if not state.custom_prompt:
                baseline_iso = state.baseline_date.isoformat() if state.baseline_date else None
                artifacts.append(
                    publish_daily_snapshot(
                        client=deps.client,
                        date_str=date_str,
                        snapshot=dict(state.phase7_digest),
                        run_type=run_type,
                        baseline_date=baseline_iso,
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
]
