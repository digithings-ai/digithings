"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type AreaData,
  type IChartApi,
  type Time,
} from "lightweight-charts";

/** Deterministic cumulative-equity walk (starts at 100, drifts up with dips). */
function generate(n: number) {
  let seed = 730217;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const data: AreaData[] = [];
  let equity = 100;
  const start = new Date(Date.UTC(2022, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i * 7);
    const time = date.toISOString().slice(0, 10) as unknown as Time;
    equity *= 1 + (rnd() - 0.44) * 0.05;
    data.push({ time, value: Math.max(40, equity) });
  }
  return data;
}

const DATA = generate(210);

export function EquityCurveReference() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const cssVar = (name: string, fb: string) =>
      getComputedStyle(host).getPropertyValue(name).trim() || fb;

    const palette = () => ({
      inkMute: cssVar("--ink-mute", "#8A9097"),
      hair: cssVar("--hair", "rgba(255,255,255,0.1)"),
      accent: cssVar("--accent", "#3dd6c4"),
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

    const toRgba = (col: string, a: number) => {
      const m = col.match(/[\d.]+/g);
      if (col.startsWith("#") || !m || m.length < 3) return col;
      return `rgba(${m[0]},${m[1]},${m[2]},${a})`;
    };

    const area = chart.addSeries(AreaSeries, {
      lineColor: p.accent,
      topColor: toRgba(p.accent, 0.28),
      bottomColor: toRgba(p.accent, 0.02),
      lineWidth: 2,
      priceLineVisible: false,
    });
    area.setData(DATA);
    chart.timeScale().fitContent();

    const retheme = () => {
      p = palette();
      chart.applyOptions({
        layout: { textColor: p.inkMute },
        grid: { vertLines: { color: p.hair }, horzLines: { color: p.hair } },
        rightPriceScale: { borderColor: p.hair },
        timeScale: { borderColor: p.hair },
      });
      area.applyOptions({
        lineColor: p.accent,
        topColor: toRgba(p.accent, 0.28),
        bottomColor: toRgba(p.accent, 0.02),
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

  return <div className="pc-host eq-host" ref={hostRef} aria-hidden="true" />;
}
