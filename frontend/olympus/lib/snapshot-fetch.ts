/**
 * Live read of the latest Atlas daily snapshot from Supabase.
 *
 * Reads the freshest `daily_snapshots` row, validates the `snapshot` jsonb
 * payload conforms to the {@link DigestPayload} shape, and assembles a typed
 * {@link SnapshotEnvelope} that mirrors the Pydantic model exported by the
 * Atlas pipeline (see `digiquant/src/digiquant/atlas/snapshot.py`).
 *
 * Empty-state rule: returns `{ kind: 'empty' }` when the freshest row is older
 * than yesterday (today's UTC date or yesterday's UTC date). A 5-day-old row
 * is **not** treated as "present but stale" — that combination would surface
 * stale-banner ambiguity. Only rows from {today, yesterday} are surfaced.
 *
 * Anonymous read works under migration 011's `anon_read` SELECT RLS policy
 * (`digiquant/supabase/migrations/011_anon_read_daily_snapshots.sql`).
 *
 * Optional BFF (`NEXT_PUBLIC_OLYMPUS_USE_BFF=1`): inject `bffFetch` in tests or
 * host Olympus on a Node runtime with your own `/api/snapshots` handler. Static
 * export (`output: 'export'` on digiquant.io) cannot ship App Router API routes.
 */
import type { SupabaseClient } from '@supabase/supabase-js';
import { isSupabaseConfigured, supabase } from './supabase';
import type { Database } from './database.types';
import type {
  DigestPayload,
  SnapshotEnvelope,
  SnapshotFetchResult,
} from './snapshot-types';

type SB = SupabaseClient<Database>;

/** Browser opt-in: fetch `/api/snapshots` instead of anon Supabase (REM-081 / REM-036). */
export function isBffSnapshotEnabled(): boolean {
  return process.env.NEXT_PUBLIC_OLYMPUS_USE_BFF === '1';
}

/** Narrow `daily_snapshots` row pick — only what we need to assemble the envelope. */
type SnapshotRowPick = {
  date: string;
  run_type: string | null;
  baseline_date: string | null;
  snapshot: unknown;
  created_at: string | null;
};

/** Format a UTC date as `YYYY-MM-DD`. Stable independent of host TZ. */
function isoUtcDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Returns `[todayUtc, yesterdayUtc]` as ISO date strings. */
function todayAndYesterday(now: Date = new Date()): [string, string] {
  const today = isoUtcDate(now);
  const y = new Date(now);
  y.setUTCDate(y.getUTCDate() - 1);
  return [today, isoUtcDate(y)];
}

function isObjectRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === 'object' && !Array.isArray(v);
}

/** Validate the jsonb payload looks like {@link DigestPayload}. Defensive — does not deep-validate. */
function asDigestPayload(raw: unknown): DigestPayload | null {
  if (!isObjectRecord(raw)) return null;
  const requiredStringKeys: Array<keyof DigestPayload> = [
    'segment',
    'date',
    'bias',
    'headline',
    'market_regime_snapshot',
    'alt_data_dashboard',
    'institutional_summary',
    'asset_classes_summary',
    'us_equities_summary',
  ];
  for (const k of requiredStringKeys) {
    if (typeof raw[k as string] !== 'string') return null;
  }

  // Provide defaults for optional list / map fields so the renderer can rely
  // on iterating without null-checks. The pipeline always emits these, but
  // historical / hand-edited rows may not.
  const safe: DigestPayload = {
    segment: raw.segment as string,
    date: raw.date as string,
    bias: raw.bias as DigestPayload['bias'],
    headline: raw.headline as string,
    material_findings: Array.isArray(raw.material_findings)
      ? (raw.material_findings as DigestPayload['material_findings'])
      : [],
    sources: Array.isArray(raw.sources) ? (raw.sources as DigestPayload['sources']) : [],
    notes: typeof raw.notes === 'string' ? raw.notes : '',
    market_regime_snapshot: raw.market_regime_snapshot as string,
    alt_data_dashboard: raw.alt_data_dashboard as string,
    institutional_summary: raw.institutional_summary as string,
    asset_classes_summary: raw.asset_classes_summary as string,
    us_equities_summary: raw.us_equities_summary as string,
    thesis_tracker: typeof raw.thesis_tracker === 'string' ? raw.thesis_tracker : '',
    portfolio_recommendations:
      typeof raw.portfolio_recommendations === 'string' ? raw.portfolio_recommendations : '',
    actionable_summary: Array.isArray(raw.actionable_summary)
      ? (raw.actionable_summary as DigestPayload['actionable_summary'])
      : [],
    risk_radar: Array.isArray(raw.risk_radar) ? (raw.risk_radar as DigestPayload['risk_radar']) : [],
    segment_freshness: isObjectRecord(raw.segment_freshness)
      ? (raw.segment_freshness as DigestPayload['segment_freshness'])
      : {},
  };
  return safe;
}

