import type { Vela } from "@luxalgo/vela";
import {
  candleSweepRange,
  heroOverlayInputs,
  paddedPriceWindow,
  revealYDomain,
  EMA_COLOR,
  EMA_LENGTH,
  SMA_COLOR,
  SMA_LENGTH,
  type HeroBar,
} from "@/lib/hero-build";

/** One-minute bars. The same bucket the homepage hero plots. */
export const VELA_BAR_MS = 60_000;

type PricePane = {
  kind?: string;
  manualScale: { min: number; max: number } | null;
  scale: { min: number; max: number };
  scaleTarget: { min: number; max: number };
};

type ScaleControl = {
  renderer?: {
    bars?: unknown;
    scene?: { panes?: { values: () => Iterable<PricePane> } };
    scheduler?: { invalidate: (tier: number) => void };
  };
  set: (feature: Record<string, unknown>) => void;
};

/** Coinbase rows, or the bars Vela already mounted. Drops anything that is not a real print. */
export function coinbaseBars(rows: unknown): HeroBar[] {
  if (!Array.isArray(rows)) return [];
  const out: HeroBar[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const bar = row as Partial<HeroBar>;
    const { time, open, high, low, close, volume } = bar;
    if (![time, open, high, low, close].every((n) => typeof n === "number" && Number.isFinite(n))) continue;
    out.push({
      time: time as number,
      open: open as number,
      high: high as number,
      low: low as number,
      close: close as number,
      volume: typeof volume === "number" ? volume : undefined,
    });
  }
  out.sort((a, b) => a.time - b.time);
  return out;
}

/** Price window for the finished series, including Bollinger. Not the empty 0–1 placeholder. */
export function lockedPriceWindow(bars: readonly HeroBar[]): { min: number; max: number } {
  return paddedPriceWindow(revealYDomain(bars, bars.length, "bollinger-bands"));
}

export function chartBars(chart: Vela, book: readonly HeroBar[]): HeroBar[] {
  const native = (chart.renderer as unknown as ScaleControl).renderer;
  const fromChart = coinbaseBars(native?.bars);
  if (fromChart.length >= 2) return fromChart;
  return [...book];
}

/**
 * Freeze the price pane on the series window. `autoScale: false` copies whatever
 * scale is current — the empty chart's 0–1 — so the real window is written after that.
 */
export function lockPriceFrame(chart: Vela, bars: readonly HeroBar[]): void {
  if (bars.length < 2) return;
  const price = lockedPriceWindow(bars);
  try {
    chart.setVisibleRange(candleSweepRange(bars[0].time, bars[bars.length - 1].time, VELA_BAR_MS));
  } catch {
    /* renderer without range control */
  }
  const control = chart.renderer as unknown as ScaleControl;
  const write = () => {
    const panes = control.renderer?.scene?.panes;
    if (!panes) return;
    const locked = { min: price.min, max: price.max };
    for (const pane of panes.values()) {
      if (pane.kind !== "price") continue;
      pane.manualScale = locked;
      pane.scale = locked;
      pane.scaleTarget = locked;
    }
  };
  write();
  try {
    control.set({ animAutoscale: 0, autoScale: false });
  } catch {
    /* renderer without a scale lock */
  }
  write();
  control.renderer?.scheduler?.invalidate(4);
}

/** SMA 20, EMA 50, and Bollinger — the studies the homepage hero paints on this feed. */
export function mountPriceStudies(chart: Vela): void {
  chart.addNativeIndicator("sma", { inputs: { length: SMA_LENGTH, color: SMA_COLOR } });
  chart.addNativeIndicator("ema", { inputs: { length: EMA_LENGTH, color: EMA_COLOR } });
  chart.addNativeIndicator("bollinger-bands", { inputs: heroOverlayInputs("bollinger-bands") });
}
