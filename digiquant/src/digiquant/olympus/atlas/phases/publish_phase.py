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
                    category="deep-dive",
                    segment="analyst",
                    sector=ticker,
                )
            )

        # Per-ticker bull/bear debate summaries (#698). Produced by the Phase
        # 7C-D research manager but previously discarded in state — publish so
        # the dashboard can show *why* a ticker's conviction moved. Skip any
        # half-built scratch entry (a finished summary always has net_stance).
        for ticker, debate in state.phase7cd_debates.items():
            if not isinstance(debate, dict) or "net_stance" not in debate:
                continue
            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key=f"deliberation/{ticker}",
                    payload=dict(debate),
                    doc_type=None,
                    run_type=run_type,
                    title=f"{ticker} debate {date_str}",
                    date_str=date_str,
                    category="deep-dive",
                    segment="deliberation",
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
                    category="portfolio",
                )
            )

        # Aggressive-vs-conservative risk-temperament debate (#698) — the
        # portfolio-level deliberation framing the PM decision. One per run.
        # ``phase7d_risk_debate`` is TypedDict(total=False): the aggressive node
        # writes a partial dict (conservative_case / key_tension empty) that the
        # conservative node later completes. Publish only when all three sides
        # are filled, matching the frontend sniffer's contract.
        risk_debate = state.phase7d_risk_debate or {}
        if all(
            str(risk_debate.get(k, "")).strip()
            for k in ("aggressive_case", "conservative_case", "key_tension")
        ):
            artifacts.append(
                publish_document(
                    client=deps.client,
                    document_key="risk-debate",
                    payload=dict(risk_debate),
                    doc_type=None,
                    run_type=run_type,
                    title=f"Risk Debate {date_str}",
                    date_str=date_str,
                    category="portfolio",
                    segment="deliberation",
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
