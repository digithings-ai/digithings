"use client";

import { useEffect, useRef } from "react";
import {
  BaselineSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type BaselineData,
  type IChartApi,
  type Time,
} from "lightweight-charts";

/** Deterministic drawdown series: run an equity walk, measure % below the
 *  running peak. Every value is ≤ 0 — the classic "underwater" curve. */
function generate(n: number) {
  let seed = 5150;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const data: BaselineData[] = [];
  let equity = 100;
  let peak = 100;
  const start = new Date(Date.UTC(2022, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i * 7);
    const time = date.toISOString().slice(0, 10) as unknown as Time;
    equity *= 1 + (rnd() - 0.44) * 0.05;
    peak = Math.max(peak, equity);
    data.push({ time, value: Math.round((equity / peak - 1) * 1000) / 10 });
  }
  return data;
}

const DATA = generate(210);

export function DrawdownPlotReference() {
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
        vertLine: { color: p.inkMute, labelBackgroundColor: p.down },
        horzLine: { color: p.inkMute, labelBackgroundColor: p.down },
      },
    });

    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: 0 },
      topLineColor: "transparent",
      topFillColor1: "transparent",
      topFillColor2: "transparent",
      bottomLineColor: p.down,
      bottomFillColor1: toRgba(p.down, 0.05),
      bottomFillColor2: toRgba(p.down, 0.32),
      lineWidth: 2,
      priceLineVisible: false,
    });
    series.setData(DATA);
    chart.timeScale().fitContent();

    const retheme = () => {
      p = palette();
      chart.applyOptions({
        layout: { textColor: p.inkMute },
        grid: { vertLines: { color: p.hair }, horzLines: { color: p.hair } },
        rightPriceScale: { borderColor: p.hair },
        timeScale: { borderColor: p.hair },
      });
      series.applyOptions({
        bottomLineColor: p.down,
        bottomFillColor1: toRgba(p.down, 0.05),
        bottomFillColor2: toRgba(p.down, 0.32),
      });
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    // autoSize tracks width + height from the host, so the chart fills the pane.

    return () => {
      themeObs.disconnect();
      chart.remove();
    };
  }, []);

  return <div className="pc-host dd-host" ref={hostRef} aria-hidden="true" />;
}
