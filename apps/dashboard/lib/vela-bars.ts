import type { VelaSpikeBar } from '@/components/research/VelaSpikeChart';

/**
 * digiquant `GET /bars` reader for the dashboard Vela chart (#4879).
 *
 * Keyless, read-only, display-only: bars come from the anonymous Gloomberb
 * price-history path (no keys, no session cookie) and must never feed the
 * validate → backtest → optimize → export pipeline. Free-tier data may be
 * delayed — the endpoint's `delay_note` is surfaced so the page can say so.
 *
 * Route interface (`app/research/vela-spike/page.tsx`):
 * `?symbol=<listing>` (default `BTC-USD`) and `?timeframe=<tf>` (default
 * `1d`, one of `1m | 5m | 15m | 30m | 1h | 1d | 1wk | 1mo`). Unknown
 * timeframes fall back to the default rather than 422ing the page.
 */

/** Dashboard `timeframe` vocabulary — exactly `GET /bars`' resolutions. */
export const VELA_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '1d', '1wk', '1mo'] as const;

export type VelaTimeframe = (typeof VELA_TIMEFRAMES)[number];

/** Crypto default so the out-of-box chart shows a live-smoked symbol. */
export const VELA_DEFAULT_SYMBOL = 'BTC-USD';

export const VELA_DEFAULT_TIMEFRAME: VelaTimeframe = '1d';

/**
 * digiquant base URL for client-side reads. Override with
 * `NEXT_PUBLIC_DIGIQUANT_BASE_URL` wherever the dashboard is served from a
 * host where digiquant is not on localhost (same `NEXT_PUBLIC_*` precedent
 * as the Supabase readers).
 */
export function velaDigiquantBaseUrl(): string {
  return process.env.NEXT_PUBLIC_DIGIQUANT_BASE_URL?.trim() || 'http://127.0.0.1:8001';
}

/** Blank input falls back to the default symbol; the endpoint normalizes case. */
export function normalizeVelaSymbol(raw: string | null | undefined): string {
  const cleaned = (raw ?? '').trim();
  return cleaned === '' ? VELA_DEFAULT_SYMBOL : cleaned;
}

/** Case-insensitive match against the endpoint vocabulary; fallback is `1d`. */
export function normalizeVelaTimeframe(raw: string | null | undefined): VelaTimeframe {
  const cleaned = (raw ?? '').trim().toLowerCase();
  return (VELA_TIMEFRAMES as readonly string[]).includes(cleaned)
    ? (cleaned as VelaTimeframe)
    : VELA_DEFAULT_TIMEFRAME;
}

export interface VelaBarsResult {
  bars: VelaSpikeBar[];
  /** Echoed upstream listing symbol (may differ in case/format from requested). */
  symbol: string;
  timeframe: string;
  source: string;
  stale: boolean;
  delayNote: string | null;
}

/** Typed `GET /bars` failure — the page renders `message`, never a traceback. */
export class VelaBarsError extends Error {
  readonly status: number | null;

  constructor(status: number | null, message: string) {
    super(message);
    this.name = 'VelaBarsError';
    this.status = status;
  }
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Map one `BarsBar` (`{timestamp: ISO string, open/high/low/close, volume?}`)
 * onto the `VelaSpikeBar` shape (`t` = epoch ms). Returns `null` for bars
 * Vela cannot draw: unparseable timestamps or non-finite o/h/l/c (the
 * endpoint types o/h/l/volume as nullable).
 */
export function toVelaSpikeBar(raw: unknown): VelaSpikeBar | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const bar = raw as Record<string, unknown>;
  const t = typeof bar.timestamp === 'string' ? Date.parse(bar.timestamp) : NaN;
  const { open, high, low, close, volume } = bar;
  if (!Number.isFinite(t)) return null;
  if (!isFiniteNumber(open) || !isFiniteNumber(high) || !isFiniteNumber(low)) return null;
  if (!isFiniteNumber(close)) return null;
  return {
    t,
    o: open,
    h: high,
    l: low,
    c: close,
    ...(isFiniteNumber(volume) ? { v: volume } : {}),
  };
}

/** Map a `BarsResponse` payload onto drawable bars, dropping incomplete rows. */
export function barsResponseToVelaBars(payload: unknown): VelaSpikeBar[] {
  if (typeof payload !== 'object' || payload === null) return [];
  const bars = (payload as { bars?: unknown }).bars;
  if (!Array.isArray(bars)) return [];
  const out: VelaSpikeBar[] = [];
  for (const raw of bars) {
    const mapped = toVelaSpikeBar(raw);
    if (mapped !== null) out.push(mapped);
  }
  return out;
}

/**
 * Fetch drawable bars from keyless `GET /bars`. Throws `VelaBarsError` on
 * HTTP errors (with status) and on transport failures (status `null`,
 * upstream detail preserved for the page's error state).
 */
export async function fetchVelaBars(
  symbol: string,
  timeframe: string,
  opts?: { baseUrl?: string; limit?: number; signal?: AbortSignal }
): Promise<VelaBarsResult> {
  const base = (opts?.baseUrl ?? velaDigiquantBaseUrl()).replace(/\/+$/, '');
  const params = new URLSearchParams({ symbol, timeframe });
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit));
  let res: Response;
  try {
    res = await fetch(`${base}/bars?${params.toString()}`, { signal: opts?.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new VelaBarsError(null, err instanceof Error ? err.message : String(err));
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = (await res.json()) as { detail?: unknown; error?: unknown };
      if (typeof body?.detail === 'string') {
        detail = body.detail;
      } else if (
        typeof body?.error === 'object' &&
        body.error !== null &&
        typeof (body.error as { message?: unknown }).message === 'string'
      ) {
        // digiquant error envelope: {"error": {"code", "message", ...}}.
        detail = (body.error as { message: string }).message;
      }
    } catch {
      /* non-JSON error body — fall through to the status line */
    }
    throw new VelaBarsError(
      res.status,
      detail === '' ? `GET /bars answered HTTP ${res.status}` : detail
    );
  }
  const payload = (await res.json()) as Record<string, unknown>;
  return {
    bars: barsResponseToVelaBars(payload),
    symbol: typeof payload.symbol === 'string' ? payload.symbol : symbol,
    timeframe: typeof payload.timeframe === 'string' ? payload.timeframe : timeframe,
    source: typeof payload.source === 'string' ? payload.source : 'gloomberb',
    stale: payload.stale === true,
    delayNote: typeof payload.delay_note === 'string' ? payload.delay_note : null,
  };
}
