/**
 * Ledger-anchored weights for `GET /allocations` (contract §6.2, DIG-2803).
 *
 * `positions.weight_pct` is a drift-carrying ACTUAL written by several
 * independent writers; `position_events` is the rebalance LEDGER — the
 * operator's intended target weight per ticker. Chris's 2026-10-10 verdict:
 * the ledger's 25 Sep rebalance targets (UUP 15 / DBO 10 / XLV 10) are the
 * correct weights, so the read path must AGREE with the ledger rather than
 * echo an unreconciled writer output.
 *
 * This module is pure: it replays an already-fetched event list and reconciles
 * it against the committed book rows. It performs no I/O, so the route layer
 * owns the `position_events` read and can fail closed before calling in.
 *
 * Two rules keep this honest rather than clever:
 *  - FAIL CLOSED. A missing, unreadable, future-dated or unrecognised event
 *    never invents or zeroes a weight. The book value stands and the row is
 *    flagged `positions_no_ledger`. Callers that pass `null` get exactly the
 *    pre-DIG-2803 behaviour, byte for byte.
 *  - NOTHING IS HIDDEN. Anchoring `weight_pct` to the ledger target does not
 *    discard the positions value — every row carries `positionsWeightPct` and
 *    `driftPp` so the substitution stays measurable on the wire.
 *
 * `weight` vs `scaledWeight`: `weightPct` is the book's own weight; the
 * envelope in `book.ts` then rescales the held sum into the NAV tip's
 * `invested` %, so `scaledWeightPct` = `weightPct * (invested / heldSum)`.
 * The two are different quantities and are reported separately.
 */

/** `position_events.event` values the replay understands (mirrors §6.8). */
export const LEDGER_WEIGHT_EVENT_TYPES = ['OPEN', 'ADD', 'EXIT', 'TRIM'] as const;

export type LedgerWeightEventType = (typeof LEDGER_WEIGHT_EVENT_TYPES)[number];

/** One replayed `position_events` row, already mapped by the I/O layer. */
export interface LedgerWeightEvent {
  date: string;
  ticker: string;
  /** Raw `event` text; anything outside the four types is ignored. */
  event: string;
  weightPct: number | null;
  prevWeightPct?: number | null;
}

/** The ledger's current intended weight for one ticker. */
export interface LedgerTarget {
  ticker: string;
  weightPct: number;
  eventDate: string;
  event: LedgerWeightEventType;
  prevWeightPct: number | null;
}

/** Replay outcome. Counts are reported so a silent no-op is never confused
 * with "the ledger agrees". */
export interface LedgerWeightState {
  /** Ticker -> latest usable target. */
  targets: ReadonlyMap<string, LedgerTarget>;
  /** Tickers the ledger has EXITed and not re-opened. */
  exited: ReadonlySet<string>;
  /** Latest event date applied, or null when nothing was usable. */
  latestEventDate: string | null;
  applied: number;
  /** Events skipped: unparseable date or unknown event type. */
  ignored: number;
  /** Usable events dated after the committed book (never applied). */
  future: number;
  /** OPEN/ADD/TRIM events whose `weight_pct` was null or negative. */
  unusableWeight: number;
}

/** Where a row's emitted weight came from. */
export type WeightSource = 'ledger' | 'positions' | 'positions_no_ledger';

export interface ReconciledWeight {
  ticker: string;
  /** The raw `positions.weight_pct` this row started from. Never lost. */
  positionsWeightPct: number;
  /** The weight the envelope should lay out: ledger target when covered. */
  weightPct: number;
  weightSource: WeightSource;
  ledgerWeightPct: number | null;
  /** `positionsWeightPct - ledgerWeightPct`; null when not ledger-covered. */
  driftPp: number | null;
}

export interface WeightReconciliation {
  resolved: ReadonlyMap<string, ReconciledWeight>;
  /** Tickers whose emitted weight came from the ledger. */
  reconciledCount: number;
  /** Of those, how many the positions rows disagree with. */
  driftedCount: number;
  /** Non-CASH book tickers the ledger says nothing about. */
  unreconciled: string[];
  /** Tickers the ledger covers that have no positions row at all. */
  ledgerOnly: string[];
  /** Book rows the ledger has EXITed — a genuine conflict, surfaced. */
  conflicts: string[];
  /** The replay state, or null when the caller supplied no ledger. */
  state: LedgerWeightState | null;
}

const CALENDAR_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Same predicate the ledger reader uses — a shape check plus a UTC round
 * trip, so `2026-02-31` cannot pass. */
function isCalendarDate(v: string): boolean {
  if (!CALENDAR_DATE.test(v)) return false;
  const t = Date.parse(`${v}T00:00:00Z`);
  if (Number.isNaN(t)) return false;
  return new Date(t).toISOString().slice(0, 10) === v;
}

function roundPct(v: number): number {
  return Math.round(v * 1e6) / 1e6;
}

function eventType(raw: string): LedgerWeightEventType | null {
  const up = String(raw ?? '').trim().toUpperCase();
  return (LEDGER_WEIGHT_EVENT_TYPES as readonly string[]).includes(up)
    ? (up as LedgerWeightEventType)
    : null;
}

