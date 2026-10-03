"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import { readDigiquantChartScale } from "@digithings/ui/chart-scale";
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
import { heroWatermark, HERO_HOLD_MS, loadHeroSeries, nextHero, type HeroSeries } from "@/lib/live/hero-series";

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
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

const WHEEL_IDLE_MS = 140;
const ZOOM_OUT_BUDGET = 720;
const BAR_MS = 60_000;
const DAY_MS = 86_400_000;

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

function velaBars(bars: readonly HeroBar[]) {
  return bars.map((bar) => ({
    time: bar.time,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    ...(bar.volume === undefined ? {} : { volume: bar.volume }),
  }));
}

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [watermark, setWatermark] = useState("");

  useEffect(() => {
    const host = ref.current;
    const frame = frameRef.current;
    if (!host || !frame) return;

    const scale = readDigiquantChartScale(host);
    const theme = { ...THEME, upColor: scale.candleUp, downColor: scale.candleDown };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
    let barMs = BAR_MS;
    let flight: AbortController | null = null;
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

    beat("chrome");
    host.style.transition = reduced ? "none" : `opacity ${HERO_FADE_MS}ms ease`;
    if (reduced) host.style.opacity = "1";

    const unavailable = () => {
      setWatermark("");
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
        chart.setVisibleRange(candleSweepRange(rows[0].time, rows[rows.length - 1].time, barMs));
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

    const chartOptions = (series: HeroSeries) => {
      const motion = reduced ? false : { intro: false, zoom: true, pan: true, autoscale: false };
      const colors = {
        theme,
        upColor: scale.candleUp,
        downColor: scale.candleDown,
        volume: false as const,
        drawings: false as const,
        animations: motion,
      };
      if (series.source === "coinbase") {
        return {
          ...colors,
          symbol: `coinbase:${series.symbol}`,
          timeframe: series.velaTimeframe,
          bars: 300,
          live: !reduced,
        };
      }
      return {
        ...colors,
        symbol: series.symbol,
        timeframe: series.velaTimeframe,
        live: false as const,
        data: velaBars(series.bars),
      };
    };

    const paint = async (series: HeroSeries) => {
      book = series.bars;
      barMs = series.velaTimeframe === "1" ? BAR_MS : DAY_MS;
      setWatermark(heroWatermark(series.symbol, series.timeframe));
      if (!chart) {
        const [{ Vela: VelaChart }, { CoinbaseProvider }] = await Promise.all([
          import("@luxalgo/vela"),
          import("@luxalgo/vela/providers/coinbase"),
        ]);
        if (dead) return;
        chart = new VelaChart(host, chartOptions(series));
        chart.addNativeIndicator("volume", {
          inputs: { upColor: scale.volumeUp, downColor: scale.volumeDown },
        });
        host.style.touchAction = "pan-y";
        chart.data.registerProvider("coinbase", new CoinbaseProvider());
        chart.on("load:end", (ev) => {
          if (dead) return;
          hasBars = (ev?.bars ?? 0) > 0 || book.length >= 2;
          if (hasBars) fadeIn();
        });
        await chart.ready().catch(() => undefined);
      } else if (series.source === "coinbase") {
        await chart.setMarket({ symbol: `coinbase:${series.symbol}`, timeframe: "1" });
      } else {
        await chart.setMarket({
          symbol: series.symbol,
          timeframe: "D",
          data: velaBars(series.bars),
        });
      }
      if (dead || !chart) return;
      hasBars = true;
      chart.resize();
      fadeIn();
      lockFrame(loadedSeries());
    };

    const missed = new Set<string>();
    const load = (symbol: string, signal?: AbortSignal) => {
      if (missed.has(symbol)) return Promise.resolve(null);
      return loadHeroSeries(symbol, signal).then((series) => {
        if (!series) missed.add(symbol);
        return series;
      });
    };

    const step = async (start: number) => {
      flight?.abort();
      const controller = new AbortController();
      flight = controller;
      try {
        const found = await nextHero(start, load, controller.signal);
        if (dead || controller.signal.aborted) return;
        if (!found) {
          unavailable();
          return;
        }
        await paint(found.series);
        if (dead || controller.signal.aborted) return;
        later(HERO_HOLD_MS, () => {
          void step(found.index + 1);
        });
      } catch (err) {
        if (dead || (err instanceof DOMException && err.name === "AbortError")) return;
        unavailable();
      }
    };

    void step(0);

    later(CHART_BUILD_MAX_MS, () => {
      if (shown) return;
      if (!hasBars && book.length === 0) unavailable();
      else fadeIn();
    });

    return () => {
      dead = true;
      flight?.abort();
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
          aria-label={watermark || "price chart"}
          className="hero-chart absolute inset-0 h-full w-full [transform:translateZ(0)]"
        />
        {watermark ? (
          <p
            data-hero-watermark=""
            aria-hidden="true"
            className="pointer-events-none absolute bottom-[14%] left-1/2 z-10 m-0 -translate-x-1/2 font-mono text-[clamp(1.35rem,3vw,2.25rem)] tracking-[0.12em] text-ink opacity-40"
          >
            {watermark}
          </p>
        ) : null}
      </div>
    </>
  );
}
