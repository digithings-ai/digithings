/**
 * Hand-written TypeScript mirror of `SnapshotEnvelope` in
 * `digiquant/src/digiquant/atlas/snapshot.py` (schema v1).
 *
 * Source of truth: `digiquant/docs/schemas/atlas_snapshot.v1.json`. When the
 * Pydantic model bumps `SCHEMA_VERSION`, regenerate the JSON schema and
 * update this file in lockstep — the Atlas pipeline writes the envelope
 * shape into `daily_snapshots.snapshot` and the frontend reads it back.
 *
 * Why hand-written vs json-schema-to-typescript? The field set is small
 * (six top-level keys, eleven nested narrative slots) and adding a code
 * generator just for this one schema introduces a build-time dependency we
 * would otherwise not need.
 */
export const SNAPSHOT_SCHEMA_VERSION = 1 as const;

/** Bias vocabulary mirrored from `digiquant_atlas.segments.Bias`. */
export type SnapshotBias =
  | 'strong_bullish'
  | 'bullish'
  | 'neutral'
  | 'bearish'
  | 'strong_bearish'
  | 'mixed';

/** Per-segment provenance marker. Mirrors phase7_synthesis.SegmentFreshness. */
export interface SegmentFreshness {
  source: 'today' | 'baseline';
  /** ISO date string ('' if unknown). */
  as_of: string;
}

/** One actionable summary entry. Mirrors phase7_synthesis.ActionableItem. */
export interface ActionableItem {
  /** 1 (highest) … 5 (lowest). */
  priority: number;
  label: string;
  rationale: string;
}

/** One risk-radar entry. Mirrors phase7_synthesis.RiskItem. */
export interface RiskItem {
  /** 1 … 168 hours. */
  horizon_hours: number;
  label: string;
  trigger: string;
}

/** One material finding. Mirrors digiquant_atlas.segments.Finding. */
export interface SnapshotFinding {
  label: string;
  summary: string;
  source_ids?: string[];
}

/** One cited source. Mirrors digiquant_atlas.segments.Source. */
export interface SnapshotSource {
  id: string;
  title?: string | null;
  url?: string | null;
}

/**
 * Frontend-facing copy of the Phase 7 master synthesis payload.
 * Mirrors `digiquant.atlas.snapshot.DigestPayload`.
 */
export interface DigestPayload {
  /* SegmentReport core */
  segment: string;
  /** ISO date `YYYY-MM-DD`. */
  date: string;
  bias: SnapshotBias;
  headline: string;
  material_findings: SnapshotFinding[];
  sources: SnapshotSource[];
  notes: string;

  /* Digest-specific narrative sections */
  market_regime_snapshot: string;
  alt_data_dashboard: string;
  institutional_summary: string;
  asset_classes_summary: string;
  us_equities_summary: string;
  thesis_tracker: string;
  portfolio_recommendations: string;
  actionable_summary: ActionableItem[];
  risk_radar: RiskItem[];
  segment_freshness: Record<string, SegmentFreshness>;
}

/**
 * Frontend-consumable wrapper around a `daily_snapshots` row.
 * Mirrors `digiquant.atlas.snapshot.SnapshotEnvelope`.
 */
export interface SnapshotEnvelope {
  schema_version: number;
  /** ISO date `YYYY-MM-DD`. */
  run_date: string;
  run_type: 'baseline' | 'delta';
  /** ISO date `YYYY-MM-DD` — the most recent baseline a delta builds on; `null` on a baseline run. */
  baseline_date: string | null;
  /** ISO 8601 UTC timestamp the envelope was assembled. */
  published_at: string;
  digest: DigestPayload;
}

/** Outcome of `fetchLatestSnapshot()`. Discriminated union to make rendering states explicit. */
export type SnapshotFetchResult =
  | { kind: 'present'; envelope: SnapshotEnvelope }
  | { kind: 'empty'; reason: 'no_recent_row' | 'unconfigured' }
  | { kind: 'error'; message: string };
