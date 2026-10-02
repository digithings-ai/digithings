"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  CHART_BUILD_MAX_MS,
  HERO_FADE_MS,
  candleSweepRange,
  heroOverlayInputs,
  paddedPriceWindow,
  revealYDomain,
  EMA_COLOR,
  EMA_LENGTH,
  SMA_COLOR,
  SMA_LENGTH,
  type HeroBar,
  type HeroOverlay,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: one finished LuxAlgo Vela chart, faded in.
 *
 *  Vela owns the axes for the whole life of the chart. There is no SVG axis
 *  stroke and no left-to-right reveal — those unmounted the frame and let
 *  Vela autoscale a second time. The price window is the full series, locked
 *  before the fade. Reduced motion shows the chart immediately. A failed feed
 *  still leaves the chrome up and says the chart is unavailable.
 *
 *  Wheel: zoom-out while the gesture is live; after settle or the zoom-out
 *  budget, the next wheel scrolls the page. Horizontal / shift stays on the chart. */

const UP = "#3DFF9A"; // canon-allow: hero candle up
const DOWN = "#FF5C6C"; // canon-allow: hero candle down
const CYCLE = [
  { type: "bollinger-bands", label: "Bollinger" },
  { type: "vwap", label: "VWAP" },
  { type: "supertrend", label: "SuperTrend" },
] as const;

