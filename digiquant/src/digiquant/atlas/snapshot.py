"""Atlas daily snapshot envelope — frontend-consumable schema.

This module defines :class:`SnapshotEnvelope`, the Pydantic v2 contract the
Atlas frontend (and any other consumer) uses to validate a row read from the
Supabase ``daily_snapshots`` table. The envelope wraps the digest payload
(produced by :class:`digiquant.atlas.phases.phase7_synthesis.DigestSnapshot`)
with run-level metadata (``schema_version``, ``run_date``, ``run_type``,
``baseline_date``, ``published_at``).

Why a duplicate model and not an import?
----------------------------------------
Importing the pipeline-side ``DigestSnapshot`` would force every consumer of
this contract to install the full pipeline runtime (LangGraph, orchestrator
skills, supabase, …) — unacceptable for a serverless BFF or lightweight
validation library that just wants to validate JSON.

Instead :class:`DigestPayload` mirrors the field set of
:class:`digiquant.atlas.phases.phase7_synthesis.DigestSnapshot` exactly. A
parity test (`tests/dq/atlas/test_snapshot.py::test_payload_matches_pipeline_digest`)
imports both when the pipeline extras are installed and asserts field-name
parity — drift fails loud rather than silently.

Read path (Option A — see PR #441 follow-up)
--------------------------------------------
1. The Atlas pipeline writes a row to ``daily_snapshots`` via
   ``digiquant.atlas.supabase_io.publish_daily_snapshot``.
2. The frontend (or any consumer) reads that row directly using the Supabase
   anon key under the ``anon_read`` RLS policy installed by migration 011.
3. The row JSON is loaded into :class:`SnapshotEnvelope` for validation, then
   rendered. ``SnapshotEnvelope.from_supabase_row`` accepts the natural
   column layout (``date``, ``run_type``, ``baseline_date``, ``snapshot``,
   ``created_at`` / ``updated_at``) and produces a typed envelope without
   the caller having to hand-build it.

Schema versioning
-----------------
``schema_version`` is at the top of the envelope so future migrations are
tractable: bump ``SCHEMA_VERSION`` here when the field set or semantics
change, regenerate ``digiquant/docs/schemas/atlas_snapshot.v1.json`` (and
add a ``.v2.json`` sibling for breaking changes), and ship a frontend
update in lockstep.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bump when fields are added/removed/renamed or semantics change.
# The on-disk schema export lives at ``digiquant/docs/schemas/atlas_snapshot.v{N}.json``.
SCHEMA_VERSION: int = 1


# ─── Per-segment freshness markers (mirrors phase7_synthesis.SegmentFreshness) ──


class SegmentFreshness(BaseModel):
    """Per-segment provenance marker used by the dashboard.

    Mirrors :class:`digiquant.atlas.phases.phase7_synthesis.SegmentFreshness`.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["today", "baseline"]
    as_of: str = Field(description="ISO date string ('' if unknown)")


class ActionableItem(BaseModel):
    """One actionable summary entry. Mirrors phase7_synthesis.ActionableItem."""

    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1, le=5)
    label: str = Field(max_length=120)
    rationale: str = Field(max_length=500)


class RiskItem(BaseModel):
    """One risk-radar entry. Mirrors phase7_synthesis.RiskItem."""

    model_config = ConfigDict(extra="forbid")

    horizon_hours: int = Field(ge=1, le=168)
    label: str = Field(max_length=120)
    trigger: str = Field(max_length=400)


# ─── Source citation primitives (mirrors digiquant.atlas.segments) ──────────


class Finding(BaseModel):
    """One material finding. Mirrors digiquant.atlas.segments.Finding."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=120)
    summary: str = Field(max_length=800)
    source_ids: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """One cited source. Mirrors digiquant.atlas.segments.Source."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(max_length=64)
    title: str | None = Field(default=None, max_length=600)
    url: str | None = Field(default=None, max_length=1000)


