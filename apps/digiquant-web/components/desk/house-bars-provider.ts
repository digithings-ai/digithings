/**
 * House market-data provider for the Vela charts (DIG-2814; Refs #4879/#4880).
 *
 * Vela's default feed is a registry of vendor providers, and the desk was
 * registering the browser-side Binance and Coinbase ones: the `/tools/charts`
 * route then rendered `binance:BTCUSDT` and every load tried to reach
 * `api.binance.com` and `fapi.binance.com` straight from the browser, which the
 * render audit recorded as a CORS failure (surfaces-audit.md finding 4). Neither
 * is house data.
 *
 * This provider replaces both. It answers from digiquant's keyless
 * `GET /bars?symbol=&timeframe=&limit=` — auth-exempt by design
 * (`digikey/src/digikey/integrations/service_middleware.py:182`), no provider
 * key, no session cookie, no order path, display-only. That is what makes a
 * browser-side fetch legitimate here: the desk is a static export with no
 * server runtime, and the endpoint carries no credential to protect.
 *
 * Unconfigured is honest-empty: an unset base URL returns no bars rather than
 * falling back to a vendor feed (the same rule as `lib/live/market-data.ts`).
 */
import type { DataProvider, BarRange, OHLCV, ProviderInfo, SymbolDescriptor } from "@luxalgo/vela";

/** Prefix Vela's `MultiProviderFeed` must resolve; a bare symbol has no route to us. */
export const HOUSE_PROVIDER_NAME = "house";

/** Prefixes a house symbol: `house:BTC-USD`. Vela resolves the part after the colon. */
export function houseSymbol(symbol: string): string {
  return `${HOUSE_PROVIDER_NAME}:${symbol}`;
}

/**
 * Vela timeframes are chart-internal (`1` = one minute); digiquant takes the
 * suffixed spelling. Only the pairings digiquant serves are listed, so an
 * unsupported chart timeframe is a `null` map result and not a silent 400.
 */
const HOUSE_TIMEFRAMES: Readonly<Record<string, string>> = {
  "1": "1m",
  "5": "5m",
  "15": "15m",
  "30": "30m",
  "60": "1h",
  D: "1d",
  W: "1wk",
  M: "1mo",
};

/** The digiquant timeframe for a Vela timeframe, or `null` when we do not serve it. */
export function houseTimeframe(timeframe: string): string | null {
  return HOUSE_TIMEFRAMES[timeframe.trim()] ?? null;
}

/** Bars requested per fetch. digiquant caps `/bars` at `MAX_LIMIT`; 300 is well under. */
const HOUSE_BAR_LIMIT = 300;

/** digiquant's `/bars` defaults to 500; ask for the newest, so a bounded window is the norm. */
function houseBarsBaseUrl(): string {
  // Read per call, not at module scope: the export inlines this at build time and
  // tests stub the env between imports (the rule `lib/live/market-data.ts` sets).
  return (process.env.NEXT_PUBLIC_DIGIQUANT_BASE_URL ?? "").trim().replace(/\/+$/, "");
}

/** One `/bars` row exactly as digiquant shapes it. */
interface HouseBarRow {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * `/bars` rows -> Vela's `OHLCV`. A row is dropped rather than plotted wrong:
 * an unparseable open time or a non-finite OHLC value has no honest rendering.
 * Output stays oldest-first, which is the order Vela documents.
 */
export function houseBarsFromResponse(payload: unknown): OHLCV[] {
  const bars = (payload as { bars?: unknown })?.bars;
  if (!Array.isArray(bars)) return [];
  const out: OHLCV[] = [];
  for (const row of bars as HouseBarRow[]) {
    const time = Date.parse(String(row?.timestamp ?? ""));
    if (!Number.isFinite(time)) continue;
    if (!isFiniteNumber(row.open) || !isFiniteNumber(row.high) || !isFiniteNumber(row.low)) continue;
    if (!isFiniteNumber(row.close)) continue;
    const bar: OHLCV = { time, open: row.open, high: row.high, low: row.low, close: row.close };
    if (isFiniteNumber(row.volume)) bar.volume = row.volume;
    out.push(bar);
  }
  return out;
}

/**
 * Newest-last OHLCV for `symbol` from the keyless digiquant route.
 *
 * Empty when unconfigured or unanswerable — a failed read must never be shown as
 * "this symbol has no history", which is the vendor feed's failure mode.
 */
export async function fetchHouseBars(
  symbol: string,
  timeframe: string,
  limit: number = HOUSE_BAR_LIMIT,
): Promise<OHLCV[]> {
  const base = houseBarsBaseUrl();
  if (!base) return [];
  const tf = houseTimeframe(timeframe);
  if (!tf) return [];
  const query = new URLSearchParams({ symbol, timeframe: tf, limit: String(limit) });
  try {
    const res = await fetch(`${base}/bars?${query.toString()}`);
    if (!res.ok) return [];
    return houseBarsFromResponse(await res.json());
  } catch {
    return [];
  }
}

/**
 * The `DataProvider` the desk registers. `stream` is false on purpose: we serve
 * history, and a provider that claims to stream must not be asked to.
 */
export class HouseBarsProvider implements DataProvider {
  async getBars(ticker: string, timeframe: string, _range: BarRange): Promise<OHLCV[]> {
    return fetchHouseBars(ticker, timeframe, _range?.limit ?? HOUSE_BAR_LIMIT);
  }

  info(): ProviderInfo {
    return {
      name: HOUSE_PROVIDER_NAME,
      displayName: "digithings (digiquant)",
      requiresApiKey: false,
      supportedTimeframes: Object.keys(HOUSE_TIMEFRAMES),
      capabilities: { enumerate: true, stream: false, symbolInfo: true },
    };
  }

  /** Declaring enumeration means a bare ticker resolves here, not to a vendor. */
  async listSymbols(): Promise<SymbolDescriptor[]> {
    return [];
  }
}
