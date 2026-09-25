/**
 * `GET /portfolio` response builder for the dashboard-api worker (slice 0003).
 *
 * Assembles the contract §6.1 shape from one committed-book read: the folded
 * `book_as_of` gate, the NAV tip (raw invested KPI, seam/gap-guarded day
 * return), the seam object, the invested envelope pair, and reconciled
 * positions laid out inside the clamped-100 envelope.
 *
 * Pure logic — the route layer supplies rows (house-pinned reads) and maps
 * the `not_found` result to the §2 error envelope. No I/O, no secrets,
 * no time/tool-call budgets.
 */

import { reconcileBook, type BookPositionInput, type ReconciledRow } from './book';
import { committedBookDate } from './committed-book';
import {
  buildNavSeries,
  calendarDaysBetween,
  crossesNavSeam,
  navRowContractLabel,
  type NavContract,
  type NavInputRow,
} from './nav-series';
import {
  buildInvestedEnvelope,
  resolveInvestedPct,
  type InvestedDefinition,
} from './invested';

export interface PortfolioNavTipInput extends NavInputRow {
  investedPct?: number | null;
  cashPct?: number | null;
}

export interface PortfolioData {
  bookAsOf: string;
  navTip: {
    date: string;
    nav: number;
    contract: NavContract;
    investedPct: number | null;
    cashPct: number | null;
    dayReturnPct: number | null;
  } | null;
  seam: { crossesNavSeam: boolean; lagDays: number | null; lagDirection: string | null };
  invested: {
    kpiPct: number | null;
    envelopePct: number | null;
    cashPct: number | null;
    definition: InvestedDefinition;
  };
  positions: ReconciledRow[];
}

export type PortfolioResult =
  | { ok: true; data: PortfolioData }
  | { ok: false; error: { code: 'not_found'; message: string } };

/**
 * Build the §6.1 payload. `snapshotDate` is the latest `daily_snapshots.date`;
 * `positionDates` are the distinct `positions.date` values visible to the
 * house read; `positions` are the rows on the committed date; `navRows` the
 * accounting NAV history; `metricsInvestedPct` the
 * `portfolio_metrics.invested_pct` fallback; `metricsAsOf` the metrics stamp
 * for the seam lag chrome.
 */
export function buildPortfolioData(args: {
  snapshotDate: string | null | undefined;
  positionDates: readonly string[];
  positions: ReadonlyArray<BookPositionInput>;
  navRows: ReadonlyArray<PortfolioNavTipInput>;
  metricsInvestedPct?: number | null;
  metricsAsOf?: string | null;
}): PortfolioResult {
  const bookAsOf = committedBookDate(args.snapshotDate, args.positionDates);
  if (!bookAsOf) {
    return {
      ok: false,
      error: { code: 'not_found', message: 'no committed book for asOf' },
    };
  }

  const sortedNav = [...args.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sortedNav.at(-1) ?? null;
  const prior = sortedNav.length >= 2 ? sortedNav[sortedNav.length - 2] : null;
  const series = buildNavSeries(sortedNav);
  const tipPoint = tip ? series.find((p) => p.date === tip.date) ?? null : null;

  const heldSum = args.positions
    .filter((p) => p.ticker.trim().toUpperCase() !== 'CASH')
    .reduce((s, p) => s + (p.weightActual ?? 0), 0);
  const resolved = resolveInvestedPct({
    tipInvestedPct: tip?.investedPct ?? null,
    bookWeightInvestedPct: heldSum,
    metricsInvestedPct: args.metricsInvestedPct ?? null,
  });
  const envelope = buildInvestedEnvelope(resolved, heldSum);
  const book = reconcileBook(args.positions, { investedPct: resolved.investedPct });

  const metricsAsOf = args.metricsAsOf?.slice(0, 10) ?? null;
  const lagDays =
    tip && metricsAsOf ? calendarDaysBetween(metricsAsOf, tip.date) : null;
  const lagDirection =
    lagDays == null || Math.abs(lagDays) < 1
      ? null
      : lagDays > 0
        ? 'metrics lag'
        : 'nav lag';

  return {
    ok: true,
    data: {
      bookAsOf,
      navTip: tip
        ? {
            date: tip.date,
            nav: tip.nav,
            contract: navRowContractLabel(tip),
            investedPct:
              tip.investedPct != null && Number.isFinite(tip.investedPct)
                ? tip.investedPct
                : null,
            cashPct:
              tip.cashPct != null && Number.isFinite(tip.cashPct) ? tip.cashPct : null,
            dayReturnPct: tipPoint?.dayReturnPct ?? null,
          }
        : null,
      seam: {
        crossesNavSeam: tip ? crossesNavSeam(tip, prior) : false,
        lagDays,
        lagDirection,
      },
      invested: {
        kpiPct: envelope.kpiPct,
        envelopePct: envelope.envelopePct,
        cashPct: envelope.cashPct,
        definition: envelope.definition,
      },
      positions: book.rows,
    },
  };
}
