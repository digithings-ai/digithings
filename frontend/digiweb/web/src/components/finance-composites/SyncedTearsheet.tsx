"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  BaselineSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type AreaData,
  type BaselineData,
  type IChartApi,
  type Time,
} from "lightweight-charts";

/**
 * SyncedTearsheet — the multi-pane tearsheet chart promoted from the design
 * reference (finance/synced-tearsheet): ONE Lightweight Charts instance, two
 * panes sharing a single time axis — cumulative equity on top, the underwater
 * drawdown below. Because both live in one chart, the x-axis, crosshair and
 * zoom are synced natively (no cross-chart plumbing). Equity wears the module
 * accent (identity); drawdown wears --down (it only ever reads negative) —
 * per the charting house rules, every color is read from a design token at
 * runtime and a MutationObserver on data-theme re-themes live.
 *
 * This IS the multi-series primitive: add a pane per series rather than
 * stacking separate charts. The finance-charts family's single-series
 * specimens (price-chart / equity-curve / drawdown-plot) are siblings, not
 * children — composites embed this component directly. Give the host a
 * definite height (the reference wraps it in `.pc-frame--tall`); autoSize
 * fills it. Canvas-only, so nothing to read without JS — decorative by
 * default (aria-hidden) unless you pass `ariaLabel`.
 *
 * Wiring (in the consuming app):
 *   package: lightweight-charts ^5.2.0
 *   globals.css   @source "<path-to>/digiweb/web/src/components/finance-composites";
 *   (no family CSS needed — the chart paints from tokens on canvas)
 */
export type TearsheetPoint = {
  /** ISO date, yyyy-mm-dd — Lightweight Charts business-day time. */
  time: string;
  value: number;
};

export type SyncedTearsheetProps = {
  /** Cumulative equity series (pane 0, module accent). */
  equity: TearsheetPoint[];
  /**
   * Underwater drawdown series (pane 1, --down), in percent (≤ 0). Derived
   * from `equity`'s running peak (one decimal) when omitted.
   */
  drawdown?: TearsheetPoint[];
  /** Height share of the equity pane relative to the drawdown pane's 1. */
  equityStretch?: number;
  /** Describes the chart to AT; omitted = decorative (aria-hidden). */
  ariaLabel?: string;
  /** Extra classes on the host (defaults fill the parent: h-full w-full). */
  className?: string;
};

function deriveDrawdown(equity: TearsheetPoint[]): TearsheetPoint[] {
  let peak = -Infinity;
  return equity.map((p) => {
    peak = Math.max(peak, p.value);
    return { time: p.time, value: Math.round((p.value / peak - 1) * 1000) / 10 };
  });
}

export function SyncedTearsheet({
  equity,
  drawdown,
  equityStretch = 2.4,
  ariaLabel,
  className,
}: SyncedTearsheetProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || equity.length === 0) return;
    const cssVar = (name: string, fb: string) =>
      getComputedStyle(host).getPropertyValue(name).trim() || fb;
    const toRgba = (col: string, a: number) => {
      const m = col.match(/[\d.]+/g);
      if (col.startsWith("#") || !m || m.length < 3) return col;
      return `rgba(${m[0]},${m[1]},${m[2]},${a})`;
    };

    const palette = () => ({
      inkMute: cssVar("--ink-mute", "#8A9097"),
      hair: cssVar("--hair", "rgba(255,255,255,0.1)"),
      accent: cssVar("--accent", "#3dd6c4"),
      down: cssVar("--down", "#E0654B"),
      mono: cssVar("--font-mono", "monospace"),
    });
    let p = palette();

    const chart: IChartApi = createChart(host, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: p.inkMute,
        fontFamily: p.mono,
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { color: p.hair }, horzLines: { color: p.hair } },
      rightPriceScale: { borderColor: p.hair },
      timeScale: { borderColor: p.hair, timeVisible: false },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: p.inkMute, labelBackgroundColor: p.accent },
        horzLine: { color: p.inkMute, labelBackgroundColor: p.accent },
      },
    });

    // pane 0 — cumulative equity (identity accent)
    const equitySeries = chart.addSeries(
      AreaSeries,
      {
        lineColor: p.accent,
        topColor: toRgba(p.accent, 0.28),
        bottomColor: toRgba(p.accent, 0.02),
        lineWidth: 2,
        priceLineVisible: false,
      },
      0,
    );
    equitySeries.setData(
      equity.map((pt): AreaData => ({ time: pt.time as Time, value: pt.value })),
    );

    // pane 1 — underwater drawdown (money --down)
    const drawdownSeries = chart.addSeries(
      BaselineSeries,
      {
        baseValue: { type: "price", price: 0 },
        topLineColor: "transparent",
        topFillColor1: "transparent",
        topFillColor2: "transparent",
        bottomLineColor: p.down,
        bottomFillColor1: toRgba(p.down, 0.05),
        bottomFillColor2: toRgba(p.down, 0.32),
        lineWidth: 2,
        priceLineVisible: false,
        // this pane is always the underwater drawdown series (percent, ≤ 0) —
        // format the axis accordingly rather than leaving it bare numbers.
        priceFormat: { type: "custom", formatter: (v: number) => `${v.toFixed(1)}%`, minMove: 0.1 },
      },
      1,
    );
    drawdownSeries.setData(
      (drawdown ?? deriveDrawdown(equity)).map(
        (pt): BaselineData => ({ time: pt.time as Time, value: pt.value }),
      ),
    );

    // give the equity pane the lion's share of the height
    const panes = chart.panes();
    panes[0]?.setStretchFactor(equityStretch);
    panes[1]?.setStretchFactor(1);

    chart.timeScale().fitContent();

    const retheme = () => {
      p = palette();
      chart.applyOptions({
        layout: { textColor: p.inkMute },
        grid: { vertLines: { color: p.hair }, horzLines: { color: p.hair } },
        rightPriceScale: { borderColor: p.hair },
        timeScale: { borderColor: p.hair },
      });
      equitySeries.applyOptions({
        lineColor: p.accent,
        topColor: toRgba(p.accent, 0.28),
        bottomColor: toRgba(p.accent, 0.02),
      });
      drawdownSeries.applyOptions({
        bottomLineColor: p.down,
        bottomFillColor1: toRgba(p.down, 0.05),
        bottomFillColor2: toRgba(p.down, 0.32),
      });
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => {
      themeObs.disconnect();
      chart.remove();
    };
  }, [equity, drawdown, equityStretch]);

  return (
    <div
      className={className ?? "h-full w-full"}
      ref={hostRef}
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : "true"}
    />
  );
}
