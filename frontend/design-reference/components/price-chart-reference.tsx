"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type Time,
} from "lightweight-charts";

/** Deterministic OHLC + volume walk so the demo looks the same every render. */
function generate(n: number) {
  let seed = 20260101;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const candles: CandlestickData[] = [];
  const volume: HistogramData[] = [];
  let price = 92;
  const start = new Date(Date.UTC(2026, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i);
    const time = date.toISOString().slice(0, 10) as unknown as Time;
    const drift = (rnd() - 0.47) * 3.4;
    const open = price;
    const close = Math.max(6, open + drift);
    const high = Math.max(open, close) + rnd() * 2.1;
    const low = Math.min(open, close) - rnd() * 2.1;
    candles.push({ time, open, high, low, close });
    volume.push({ time, value: 40 + rnd() * 120 });
    price = close;
  }
  return { candles, volume };
}

const DATA = generate(120);

export function PriceChartReference() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const cssVar = (name: string, fallback: string) =>
      getComputedStyle(host).getPropertyValue(name).trim() || fallback;

    const palette = () => ({
      ink: cssVar("--ink", "#ECEEF0"),
      inkMute: cssVar("--ink-mute", "#8A9097"),
      hair: cssVar("--hair", "rgba(255,255,255,0.1)"),
      up: cssVar("--up", "#3FB984"),
      down: cssVar("--down", "#E0654B"),
      accent: cssVar("--accent", "#3dd6c4"),
      mono: cssVar("--font-mono", "monospace"),
    });

    let p = palette();

    const chart: IChartApi = createChart(host, {
      width: host.clientWidth,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: p.inkMute,
        fontFamily: p.mono,
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: p.hair },
        horzLines: { color: p.hair },
      },
      rightPriceScale: { borderColor: p.hair },
      timeScale: { borderColor: p.hair, timeVisible: false },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: p.inkMute, labelBackgroundColor: p.accent },
        horzLine: { color: p.inkMute, labelBackgroundColor: p.accent },
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: p.up,
      downColor: p.down,
      borderUpColor: p.up,
      borderDownColor: p.down,
      wickUpColor: p.up,
      wickDownColor: p.down,
    });
    candles.setData(DATA.candles);

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: p.hair,
    });
    volume.setData(DATA.volume);
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    chart.timeScale().fitContent();

    const retheme = () => {
      p = palette();
      chart.applyOptions({
        layout: { textColor: p.inkMute },
        grid: { vertLines: { color: p.hair }, horzLines: { color: p.hair } },
        rightPriceScale: { borderColor: p.hair },
        timeScale: { borderColor: p.hair },
      });
      candles.applyOptions({
        upColor: p.up,
        downColor: p.down,
        borderUpColor: p.up,
        borderDownColor: p.down,
        wickUpColor: p.up,
        wickDownColor: p.down,
      });
      volume.applyOptions({ color: p.hair });
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const ro = new ResizeObserver(() => chart.applyOptions({ width: host.clientWidth }));
    ro.observe(host);

    return () => {
      themeObs.disconnect();
      ro.disconnect();
      chart.remove();
    };
  }, []);

  return <div className="pc-host" ref={hostRef} aria-hidden="true" />;
}
