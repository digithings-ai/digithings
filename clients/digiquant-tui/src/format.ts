import { calendarDay, todayYmd, tradingSessionsSince } from "./pages/trading-calendar";

/**
 * One formatter for every desk read, terminal and website alike (DIG-2806).
 * The official API sends raw floats (`123.50887821352958`); the field name says
 * what the number is, so the field name picks the rounding:
 *   *_pct  percent, already ×100 by dashboard-api. 2 dp and a `%`.
 *          Returns and moves carry a sign; weights and shares of the book do not.
 *   *_bp   basis points, signed, 1 dp. The column header already says bp.
 *   *_usd  dollars. Under one dollar keeps 4 dp (LLM run costs).
 *   price  prices, NAV, index levels: 2 dp, grouped. FX quotes: 4 dp.
 *   count  integers, grouped.
 * Null is an em dash. Zero is a number: `0.00%`, never a dash.
 * A signed figure starts with `+` or `-`, so a renderer reads its tone off the
 * text (see `toneOf`) and the line format stays plain strings.
 */

export const DASH = "—";

type Kind = "pct" | "signed-pct" | "bp" | "usd" | "price" | "fx" | "count" | "ratio" | "plain";

const UNSIGNED_PCT = /(weight|invested|cash|envelope|allocated|win_rate|yield|^max_pct|^current_pct|vol|hit_rate|share)/;
const FX = /^(bid|offer|ask|spot|rate|fx_rate)$/;
const PRICE = /(^|_)(price|close|open|high|low|mark|nav|index|level|entry|avg_entry|base100_tip|paper_capital|balance)$/;
const COUNT =
  /^(shares|tokens_in|tokens_out|calls|ok|carried|failed|active|watch|exited|names|overlap_days|catalog|deployable|deployments|paper_accounts|portfolios|brokers|count|trades|n|rows)$|_count$/;
const RATIO = /(^|_)(beta|ratio|sharpe|sortino|calmar|information_ratio|r2|corr)$/;

export function fieldKind(key: string): Kind {
  const k = key.toLowerCase();
  if (/(^|_)pct$/.test(k)) return UNSIGNED_PCT.test(k) ? "pct" : "signed-pct";
  if (/(^|_)bps?$/.test(k)) return "bp";
  if (/(^|_)usd$/.test(k)) return "usd";
  if (FX.test(k)) return "fx";
  if (COUNT.test(k)) return "count";
  if (RATIO.test(k)) return "ratio";
  if (PRICE.test(k)) return "price";
  return "plain";
}

const grouped = (value: number, digits: number): string =>
  value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const signed = (text: string, value: number): string => (value > 0 ? `+${text}` : text);

/** A rounded zero must not keep its sign: -0.001 shows as `0.00`, not `-0.00`. */
function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  const rounded = Math.round(value * factor) / factor;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function plainNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  const digits = Math.abs(value) >= 1 ? 2 : 4;
  return grouped(round(value, digits), digits);
}

/** One number, rounded for its field. Non-finite is a dash. */
export function formatNumber(value: number, key = ""): string {
  if (!Number.isFinite(value)) return DASH;
  switch (fieldKind(key)) {
    case "signed-pct": {
      const v = round(value, 2);
      return `${signed(grouped(v, 2), v)}%`;
    }
    case "pct":
      return `${grouped(round(value, 2), 2)}%`;
    case "bp": {
      const v = round(value, 1);
      return signed(grouped(v, 1), v);
    }
    case "usd": {
      const digits = value !== 0 && Math.abs(value) < 1 ? 4 : 2;
      const v = round(value, digits);
      const body = grouped(Math.abs(v), digits);
      return v < 0 ? `-$${body}` : `$${body}`;
    }
    case "fx":
      return grouped(round(value, 4), 4);
    case "price":
      return grouped(round(value, 2), 2);
    case "count":
      return Number.isInteger(value) ? grouped(value, 0) : plainNumber(value);
    case "ratio":
      return grouped(round(value, 2), 2);
    case "plain":
      return plainNumber(value);
  }
}

const NUMERIC_TEXT = /^-?\d+(\.\d+)?$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;

/** The reader's own zone. The terminal runs on the reader's machine and the desk renders in their browser. */
export function readerTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * A timestamp in one zone, with that zone named: `2026-10-10 14:05 GMT+2`.
 * A calendar date (`2026-10-09`) is not a moment and is never shifted.
 */
export function formatTimestamp(value: string, timeZone: string = readerTimeZone()): string {
  if (!TIMESTAMP.test(value)) return value;
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return value;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZoneName: "short",
    })
      .formatToParts(new Date(ms))
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} ${parts.timeZoneName}`;
}

/**
 * One cell. `key` is the field name and picks the rounding; without it a number
 * gets the plain rule (integers as sent, decimals to 2 dp, under one to 4 dp).
 * A numeric string under a numeric key is formatted as that number.
 */
export function cell(value: unknown, key = "", timeZone?: string): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number") return formatNumber(value, key);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") {
    if (key && fieldKind(key) !== "plain" && NUMERIC_TEXT.test(value.trim())) return formatNumber(Number(value), key);
    return TIMESTAMP.test(value) ? formatTimestamp(value, timeZone) : value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "no rows";
    return value.map((item) => cell(item, key, timeZone)).join(", ");
  }
  return DASH;
}

export type Tone = "up" | "down" | null;

/** Tone of a formatted cell. Only signed figures carry one; a zero is flat. */
export function toneOf(text: string): Tone {
  if (/^\+\d/.test(text)) return "up";
  if (/^-\$?\d/.test(text) && /[1-9]/.test(text)) return "down";
  return null;
}

/** Age policy shared with the FX desk (DIG-183): trading sessions behind the data date. */
const SESSION_WARN = 2;
const SESSION_STALE = 3;

export type AsOf = {
  /** Footer text: both dates, then the age. The route when the read has no date. */
  label: string;
  /** Age badge text, or null when the read cannot be aged. */
  age: string | null;
  state: "fresh" | "warn" | "stale" | null;
};

function ageText(sessions: number): string {
  if (sessions === 0) return "current session";
  return sessions === 1 ? "1 trading day old" : `${sessions} trading days old`;
}

/**
 * Pane footer. A read carries two dates: the envelope `as_of` (the book asked
 * for; null means latest) and the data date (the tip the payload actually
 * holds). Show both when they differ, and age the data date, because that is
 * the one that goes stale.
 */
export function asOfStatus(
  route: string,
  asOf: string | null | undefined,
  dataAsOf: string | null | undefined,
  now: string = todayYmd(),
  staleAfter: number = SESSION_STALE,
): AsOf {
  const asked = calendarDay(asOf);
  const tip = calendarDay(dataAsOf);
  const shown = tip ?? asked;
  if (!shown) return { label: route, age: null, state: null };
  const dates = asked && tip && asked !== tip ? `as of ${asked} · data ${tip}` : `as of ${shown}`;
  const today = calendarDay(now);
  const sessions = tradingSessionsSince(shown, now);
  // A date ahead of the clock is skew, not freshness: name no age for it.
  if (sessions === null || (today !== null && shown > today)) return { label: dates, age: null, state: null };
  const staleAt = Number.isFinite(staleAfter) && staleAfter >= 1 ? Math.floor(staleAfter) : SESSION_STALE;
  const warnAt = Math.min(SESSION_WARN, Math.max(1, staleAt - 1));
  const state = sessions >= staleAt ? "stale" : sessions >= warnAt ? "warn" : "fresh";
  const age = ageText(sessions);
  return { label: `${dates} · ${age}${state === "fresh" ? "" : ` · ${state}`}`, age, state };
}
