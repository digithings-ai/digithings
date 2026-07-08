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
 * One Lightweight Charts instance, two panes sharing a single time axis:
 * cumulative equity on top, the underwater drawdown below. Both series are
 * derived from the *same* walk, so a dip in equity is the same bar as the red
 * beneath it — and because they live in one chart, the x-axis, crosshair and
 * zoom are synced natively (no cross-chart plumbing). Equity wears the module
 * accent (identity); drawdown wears --down (it only ever reads negative).
 */
function generate(n: number) {
  let seed = 730217;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const equity: AreaData[] = [];
  const drawdown: BaselineData[] = [];
  let eq = 100;
  let peak = 100;
  const start = new Date(Date.UTC(2022, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i * 7);
    const time = date.toISOString().slice(0, 10) as unknown as Time;
    eq = Math.max(40, eq * (1 + (rnd() - 0.44) * 0.05));
    peak = Math.max(peak, eq);
    equity.push({ time, value: eq });
    drawdown.push({ time, value: Math.round((eq / peak - 1) * 1000) / 10 });
  }
  return { equity, drawdown };
}

const DATA = generate(210);

export function SyncedTearsheetReference() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
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
    const equity = chart.addSeries(
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
    equity.setData(DATA.equity);

    // pane 1 — underwater drawdown (money --down)
    const drawdown = chart.addSeries(
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
      },
      1,
    );
    drawdown.setData(DATA.drawdown);

    // give the equity pane the lion's share of the height
    const panes = chart.panes();
    panes[0]?.setStretchFactor(2.4);
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
      equity.applyOptions({
        lineColor: p.accent,
        topColor: toRgba(p.accent, 0.28),
        bottomColor: toRgba(p.accent, 0.02),
      });
      drawdown.applyOptions({
        bottomLineColor: p.down,
        bottomFillColor1: toRgba(p.down, 0.05),
        bottomFillColor2: toRgba(p.down, 0.32),
      });
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      themeObs.disconnect();
      chart.remove();
    };
  }, []);

  return <div className="h-full w-full" ref={hostRef} aria-hidden="true" />;
}
