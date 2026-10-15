/**
 * The ticker universe behind the marketing tearsheets band.
 *
 * The live universe is the UNION of two reads that are themselves API/DB
 * sourced, never a hand-kept list (DIG-2858):
 *
 * 1. the digiquant workflow portfolio holdings — `/portfolio` on the official
 *    read API, `data.positions[].ticker`; and
 * 2. every symbol in the backend price tables — the R2 market Worker's own
 *    manifest, `GET /v1/market/tickers`.
 *
 * A symbol added to the R2 archive or bought into the book therefore reaches
 * the ticker with no frontend edit. {@link loadTapeUniverse} is the only
 * caller-facing entry point; {@link mergeTapeUniverse} is the pure join.
 *
 * {@link TAPE_SYMBOLS} is retained as the DEGRADED FALLBACK for a build with
 * `NEXT_PUBLIC_MARKET_DATA_URL` unset (`apps/digiquant-web/.env.local.example`
 * ships it commented out). It is the snapshot of
 * `digiquant/src/digiquant/data/prices/ticker_venues.py` (`_NYSE_TICKERS`,
 * `_CRYPTO_TICKERS`, `_FX_TICKERS`) as it stood when this module was written:
 * ETFs (incl. commodity and fixed-income funds), currencies, crypto. It is no
 * longer the source of the universe and is deliberately short of the live
 * manifest — the live read carries symbols this list never had.
 */
import { officialGet } from "@/lib/official-api";
import { fetchMarketTickers } from "./market-data";

/**
 * Baseline snapshot of the core backfill universe in
 * `digiquant/src/digiquant/data/prices/ticker_venues.py`. Fallback only — see
 * the module docstring. Yahoo `=X` spellings in `_FX_TICKERS` are aliases of
 * the four FX codes already listed, so this snapshot shows each asset once.
 */
export const TAPE_SYMBOLS = [
  // US equity ETFs, by group as ticker_venues.py groups them.
  "SPY", "QQQ", "DIA", "IWB", "VTI", "MDY", "IJH", "IWM", "IJR",
  "XLK", "XLF", "XLE", "XLV", "XLI", "XLRE", "XLU", "XLY", "XLP", "XLB", "XLC",
  "EFA", "VEA", "VGK", "EWJ", "EWG", "EWU", "EWA", "EEM", "VWO", "FXI",
  "ASHR", "EWZ", "EWT", "EWY", "INDA",
  "GLD", "IAU", "SLV", "DBO", "USO", "BNO", "PDBC", "DJP", "CPER",
  "BIL", "SHV", "SHY", "IEF", "TLT", "AGG", "HYG", "LQD", "TIP", "EMB", "UUP",
  // Crypto: spot pairs, then the US-listed crypto ETFs.
  "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "TRX-USD", "DOGE-USD",
  "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "BCH-USD", "LTC-USD",
  "NEAR-USD", "ATOM-USD", "XMR-USD", "SUI20947-USD",
  "BITO", "IBIT", "FBTC", "ETHA", "FETH", "GBTC",
  // FX majors.
  "EURUSD", "GBPUSD", "JPYUSD", "CADUSD",
] as const;

/**
 * Canonical spelling for one wire symbol. Yahoo emits FX as `EURUSD=X`, which
 * is the same asset as `EURUSD` — mapping to the base keeps one entry per
 * asset instead of dropping the alias and, worse, listing the same pair twice.
 */
export function canonicalTapeSymbol(raw: string): string | null {
  const trimmed = raw.trim().toUpperCase();
  if (!trimmed) return null;
  const base = trimmed.split("=")[0];
  return base || null;
}

/**
 * The union of portfolio holdings and the price-table symbols, in first-seen
 * order: house book first, then the archive. Pure, so the join is testable
 * without a network.
 *
 * Case and whitespace are normalised, Yahoo `=X` aliases collapse onto their
 * base symbol, and every symbol appears exactly once. A symbol held but not in
 * the archive still reaches the tape (it is the book's exposure and deserves a
 * row); a symbol in the archive but not held still reaches it (that is the
 * price table).
 */
export function mergeTapeUniverse(
  portfolioTickers: readonly string[],
  marketTickers: readonly string[],
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of [...portfolioTickers, ...marketTickers]) {
    if (typeof raw !== "string") continue;
    const symbol = canonicalTapeSymbol(raw);
    if (symbol === null || seen.has(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
  }
  return out;
}

/** Portfolio tickers out of an official `/portfolio` read. Empty on any other shape. */
export function portfolioTickersFrom(body: unknown): string[] {
  const data = isRecord(body) ? body.data : undefined;
  const positions = isRecord(data) ? data.positions : undefined;
  if (!Array.isArray(positions)) return [];
  return positions.flatMap((row) => {
    const ticker = isRecord(row) ? row.ticker : undefined;
    return typeof ticker === "string" ? [ticker] : [];
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * The live universe: portfolio holdings ∪ price-table symbols.
 *
 * Both reads are independent, so either may fail alone — a withheld portfolio
 * still yields the archive, and an unconfigured market worker still yields the
 * book. Only when BOTH are empty does this fall back to
 * {@link TAPE_SYMBOLS}, so a missing feed degrades to the old baseline rather
 * than to an empty ticker.
 */
export async function loadTapeUniverse(): Promise<string[]> {
  const [market, portfolio] = await Promise.all([
    fetchMarketTickers(),
    officialGet("/portfolio").then((read) => (read.ok ? portfolioTickersFrom(read.body) : [])),
  ]);
  const universe = mergeTapeUniverse(portfolio, market);
  return universe.length > 0 ? universe : [...TAPE_SYMBOLS];
}
