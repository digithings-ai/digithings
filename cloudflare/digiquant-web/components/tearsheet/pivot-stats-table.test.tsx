import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PivotStatsTable } from "./pivot-stats-table";
import type { TearsheetBreakdown, TearsheetData, TearsheetTrade } from "./types";

const BREAKDOWN: TearsheetBreakdown = {
  trades: 2,
  net_profit: 200,
  net_profit_pct: 20,
  gross_profit: 300,
  gross_loss: 100,
  percent_profitable: 50,
  profit_factor: 3,
  avg_trade: 100,
  wins: 1,
  losses: 1,
};

function trade(over: Partial<TearsheetTrade>): TearsheetTrade {
  return {
    n: 1,
    direction: "long",
    entry_label: "entry",
    entry_date: "2025-02-01",
    entry_price: 100,
    exit_date: "2025-03-01",
    exit_price: 106,
    qty: 1,
    pnl: 6,
    pnl_pct: 6,
    equity_after: 1060,
    exit_reason: "signal",
    max_runup_pct: 8,
    max_drawdown_pct: -2,
    ...over,
  };
}

const DATA: TearsheetData = {
  schema_version: "1.3",
  strategy: "btc_slapper",
  symbol: "BTC-USD",
  engine: "nautilus",
  generated_at: "2026-01-02T00:00:00Z",
  data_source: "test",
  period_start: "2025-01-01",
  period_end: "2026-01-01",
  bars: 365,
  initial_capital: 1000,
  final_equity: 1200,
  net_profit: 200,
  net_profit_pct: 20,
  max_drawdown_pct: -10,
  sharpe_ratio: 1.2,
  sortino_ratio: 1.5,
  calmar_ratio: 2,
  profit_factor: 3,
  win_rate_pct: 50,
  total_trades: 2,
  avg_trade: 100,
  overall: BREAKDOWN,
  long: BREAKDOWN,
  short: BREAKDOWN,
  equity_curve: [
    { t: "2025-01-01", v: 1000 },
    { t: "2025-07-01", v: 1100 },
    { t: "2026-01-01", v: 1200 },
  ],
  drawdown_curve: [
    { t: "2025-01-01", v: 0 },
    { t: "2025-07-01", v: -5 },
    { t: "2026-01-01", v: 0 },
  ],
  trades: [trade({}), trade({ n: 2, direction: "short", pnl: -4, pnl_pct: -4 })],
  notes: [],
};

describe("PivotStatsTable on the kit Table (wave 2 T3)", () => {
  const html = renderToStaticMarkup(<PivotStatsTable data={DATA} pivot="direction" />);

  it("renders the kit Table shell, not the native table grammar", () => {
    expect(html).toContain('data-slot="table"');
    expect(html).toContain('data-slot="table-header"');
    expect(html).toContain('data-slot="table-body"');
    expect(html).toContain("ctl-table");
    expect(html).toContain("ts-pivot-table");
    expect(html).not.toContain("ts-table ");
  });

  it("keeps all 18 metric rows with their labels", () => {
    const labels = [
      "Total return",
      "Avg annual return",
      "Max drawdown",
      "Sharpe ratio",
      "Sortino ratio",
      "Calmar ratio",
      "Omega ratio",
      "Annualized volatility",
      "Recovery factor",
      "Alpha vs buy-and-hold",
      "Trades",
      "Win rate",
      "Profit factor",
      "Avg trade %",
      "Avg winner %",
      "Avg loser %",
      "Best trade %",
      "Worst trade %",
    ];
    for (const label of labels) expect(html).toContain(`>${label}<`);
    expect(html.match(/data-slot="table-row"/g)).toHaveLength(1 + labels.length);
  });

  it("pivots by direction with a numeric column per slice", () => {
    expect(html).toContain(">all<");
    expect(html).toContain(">long<");
    expect(html).toContain(">short<");
    expect(html).toContain("ctl-table-num");
    expect(html).toContain("ts-pivot-col");
  });

  it("keeps the numeric treatment on data cells", () => {
    expect(html).toMatch(/<td[^>]*ctl-table-num[^>]*>/);
  });

  it("compact mode drops to the six preview metrics and the all column", () => {
    const compact = renderToStaticMarkup(<PivotStatsTable data={DATA} pivot="direction" compact />);
    expect(compact).toContain("ts-pivot-table-compact");
    expect(compact).toContain("ts-pivot-wrap-compact");
    expect(compact.match(/data-slot="table-row"/g)).toHaveLength(1 + 6);
    expect(compact).not.toContain(">all<");
    expect(compact).not.toContain("Worst trade %");
  });

  it("print mode renders both pivot blocks", () => {
    const printing = renderToStaticMarkup(<PivotStatsTable data={DATA} printing />);
    expect(printing).toContain("ts-pivot-stats-print");
    expect(printing).toContain("By direction");
    expect(printing).toContain("By year");
  });
});
