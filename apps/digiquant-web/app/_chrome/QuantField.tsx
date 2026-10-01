"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import { BUILD_DONE_MS } from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart (the library, not a boxed highlight).
 *
 *  A random BTC, ETH or SOL product loads from Vela's Coinbase provider. Candles
 *  use the bright up/down inks; volume and two moving averages stay on; one more
 *  native overlay (Bollinger, VWAP, SuperTrend) cycles. Reduced motion skips the
 *  intro sweep and the cycle. The wordmark still builds on its own clock; the
 *  chart's intro lasts the same span (`BUILD_DONE_MS`). */

const UP = "#3DFF9A";
const DOWN = "#FF5C6C";
const CYCLE = [
  { type: "bollinger-bands", label: "Bollinger" },
  { type: "vwap", label: "VWAP" },
  { type: "supertrend", label: "SuperTrend" },
] as const;
const CYCLE_MS = 8000;

const THEME = {
  background: "#000000",
  textColor: "#d7dde4",
  gridColor: "#1a1f24",
  borderColor: "#2a3138",
  upColor: UP,
  downColor: DOWN,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const product = HERO_PRODUCTS[Math.floor(Math.random() * HERO_PRODUCTS.length)] ?? HERO_PRODUCTS[0];
    let dead = false;
    let chart: Vela | null = null;
    let timer = 0;
    let overlay: IndicatorHandle | null = null;
    let step = 0;

    const label = (name: string) =>
      `LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${name}`;

    void (async () => {
      const [{ Vela: VelaChart }, { CoinbaseProvider }] = await Promise.all([
        import("@luxalgo/vela"),
        import("@luxalgo/vela/providers/coinbase"),
      ]);
      if (dead) return;
      chart = new VelaChart(host, {
        symbol: `coinbase:${product}`,
        timeframe: "1",
        bars: 300,
        live: !reduced,
        theme: THEME,
        upColor: UP,
        downColor: DOWN,
        volume: true,
        drawings: false,
        animations: reduced ? false : { intro: { style: "grow", duration: BUILD_DONE_MS } },
      });
      chart.data.registerProvider("coinbase", new CoinbaseProvider());
      chart.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
      chart.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
      const first = CYCLE[0];
      overlay = chart.addNativeIndicator(first.type);
      setCaption(label(first.label));
      if (reduced) return;
      timer = window.setInterval(() => {
        overlay?.remove();
        step = (step + 1) % CYCLE.length;
        const next = CYCLE[step] ?? first;
        overlay = chart?.addNativeIndicator(next.type) ?? null;
        setCaption(label(next.label));
      }, CYCLE_MS);
    })().catch(() => {
      if (!dead) setCaption("LuxAlgo Vela · chart unavailable");
    });

    return () => {
      dead = true;
      window.clearInterval(timer);
      chart?.destroy();
    };
  }, []);

  return (
    <>
      <div ref={ref} aria-label={caption} className="absolute inset-0 -z-10 h-full w-full [transform:translateZ(0)]" />
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
