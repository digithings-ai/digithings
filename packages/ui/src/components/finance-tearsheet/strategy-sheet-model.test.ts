import { describe, expect, it } from "vitest";
import { buildStrategyTearsheet, seriesOrNull, seriesSparkline } from "./strategy-sheet-model";

describe("buildStrategyTearsheet", () => {
  it("keeps unpublished figures empty and draws no chart from one point", () => {
    const model = buildStrategyTearsheet(null, { title: "BTC L/S", symbol: "BTC-USD" });
    expect(model.title).toBe("BTC L/S");
    expect(model.metrics.map((item) => item.value)).toEqual([null, null, null, null, null, null]);
    expect(model.position.every((item) => item.value === null)).toBe(true);
    expect(model.equity).toBeNull();
    expect(model.drawdown).toBeNull();
    expect(model.price).toBeNull();
    expect(model.trades).toBeNull();
    expect(seriesOrNull([{ t: "2026-01-01", v: 1 }])).toBeNull();
    expect(seriesSparkline([1])).toBeNull();
  });

  it("keeps a real series, a real trade, and a real position", () => {
    const model = buildStrategyTearsheet(
      {
        label: "BTC L/S",
        symbol: "BTC-USD",
        initial_capital: 100,
        final_equity: 121,
        period_start: "2024-01-01",
        period_end: "2025-01-01",
        max_drawdown_pct: -8,
        profit_factor: 1.4,
        win_rate_pct: 55,
        avg_trade_pct: 1.2,
        total_trades: 4,
        equity_curve: [
          { t: "2024-01-01", v: 100 },
          { t: "2024-06-01", v: 110 },
        ],
        drawdown_curve: [{ t: "2024-01-01", v: 0 }],
        ohlc_bars: [
          { t: "2024-01-01", o: 1, h: 2, l: 0.5, c: 1.5 },
          { t: "2024-01-02", o: 1.5, h: 2, l: 1, c: 1.8 },
        ],
        current_signal: { position: "long", entry_label: "break", last_price: 42, last_signal_date: "2025-01-01" },
        trades: [{ direction: "long", entry_date: "2024-02-01", entry_price: 10, exit_date: "2024-03-01", exit_price: 12, pnl_pct: 20 }],
      },
      { title: "fallback", symbol: "NOPE" },
    );
    expect(model.metrics.find((item) => item.label === "CAGR")?.value).toMatch(/%$/);
    expect(model.metrics.find((item) => item.label === "Max DD")?.value).toBe("-8.00%");
    expect(model.equity).toHaveLength(2);
    expect(model.drawdown).toBeNull();
    expect(model.price).toHaveLength(2);
    expect(model.position.find((item) => item.label === "Position")?.value).toBe("long");
    expect(model.trades?.rows[0]?.[0]).toBe("long");
    expect(seriesSparkline([1, 2])).toBe("▁█");
  });

  it("uses the DCA labels for an SDCA payload and does not invent a lump comparison", () => {
    const model = buildStrategyTearsheet(
      { strategy: "btc_sdca", kind: "dca", net_profit_pct: 3 },
      { title: "BTC-SDCA", symbol: "BTC-USD" },
    );
    expect(model.metrics.map((item) => item.label)).toEqual(["Total return", "Max DD", "Vs lump", "Allocated"]);
    expect(model.metrics[0]?.value).toBe("3.00%");
    expect(model.metrics[2]?.value).toBeNull();
  });
});