const THEME = {
  background: "#000000",
  textColor: "#d7dde4", // canon-allow: hero axis text
  gridColor: "#1a1f24", // canon-allow: hero grid
  borderColor: "#2a3138", // canon-allow: hero frame
  upColor: UP,
  downColor: DOWN,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

const WHEEL_IDLE_MS = 140;
const ZOOM_OUT_BUDGET = 720;
const BAR_MS = 60_000;

type BarSource = {
  getBars: (ticker: string, timeframe: string, range: { limit?: number }) => Promise<unknown>;
};

function asBars(rows: unknown): HeroBar[] {
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

type PricePane = {
  kind?: string;
  manualScale: { min: number; max: number } | null;
  scale: { min: number; max: number };
  scaleTarget: { min: number; max: number };
};

/** Freeze the price pane on the full-series window. Autoscale copies the visible prefix. */
function applyLockedDomain(chart: Vela, bars: readonly HeroBar[], overlay: HeroOverlay) {
  const price = paddedPriceWindow(revealYDomain(bars, bars.length, overlay));
  const control = chart.renderer as unknown as {
    renderer?: {
      scene?: { panes?: { values: () => Iterable<PricePane> } };
      scheduler?: { invalidate: (tier: number) => void };
    };
    set: (feature: Record<string, unknown>) => void;
  };
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

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
    const frame = frameRef.current;
    if (!host || !frame) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const product = HERO_PRODUCTS[Math.floor(Math.random() * HERO_PRODUCTS.length)] ?? HERO_PRODUCTS[0];
    const picked = CYCLE[Math.floor(Math.random() * CYCLE.length)] ?? CYCLE[0];
    const overlayKind = picked.type as HeroOverlay;
    let dead = false;
    let chart: Vela | null = null;
    let overlayInd: IndicatorHandle | null = null;
    let sma: IndicatorHandle | null = null;
    let ema: IndicatorHandle | null = null;
    let shown = false;
    let hasBars = false;
    let book: HeroBar[] = [];
    const timers: Array<ReturnType<typeof setTimeout>> = [];

    const later = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        if (!dead) fn();
      }, ms);
      timers.push(id);
    };

    const beat = (name: string) => {
      frame.dataset.heroBeat = name;
    };

    setCaption(`LuxAlgo Vela · ${product} · 1m`);
    beat("chrome");
    host.style.transition = reduced ? "none" : `opacity ${HERO_FADE_MS}ms ease`;
    if (reduced) host.style.opacity = "1";

    const unavailable = () => {
      setCaption("LuxAlgo Vela · chart unavailable");
      beat("unavailable");
      host.style.opacity = "1";
    };

    const loadedSeries = (): HeroBar[] => {
      const native = (chart?.renderer as unknown as { renderer?: { bars?: unknown } } | null)?.renderer;
      const fromChart = asBars(native?.bars);
      if (fromChart.length >= 2) return fromChart;
      return book;
    };

    const lockFrame = (rows: readonly HeroBar[]) => {
      if (!chart || rows.length < 2) return;
      try {
        chart.setVisibleRange(candleSweepRange(rows[0].time, rows[rows.length - 1].time, BAR_MS));
      } catch {
        /* renderer without range control */
      }
      applyLockedDomain(chart, rows, overlayKind);
    };

    const mountStudies = () => {
      if (!chart || sma) return;
      sma = chart.addNativeIndicator("sma", { inputs: { length: SMA_LENGTH, color: SMA_COLOR } });
      ema = chart.addNativeIndicator("ema", { inputs: { length: EMA_LENGTH, color: EMA_COLOR } });
      overlayInd = chart.addNativeIndicator(picked.type, { inputs: heroOverlayInputs(overlayKind) });
      setCaption(`LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${picked.label}`);
    };

    const fadeIn = () => {
      if (dead || shown) return;
      const rows = loadedSeries();
      if (rows.length < 2 && !hasBars) return;
      shown = true;
      mountStudies();
      lockFrame(rows);
      chart?.resize();
      lockFrame(loadedSeries());
      if (reduced) {
        host.style.opacity = "1";
        beat("done");
        return;
      }
      // Opacity must be painted at 0 or the transition is skipped and the
      // chart pops in. Two frames let Vela draw the finished canvas first.
      host.style.opacity = "0";
      requestAnimationFrame(() => {
        if (dead) return;
        requestAnimationFrame(() => {
          if (dead) return;
          host.style.opacity = "1";
          beat("done");
        });
      });
    };

    let pageUnlocked = false;
    let zoomOutUsed = 0;
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    const atPageTop = () => window.scrollY <= 1;

    const onWheelCapture = (e: WheelEvent) => {
      if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;

      if (pageUnlocked) {
        if (atPageTop() && e.deltaY < 0) {
          pageUnlocked = false;
          zoomOutUsed = 0;
          return;
        }
        e.stopImmediatePropagation();
        return;
      }

      if (!atPageTop()) {
        pageUnlocked = true;
        e.stopImmediatePropagation();
        return;
      }

      if (e.deltaY > 0) {
        zoomOutUsed += e.deltaY;
        if (zoomOutUsed >= ZOOM_OUT_BUDGET) {
          pageUnlocked = true;
          e.stopImmediatePropagation();
          return;
        }
      }

      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        idleTimer = null;
        if (!dead && atPageTop() && zoomOutUsed > 0) pageUnlocked = true;
      }, WHEEL_IDLE_MS);
    };

    host.addEventListener("wheel", onWheelCapture, { capture: true, passive: true });

    const mountChart = async () => {
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
        animations: reduced
          ? false
          : { intro: false, zoom: true, pan: true, autoscale: false },
      });
      host.style.touchAction = "pan-y";
      chart.data.registerProvider("coinbase", new CoinbaseProvider());

      const source = chart.data.providerInstance("coinbase") as BarSource | undefined;
      if (source && typeof source.getBars === "function") {
        void source
          .getBars(product, "1", { limit: 300 })
          .then((rows) => {
            if (dead) return;
            book = asBars(rows);
            fadeIn();
          })
          .catch(() => undefined);
      }

      chart.on("load:end", (ev) => {
        if (dead) return;
        hasBars = (ev?.bars ?? 0) > 0;
        if (!hasBars) unavailable();
        else fadeIn();
      });

      await chart.ready().catch(() => undefined);
      if (dead) return;
      hasBars = hasBars || Boolean(chart.replay.bounds);
      chart.resize();
      if (hasBars) fadeIn();
      else if (reduced) unavailable();
    };

    void mountChart().catch(() => {
      if (!dead) unavailable();
    });

    later(CHART_BUILD_MAX_MS, () => {
      if (shown) return;
      if (!hasBars && book.length === 0) unavailable();
      else fadeIn();
    });

    return () => {
      dead = true;
      if (idleTimer) clearTimeout(idleTimer);
      for (const id of timers) clearTimeout(id);
      host.removeEventListener("wheel", onWheelCapture, { capture: true });
      overlayInd?.remove();
      sma?.remove();
      ema?.remove();
      chart?.destroy();
    };
  }, []);

  return (
    <>
      <div ref={frameRef} data-hero-beat="chrome" className="absolute inset-0 -z-10 h-full min-h-full w-full">
        <div
          ref={ref}
          aria-label={caption}
          className="hero-chart absolute inset-0 h-full w-full [transform:translateZ(0)]"
        />
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">
        {caption}
      </p>
    </>
  );
}
