/**
 * Sortable data table — a strategy leaderboard you can reorder by any column.
 * Click a header to sort (toggles asc/desc), the active column shows a caret and
 * carries aria-sort; numeric columns sort numerically, text lexically. Returns
 * wear the up colour, drawdown the down colour; everything else stays ink.
 * Consumes the shared <SortableTable/> primitive from @digithings/web.
 */
import { SortableTable, type SortableColumn } from "@digithings/web";

type Row = { strat: string; cagr: number; pf: number; win: number; dd: number; sharpe: number };

const ROWS: Row[] = [
  { strat: "trend_xsec", cagr: 44.9, pf: 2.31, win: 58, dd: -18.4, sharpe: 1.87 },
  { strat: "carry", cagr: 31.2, pf: 3.02, win: 64, dd: -12.1, sharpe: 2.4 },
  { strat: "mean_rev", cagr: 38.5, pf: 2.58, win: 61, dd: -22.0, sharpe: 1.6 },
  { strat: "breakout", cagr: 52.1, pf: 1.94, win: 49, dd: -29.3, sharpe: 1.2 },
  { strat: "pairs", cagr: 18.4, pf: 1.71, win: 55, dd: -9.8, sharpe: 1.9 },
  { strat: "momentum", cagr: 41.0, pf: 2.1, win: 52, dd: -24.6, sharpe: 1.4 },
];

const COLS: SortableColumn<Row>[] = [
  { key: "strat", label: "strategy", emphasis: true },
  {
    key: "cagr",
    label: "cagr",
    numeric: true,
    format: (v) => `+${(v as number).toFixed(1)}%`,
    tone: "up",
  },
  { key: "pf", label: "pf", numeric: true, format: (v) => (v as number).toFixed(2) },
  { key: "win", label: "win", numeric: true, format: (v) => `${v}%` },
  {
    key: "dd",
    label: "max dd",
    numeric: true,
    format: (v) => `${(v as number).toFixed(1)}%`,
    tone: "down",
  },
  { key: "sharpe", label: "sharpe", numeric: true, format: (v) => (v as number).toFixed(2) },
];

export function SortableTableReference() {
  return (
    <section className="section-block" id="sortable-table">
      <p className="kicker">{"// sortable table"}</p>
      <h2 className="title">Rank by any column.</h2>
      <p className="section-copy">
        A strategy leaderboard you can reorder — click a header to sort, click again to flip. The
        active column shows a caret and reports <code>aria-sort</code>; numbers sort numerically,
        text lexically. Returns wear the up color, drawdown the down.
      </p>

      <SortableTable
        rows={ROWS}
        columns={COLS}
        rowKey={(r) => r.strat}
        defaultSort={{ key: "pf", dir: "desc" }}
        className="mt-[1.2rem]"
      />
    </section>
  );
}
