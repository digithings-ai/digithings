/**
 * Per-asset strategy notes + backtest metadata at the bottom of the tearsheet.
 */

import type { TearsheetData } from "./types";

const SLAPPER_SUFFIX = "_slapper";

export function isSlapperStrategy(strategy: string): boolean {
  return strategy.endsWith(SLAPPER_SUFFIX) || strategy.includes("slapper");
}

/** Homepage carousel copy — shared across the slapper library (no per-asset names). */
export function strategyLibraryDescription(): string[] {
  return [
    "A pre-built strategy library: custom systems researched, backtested, and calibrated on the digiquant stack. Mean-reversion signals at local extremes work alongside a medium-horizon trend layer, tuned for long and short participation from either layer or both.",
    "The catalog ships with liquid majors first and grows as new assets clear the same pipeline — each release uses the same methodology with asset-specific tuning.",
  ];
}

export function theoryCopy(asset: string, strategy: string): string[] {
  if (strategy.includes("sdca")) {
    return [
      `${asset} power-law remaining-book: each day buys a percent of remaining cash or sells a percent of remaining holdings from a power-law valuation index. Extra indicators (M2, DXY, weekly RSI/MACD, SMA band, BTC/ETH relative strength) are unused — their weights are 0. This is not a multi-indicator composite.`,
      "Nautilus vs-flat and vs-lump are the full backtest window, not walk-forward out-of-sample. Published walk-forward does not beat flat DCA.",
      "Signals are delayed 3 days. This page is a backtest — not a live trading strategy.",
    ];
  }
  if (!isSlapperStrategy(strategy)) return [];
  const lines = [
    `Mean-reversion signals tuned for high-probability local tops and bottoms work alongside a medium-horizon trend layer, calibrated for long and short participation on ${asset}. Entries can fire from either layer or both; exits follow the same logic — staying with meaningful trends while navigating volatile extremes.`,
  ];
  if (strategy.startsWith("btc_")) {
    lines.push(
      "A drawdown-sensitive reversal guard can flip the book when a mean-reversion entry moves against the prevailing trend.",
    );
  }
  return lines;
}

function metaLines(data: TearsheetData): string[] {
  const fromJson = data.notes
    .map((n) =>
      n
        .replace(/NautilusTrader\s+backtest,?\s*/gi, "")
        .replace(/\s*Slapper/gi, " long/short")
        .trim(),
    )
    .filter(Boolean);

  return [
    ...(data.data_source ? [`Data source: ${data.data_source}`] : []),
    ...fromJson,
    ...(data.generated_at ? [`Generated ${data.generated_at}`] : []),
  ];
}

export function StrategyNotes({
  data,
  asset,
  printing = false,
}: {
  data: TearsheetData;
  asset: string;
  printing?: boolean;
}) {
  const theory = theoryCopy(asset, data.strategy);
  const meta = metaLines(data);
  if (theory.length === 0 && meta.length === 0) return null;

  return (
    <details className="ts-strategy-notes" open={printing || undefined}>
      <summary className="ts-strategy-notes-summary">
        <span className="ts-strategy-notes-label">Notes</span>
        <span className="ts-strategy-notes-chevron" aria-hidden="true" />
      </summary>
      <div className="ts-strategy-notes-body">
        {theory.map((line) => (
          <p key={line}>{line}</p>
        ))}
        {meta.length > 0 ? (
          <ul className="ts-strategy-notes-meta">
            {meta.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </details>
  );
}