# Bias vocabulary — kept in sync with digiquant.atlas.segments.Bias.
Bias = Literal[
    "strong_bullish",
    "bullish",
    "neutral",
    "bearish",
    "strong_bearish",
    "mixed",
]


# ─── DigestPayload — local mirror of phase7_synthesis.DigestSnapshot ────────


class DigestPayload(BaseModel):
    """Frontend-facing copy of the Phase 7 master synthesis payload.

    **This duplicates** ``digiquant.atlas.phases.phase7_synthesis.DigestSnapshot``
    on purpose — see module docstring for the import-direction rationale. The
    parity test enforces drift detection.

    Layout: a :class:`SegmentReport`-shaped core (segment, date, bias,
    headline, findings, sources, notes) plus the digest-specific narrative
    sections defined in ARCHITECTURE.md §Phase 7.
    """

    model_config = ConfigDict(extra="forbid")

    # ── SegmentReport core ────────────────────────────────────────────────
    segment: str = Field(max_length=64)
    date: date
    bias: Bias
    headline: str = Field(max_length=280)
    material_findings: list[Finding] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)

    # ── Digest-specific narrative sections ────────────────────────────────
    market_regime_snapshot: str = Field(max_length=800)
    alt_data_dashboard: str = Field(max_length=800)
    institutional_summary: str = Field(max_length=800)
    asset_classes_summary: str = Field(max_length=1200)
    us_equities_summary: str = Field(max_length=1200)
    thesis_tracker: str = Field(default="", max_length=1200)
    portfolio_recommendations: str = Field(default="", max_length=1200)
    actionable_summary: list[ActionableItem] = Field(default_factory=list)
    risk_radar: list[RiskItem] = Field(default_factory=list)
    segment_freshness: dict[str, SegmentFreshness] = Field(default_factory=dict)


# ─── SnapshotEnvelope — the wire-level contract ─────────────────────────────


class SnapshotEnvelope(BaseModel):
    """Frontend-consumable wrapper around a ``daily_snapshots`` row.

    Layout (top-level keys ordered for human-readability when serialized):

    - ``schema_version`` — int; bump on breaking changes (see module docstring).
    - ``run_date`` — the trading date the digest was synthesized for.
    - ``run_type`` — ``"baseline"`` (Sunday weekly) or ``"delta"`` (weekday).
    - ``baseline_date`` — for delta runs, the most recent baseline this delta
      builds on; ``None`` on a baseline run.
    - ``published_at`` — UTC timestamp the envelope was assembled.
    - ``digest`` — the validated :class:`DigestPayload`.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=SCHEMA_VERSION, description="Envelope schema version")
    run_date: date
    run_type: Literal["baseline", "delta"]
    baseline_date: date | None = None
    published_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the envelope was assembled",
    )
    digest: DigestPayload

    @classmethod
    def from_supabase_row(cls, row: dict[str, Any]) -> "SnapshotEnvelope":
        """Build an envelope from a ``daily_snapshots`` row.

        ``published_at`` resolves from (in order): ``updated_at`` →
        ``created_at`` → ``default_factory`` (now in UTC) — so the envelope
        timestamp tracks the freshest write the DB knows about.
        """
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("daily_snapshots row missing 'snapshot' jsonb payload")

        kwargs: dict[str, Any] = {
            "run_date": row["date"],
            "run_type": row["run_type"],
            "baseline_date": row.get("baseline_date"),
            "digest": snapshot,
        }
        published_at = row.get("updated_at") or row.get("created_at")
        if published_at is not None:
            kwargs["published_at"] = published_at
        return cls(**kwargs)


__all__ = [
    "SCHEMA_VERSION",
    "ActionableItem",
    "Bias",
    "DigestPayload",
    "Finding",
    "RiskItem",
    "SegmentFreshness",
    "SnapshotEnvelope",
    "Source",
]
