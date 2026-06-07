"""Publish phase — upsert fresh segments, digest, and optional 7C/7D to Supabase.

Skips carried slots. Monthly runs omit this phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState, PublishedArtifact, SegmentSlot
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    publish_daily_snapshot,
    publish_document,
)


@dataclass(frozen=True)
class PublishDeps:
    """Wiring deps for the publish node (injected Supabase client)."""

    client: SupabaseClient


def _publish_segment_bag(
    *,
    client: SupabaseClient,
    bag: dict[str, SegmentSlot],
    run_type: str,
    date_str: str,
) -> list[PublishedArtifact]:
    """Publish all fresh ('today') slots in a phase output dict."""
    published: list[PublishedArtifact] = []
    for slug, slot in bag.items():
        if slot.payload.source != "today":
            continue
        artifact = publish_document(
            client=client,
            document_key=slug,
            payload=dict(slot.payload.body),
            doc_type=None,
            run_type=run_type,
            title=f"{slug} {date_str}",
            date_str=date_str,
            segment=slug,
        )
        published.append(artifact)
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

        if state.phase3_output is not None and state.phase3_output.payload.source == "today":
            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key="macro",
                    payload=dict(state.phase3_output.payload.body),
                    doc_type=None,
                    run_type=run_type,
                    title=f"macro {date_str}",
                    date_str=date_str,
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
            elif run_type == "delta":
                digest_key = "digest-delta"
                digest_doc_type = "Daily Delta"
                title = f"Atlas Daily Delta {date_str}"
            else:
                # ``monthly`` never reaches publish (deps=None for monthly);
                # baseline is the only remaining ``run_type`` that lands here.
                digest_key = "digest"
                digest_doc_type = "Daily Digest"
                title = f"Atlas Daily Digest {date_str}"

            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key=digest_key,
                    payload=dict(state.phase7_digest),
                    doc_type=digest_doc_type,
                    run_type=run_type,
                    title=title,
                    date_str=date_str,
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

        for ticker, payload in state.phase7c_analysts.items():
            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key=f"analyst/{ticker}",
                    payload=dict(payload),
                    doc_type=None,
                    run_type=run_type,
                    title=f"{ticker} analyst {date_str}",
                    date_str=date_str,
                    segment="analyst",
                    sector=ticker,
                )
            )

        if state.phase7d_rebalance is not None:
            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key="pm-rebalance",
                    payload=dict(state.phase7d_rebalance),
                    doc_type="Rebalance Decision",
                    run_type=run_type,
                    title=f"PM Rebalance {date_str}",
                    date_str=date_str,
                )
            )

        return {"published": artifacts}

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