/**
 * Replay `position_events` into per-ticker target weights as of `bookDate`.
 *
 * Events dated after the committed book are counted and dropped: a committed
 * snapshot must never be reconciled against a decision taken after it.
 * `bookDate = null` returns an empty state — the caller then has no coverage.
 */
export function replayLedgerWeights(
  events: ReadonlyArray<LedgerWeightEvent>,
  bookDate: string | null,
): LedgerWeightState {
  const targets = new Map<string, LedgerTarget>();
  const exited = new Set<string>();
  const state: LedgerWeightState = {
    targets,
    exited,
    latestEventDate: null,
    applied: 0,
    ignored: 0,
    future: 0,
    unusableWeight: 0,
  };
  if (!bookDate || !isCalendarDate(bookDate)) return state;

  // Replay in date order so the reader's own ordering cannot change the
  // outcome. Ties keep arrival order (stable sort), and the state map already
  // holds the last write, so a same-day pair resolves to the later row.
  const ordered = [...events].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  for (const e of ordered) {
    const type = eventType(e?.event ?? '');
    if (type == null || !isCalendarDate(String(e?.date ?? ''))) {
      state.ignored += 1;
      continue;
    }
    if (e.date > bookDate) {
      state.future += 1;
      continue;
    }
    const ticker = String(e.ticker ?? '').trim();
    if (!ticker) {
      state.ignored += 1;
      continue;
    }
    if (type === 'EXIT') {
      targets.delete(ticker);
      exited.add(ticker);
      state.applied += 1;
      state.latestEventDate = later(state.latestEventDate, e.date);
      continue;
    }
    const w = e.weightPct;
    if (w == null || !Number.isFinite(w) || w < 0) {
      // Fail closed: an event we cannot read leaves the prior target standing
      // rather than silently resetting the position to zero.
      state.unusableWeight += 1;
      continue;
    }
    targets.set(ticker, {
      ticker,
      weightPct: w,
      eventDate: e.date,
      event: type,
      prevWeightPct: e.prevWeightPct ?? null,
    });
    exited.delete(ticker);
    state.applied += 1;
    state.latestEventDate = later(state.latestEventDate, e.date);
  }
  return state;
}

function later(a: string | null, b: string): string | null {
  return a == null || b > a ? b : a;
}

/**
 * Reconcile committed book rows against a replayed ledger.
 *
 * With `state == null`, or with a ledger that covers nothing, every row keeps
 * its positions weight and is labelled `positions_no_ledger` — the response is
 * then identical to the pre-DIG-2803 payload.
 */
export function reconcileWeightsAgainstLedger(
  positions: ReadonlyArray<{ ticker: string; weightActual?: number | null }>,
  state: LedgerWeightState | null,
): WeightReconciliation {
  const resolved = new Map<string, ReconciledWeight>();
  const unreconciled: string[] = [];
  const conflicts: string[] = [];
  const covered = state != null && state.targets.size > 0;

  for (const p of positions) {
    const ticker = String(p.ticker ?? '').trim();
    if (!ticker || ticker.toUpperCase() === 'CASH') continue; // CASH is never a ledger target
    const positionsWeightPct = Number.isFinite(p.weightActual as number) ? (p.weightActual as number) : 0;
    const target = covered ? state!.targets.get(ticker) ?? null : null;
    if (target == null) {
      if (state?.exited.has(ticker)) conflicts.push(ticker);
      else unreconciled.push(ticker);
      resolved.set(ticker, {
        ticker,
        positionsWeightPct,
        weightPct: positionsWeightPct,
        weightSource: 'positions',
        ledgerWeightPct: null,
        driftPp: null,
      });
      continue;
    }
    const driftPp = roundPct(positionsWeightPct - target.weightPct);
    resolved.set(ticker, {
      ticker,
      positionsWeightPct,
      weightPct: target.weightPct,
      weightSource: 'ledger',
      ledgerWeightPct: target.weightPct,
      driftPp,
    });
  }

  const seen = new Set([...resolved.keys()]);
  const ledgerOnly = covered
    ? [...state!.targets.keys()].filter((t) => !seen.has(t)).sort()
    : [];

  // Count the two figures off the SAME predicate (`weightSource === 'ledger'`),
  // so `reconciledCount` matches its documented contract on line 90 and a
  // conflict row -- which emits a POSITIONS weight -- is never counted as
  // reconciled. Deriving it from `resolved.size - unreconciled.length` would
  // also count conflict rows, which is exactly what inflates the number and
  // hides the conflict on the wire.
  let reconciledCount = 0;
  let driftedCount = 0;
  for (const r of resolved.values()) {
    if (r.weightSource !== 'ledger') continue;
    reconciledCount += 1;
    if (r.driftPp != null && Math.abs(r.driftPp) > 0) driftedCount += 1;
  }

  return {
    resolved,
    reconciledCount,
    driftedCount,
    unreconciled: unreconciled.sort(),
    ledgerOnly,
    conflicts: conflicts.sort(),
    state,
  };
}