/**
 * Build a {@link SnapshotEnvelope} from a raw `daily_snapshots` row pick.
 *
 * Mirrors `SnapshotEnvelope.from_supabase_row` in the Pydantic source. The
 * `published_at` timestamp resolves from `created_at` (the only timestamp
 * column the table currently exposes) → "now" as a last resort.
 */
export function envelopeFromRow(
  row: SnapshotRowPick,
  now: Date = new Date(),
): SnapshotEnvelope | null {
  const digest = asDigestPayload(row.snapshot);
  if (!digest) return null;
  const runType = row.run_type === 'baseline' || row.run_type === 'delta' ? row.run_type : null;
  if (!runType) return null;
  return {
    schema_version: 1,
    run_date: row.date,
    run_type: runType,
    baseline_date: row.baseline_date ?? null,
    published_at: row.created_at ?? now.toISOString(),
    digest,
  };
}

interface FetchOpts {
  /** Override "now" for tests. */
  now?: Date;
  /**
   * Inject a Supabase client for tests. Defaults to the module-level
   * singleton from `lib/supabase.ts`. When the caller passes an explicit
   * client (even if `null`), the env-var configuration check is skipped —
   * the explicit value is treated as the source of truth.
   */
  client?: SB | null;
  /** Override BFF fetch for tests (defaults to global `fetch`). */
  bffFetch?: typeof fetch;
}

function resultFromRow(
  row: SnapshotRowPick | null | undefined,
  now: Date,
): SnapshotFetchResult {
  if (!row) return { kind: 'empty', reason: 'no_recent_row' };

  const [today, yesterday] = todayAndYesterday(now);
  if (row.date !== today && row.date !== yesterday) {
    return { kind: 'empty', reason: 'no_recent_row' };
  }

  const envelope = envelopeFromRow(row, now);
  if (!envelope) {
    return {
      kind: 'error',
      message: `Latest daily_snapshots row for ${row.date} has an invalid 'snapshot' payload.`,
    };
  }
  return { kind: 'present', envelope };
}

async function fetchLatestSnapshotViaBff(
  opts: FetchOpts,
  now: Date,
): Promise<SnapshotFetchResult> {
  const doFetch = opts.bffFetch ?? fetch;
  try {
    const res = await doFetch('/api/snapshots');
    if (res.status === 404) {
      return { kind: 'empty', reason: 'unconfigured' };
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      return {
        kind: 'error',
        message: body.message ?? `BFF snapshot fetch failed (HTTP ${res.status})`,
      };
    }
    const body = (await res.json()) as { snapshot?: SnapshotRowPick | null };
    return resultFromRow(body.snapshot ?? null, now);
  } catch (err) {
    return { kind: 'error', message: err instanceof Error ? err.message : String(err) };
  }
}

/**
 * Fetch the latest snapshot row, returning a discriminated result.
 *
 * - `present`: row exists for today or yesterday and the payload validates.
 * - `empty.no_recent_row`: no row, or the latest row is older than yesterday.
 * - `empty.unconfigured`: Supabase URL / anon key not set in env.
 * - `error`: Supabase returned an error or the payload failed validation.
 */
export async function fetchLatestSnapshot(
  opts: FetchOpts = {},
): Promise<SnapshotFetchResult> {
  const now = opts.now ?? new Date();
  const explicitClient = 'client' in opts;

  if (!explicitClient && isBffSnapshotEnabled()) {
    return fetchLatestSnapshotViaBff(opts, now);
  }

  // When the caller injected a client (even `null`), trust it. Otherwise
  // fall back to the module singleton, which itself is `null` when the
  // public env vars are missing.
  const client = explicitClient ? opts.client ?? null : supabase;
  if (!client) {
    // No production client and no env-configured singleton → ask the user
    // to set the public env vars. (Tests inject `null` directly to exercise
    // this branch.)
    if (!explicitClient && isSupabaseConfigured()) {
      // Defensive — should never happen since the singleton is null when
      // unconfigured, but keep an explicit error rather than silent miss.
      return { kind: 'error', message: 'Supabase singleton missing despite configured env.' };
    }
    return { kind: 'empty', reason: 'unconfigured' };
  }
  try {
    const { data, error } = await client
      .from('daily_snapshots')
      .select('date, run_type, baseline_date, snapshot, created_at')
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error) {
      return { kind: 'error', message: error.message ?? String(error) };
    }
    return resultFromRow(data as SnapshotRowPick | null, now);
  } catch (err) {
    return { kind: 'error', message: err instanceof Error ? err.message : String(err) };
  }
}
