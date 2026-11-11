import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { reconcileBook } from "./book-reconciliation";
import { sortTickerUniverse } from "./benchmark-tickers";
import type { Position } from "./types";

function position(ticker: string, weightActual: number): Position {
  return {
    ticker,
    name: ticker,
    type: "LONG",
    weight_actual: weightActual,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: "",
    thesis_ids: [],
    category: "",
    pm_notes: "",
    stats: {},
  };
}

describe("@digithings-ai/contract boundary", () => {
  it("keeps shared modules free of app-relative imports and React", () => {
    const dir = new URL(".", import.meta.url).pathname;
    const sources = readdirSync(dir).filter(
      (name) => name.endsWith(".ts") && !name.endsWith(".test.ts"),
    );
    expect(sources.length).toBeGreaterThan(0);
    for (const name of sources) {
      const text = readFileSync(join(dir, name), "utf8");
      expect(text, name).not.toMatch(/apps\/dashboard/);
      expect(text, name).not.toMatch(/\.\.\/\.\.\/dashboard/);
      // Framework-free: the R5 Worker bundle imports this package, so a React
      // or @digithings-ai/ui edge here would drag the component layer in.
      expect(text, name).not.toMatch(/from\s+["']react(-dom)?["']/);
      expect(text, name).not.toMatch(/@digithings-ai\/ui/);
    }
  });

  it("reconciles a book and sorts a ticker universe", () => {
    const book = reconcileBook(
      [position("CASH", 20), position("SPY", 40), position("QQQ", 40)],
      { investedPct: 80 },
    );
    expect(book.rows.map((row) => row.ticker).sort()).toEqual(["QQQ", "SPY"]);
    expect(book.investedPct).toBe(80);
    expect(sortTickerUniverse(["GLD", "SPY", "ZZZ"])[0]).toBe("SPY");
  });
});
