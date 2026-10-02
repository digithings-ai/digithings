"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  AXIS_Y_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_BUILD_MAX_MS,
  COPY_DONE_MS,
  EMA_COLOR,
  EMA_LENGTH,
  SMA_COLOR,
  SMA_LENGTH,
  VOLUME_LAG_MS,
  candleSweepRange,
  heroAxisFrame,
  heroIndicatorStrokes,
  heroOverlayInputs,
  paddedPriceWindow,
  revealStroke,
  revealYDomain,
  staggerReveal,
  type HeroBar,
  type HeroOverlay,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: one LuxAlgo Vela chart.
 *
 *  Price and volume windows come from the full series and are locked before
 *  the frame is shown. The time axis appears and stays. The price scale
 *  uncovers shortly after. Candles, then indicators, then volume travel left
 *  to right on that same frame. Reduced motion shows the finished chart
 *  immediately. A failed feed still leaves the chrome and says the chart is
 *  unavailable.
 *
 *  Wheel: zoom-out while the gesture is live; after settle or the zoom-out
 *  budget, the next wheel scrolls the page. Horizontal / shift stays on the chart. */

const UP = "#3DFF9A";
const DOWN = "#FF5C6C";
const CYCLE = [
  { type: "bollinger-bands", label: "Bollinger" },
  { type: "vwap", label: "VWAP" },
  { type: "supertrend", label: "SuperTrend" },
] as const;

const THEME = {
  background: "#000000",
  textColor: "#d7dde4",
  gridColor: "#1a1f24",
  borderColor: "#2a3138",
  upColor: UP,
  downColor: DOWN,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

const WHEEL_IDLE_MS = 140;
const ZOOM_OUT_BUDGET = 720;
const TIME_AXIS_PX = 22;
const BAR_MS = 60_000;

const CANDLES_HIDDEN = {
  candles: { bodyVisible: false, wickVisible: false, borderVisible: false },
  grid: { vertLines: { visible: false }, horzLines: { visible: false } },
  priceScale: { labelsVisible: false },
} as const;

const CANDLES_VISIBLE = {
  candles: { bodyVisible: true, wickVisible: true, borderVisible: true },
  grid: { vertLines: { visible: true }, horzLines: { visible: true } },
  priceScale: { labelsVisible: true },
} as const;

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
  const coverRef = useRef<HTMLDivElement>(null);
  const yCoverRef = useRef<HTMLDivElement>(null);
  const revealRef = useRef<SVGSVGElement>(null);
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
    let volumeHandle: IndicatorHandle | null = null;
    let finished = false;
    let nativeOn = false;
    let barsStarted = false;
    let frameOn = false;
    let yOn = false;
    let hasBars = false;
    let book: HeroBar[] = [];
    let axisFrozen: HeroBar[] = [];
    let raf = 0;
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    const t0 = performance.now();
    setCaption(`LuxAlgo Vela · ${product} · 1m`);
    beat("chrome");
    host.style.transition = "none";
    if (!reduced) host.style.opacity = "0";

    const later = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        if (!dead) fn();
      }, ms);
      timers.push(id);
    };

    function beat(name: string) {
      frame!.dataset.heroBeat = name;
    }

    const applySafe = (config: unknown) => {
      try {
        chart?.renderer.applyConfig(config);
      } catch {
        /* renderer without rich config */
      }
    };

    const unavailable = () => {
      setCaption("LuxAlgo Vela · chart unavailable");
      beat("unavailable");
      host.style.opacity = "1";
    };

    const mountNative = () => {
      if (!chart || nativeOn) return;
      nativeOn = true;
      sma = chart.addNativeIndicator("sma", { inputs: { length: SMA_LENGTH, color: SMA_COLOR } });
      ema = chart.addNativeIndicator("ema", { inputs: { length: EMA_LENGTH, color: EMA_COLOR } });
      overlayInd = chart.addNativeIndicator(picked.type, { inputs: heroOverlayInputs(overlayKind) });
      setCaption(`LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${picked.label}`);
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

    const plotBox = () => {
      const rawGutter = getComputedStyle(host).getPropertyValue("--vela-scale-gutter");
      const rawBottom = getComputedStyle(host).getPropertyValue("--vela-bottom-gutter");
      const gutter = Number.parseFloat(rawGutter);
      const bottom = Number.parseFloat(rawBottom);
      const right = Number.isFinite(gutter) && gutter > 0 ? gutter : 56;
      const timeAxis = Number.isFinite(bottom) && bottom > 0 ? bottom : TIME_AXIS_PX;
      const plot = Math.max(0, host.clientWidth - right);
      const plotH = Math.max(0, host.clientHeight - timeAxis);
      return { right, timeAxis, plot, plotH };
    };

    const paintCover = (shown: number, barCount: number) => {
      const cover = coverRef.current;
      if (!cover) return;
      const hidden = barCount > 1 && shown < barCount ? 1 - shown / barCount : shown >= barCount ? 0 : 1;
      const { right, timeAxis, plot } = plotBox();
      cover.style.top = "0px";
      cover.style.right = `${right}px`;
      cover.style.bottom = `${timeAxis}px`;
      cover.style.left = "auto";
      cover.style.width = hidden <= 0 ? "0px" : `${hidden * plot}px`;
    };

    const sizeYCover = (open: boolean) => {
      const yCover = yCoverRef.current;
      if (!yCover) return;
      const { right, timeAxis } = plotBox();
      yCover.style.top = "0px";
      yCover.style.right = "0px";
      yCover.style.bottom = `${timeAxis}px`;
      yCover.style.width = open ? "0px" : `${Math.max(right + 8, 80)}px`;
    };

    const stampAxis = (elapsedMs: number) => {
      const next = heroAxisFrame(elapsedMs);
      if (next === "off") return;
      frame.dataset.axisFrame = next;
    };

    const revealPriceAxis = () => {
      yOn = true;
      sizeYCover(true);
      if (frameOn) stampAxis(barsStarted ? BARS_START_MS : AXIS_Y_START_MS);
    };

    const startBars = () => {
      if (!chart || dead || finished || barsStarted) return;
      if (!frameOn && !presentFrame()) {
        if (hasBars || book.length > 0 || chart.replay.bounds) later(40, () => startBars());
        return;
      }
      if (axisFrozen.length < 2) return;
      if (!yOn && performance.now() - t0 >= COPY_DONE_MS + AXIS_Y_START_MS) revealPriceAxis();
      barsStarted = true;
      beat("bars");
      stampAxis(BARS_START_MS);
      if (raf) cancelAnimationFrame(raf);
      const frozen = axisFrozen;
      const strokes = heroIndicatorStrokes(frozen, overlayKind);
      const timeIndex = new Map(frozen.map((bar, index) => [bar.time, index]));
      const price = paddedPriceWindow(revealYDomain(frozen, frozen.length, overlayKind));
      const volumeMax = revealYDomain(frozen, frozen.length, overlayKind).volumeMax;
      const svg = revealRef.current;
      if (svg) svg.style.display = "";
      const paintLayers = (counts: { candles: number; indicators: number; volume: number }) => {
        frame.dataset.revealCandles = String(counts.candles);
        frame.dataset.revealIndicators = String(counts.indicators);
        frame.dataset.revealVolume = String(counts.volume);
        const { plot, plotH } = plotBox();
        paintCover(counts.candles, frozen.length);
        if (!svg || plot < 8 || plotH < 8) return;
        svg.style.width = `${plot}px`;
        svg.style.height = `${plotH}px`;
        svg.setAttribute("viewBox", `0 0 ${plot} ${plotH}`);
        svg.replaceChildren();
        const span = price.max - price.min || 1;
        const ns = "http://www.w3.org/2000/svg";
        if (counts.indicators >= 2) {
          for (const stroke of strokes) {
            const points = revealStroke(stroke, frozen, counts.indicators - 1);
            if (points.length < 2) continue;
            const d = points
              .map((point, k) => {
                const index = timeIndex.get(point.time) ?? 0;
                const x = ((index + 0.5) / frozen.length) * plot;
                const y = ((price.max - point.price) / span) * plotH;
                return `${k === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
              })
              .join(" ");
            const path = document.createElementNS(ns, "path");
            path.setAttribute("d", d);
            path.setAttribute("fill", "none");
            path.setAttribute("stroke", stroke.color);
            path.setAttribute("stroke-width", "1.5");
            svg.appendChild(path);
          }
        }
        const band = plotH * 0.2;
        const barW = Math.max(1, (plot / frozen.length) * 0.62);
        for (let i = 0; i < counts.volume; i++) {
          const bar = frozen[i];
          const vol = bar?.volume ?? 0;
          if (!bar || !(vol > 0) || !(volumeMax > 0)) continue;
          const h = Math.max(1, (vol / volumeMax) * band);
          const rect = document.createElementNS(ns, "rect");
          rect.setAttribute("x", String(((i + 0.5) / frozen.length) * plot - barW / 2));
          rect.setAttribute("y", String(plotH - h));
          rect.setAttribute("width", String(barW));
          rect.setAttribute("height", String(h));
          rect.setAttribute("fill", bar.close >= bar.open ? UP : DOWN);
          rect.setAttribute("opacity", "0.55");
          svg.appendChild(rect);
        }
      };
      let elapsed = 0;
      let lastTick = performance.now();
      const total = VOLUME_LAG_MS + BARS_SWEEP_MS;
      const tick = (now: number) => {
        if (dead || finished) return;
        elapsed += Math.min(48, Math.max(0, now - lastTick));
        lastTick = now;
        lockFrame(frozen);
        const counts = staggerReveal(elapsed, frozen.length);
        paintLayers(counts);
        if (elapsed < total) {
          raf = requestAnimationFrame(tick);
          return;
        }
        if (svg) {
          svg.replaceChildren();
          svg.style.display = "none";
        }
        if (chart && !volumeHandle) volumeHandle = chart.addNativeIndicator("volume");
        mountNative();
        lockFrame(frozen);
        paintCover(frozen.length, frozen.length);
        finished = true;
        beat("done");
      };
      lockFrame(frozen);
      paintLayers(staggerReveal(0, frozen.length));
      raf = requestAnimationFrame(tick);
    };

    const presentFrame = (): boolean => {
      if (!chart || frameOn || dead || finished) return frameOn;
      const rowsNow = loadedSeries();
      if (rowsNow.length < 2) return false;
      axisFrozen = rowsNow.map((bar) => ({ ...bar }));
      applySafe(CANDLES_VISIBLE);
      try {
        chart.resize();
      } catch {
        /* layout not ready */
      }
      lockFrame(axisFrozen);
      paintCover(0, axisFrozen.length);
      sizeYCover(yOn);
      host.style.opacity = "1";
      frameOn = true;
      stampAxis(yOn ? AXIS_Y_START_MS : 0);
      const hold = () => {
        if (dead || finished || barsStarted) return;
        lockFrame(axisFrozen);
        raf = requestAnimationFrame(hold);
      };
      raf = requestAnimationFrame(hold);
      return true;
    };

    const runAxes = () => {
      if (dead || finished || reduced) return;
      beat("axes");
      const tryPresent = () => {
        if (dead || finished || frameOn) return;
        if (!presentFrame()) later(40, tryPresent);
      };
      tryPresent();
      later(AXIS_Y_START_MS, () => {
        if (finished) return;
        revealPriceAxis();
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
        volume: reduced,
        drawings: false,
        animations: reduced ? false : { intro: false, zoom: true, pan: true, autoscale: false },
      });
      host.style.touchAction = "pan-y";
      chart.data.registerProvider("coinbase", new CoinbaseProvider());
      if (!reduced) applySafe(CANDLES_HIDDEN);
      const source = chart.data.providerInstance("coinbase") as BarSource | undefined;
      if (source && typeof source.getBars === "function") {
        void source
          .getBars(product, "1", { limit: 300 })
          .then((rows) => {
            if (!dead) book = asBars(rows);
          })
          .catch(() => undefined);
      }
      chart.on("load:end", (ev) => {
        if (dead) return;
        hasBars = (ev?.bars ?? 0) > 0;
        if (!hasBars) unavailable();
        else if (!barsStarted && performance.now() - t0 >= COPY_DONE_MS + BARS_START_MS) startBars();
      });
      await chart.ready().catch(() => undefined);
      if (dead) return;
      hasBars = hasBars || Boolean(chart.replay.bounds);
      try {
        chart.resize();
      } catch {
        /* layout not ready */
      }
      if (reduced) {
        host.style.opacity = "1";
        applySafe(CANDLES_VISIBLE);
        if (hasBars || book.length > 0) {
          try {
            volumeHandle = chart.addNativeIndicator("volume");
          } catch {
            /* volume already mounted */
          }
          mountNative();
          lockFrame(loadedSeries());
          beat("done");
        } else unavailable();
        finished = true;
        return;
      }
      if (performance.now() - t0 >= COPY_DONE_MS + BARS_START_MS) startBars();
      else if (performance.now() - t0 >= COPY_DONE_MS) runAxes();
    };

    void mountChart().catch(() => {
      if (!dead) unavailable();
    });

    if (!reduced) {
      later(COPY_DONE_MS, () => runAxes());
      later(COPY_DONE_MS + BARS_START_MS, () => startBars());
    }

    later(CHART_BUILD_MAX_MS, () => {
      if (finished) return;
      if (!hasBars && book.length === 0 && axisFrozen.length < 2) {
        unavailable();
        finished = true;
        return;
      }
      if (!frameOn) presentFrame();
      revealPriceAxis();
      if (!barsStarted) startBars();
    });

    return () => {
      dead = true;
      if (raf) cancelAnimationFrame(raf);
      if (idleTimer) clearTimeout(idleTimer);
      for (const id of timers) clearTimeout(id);
      host.removeEventListener("wheel", onWheelCapture, { capture: true });
      try {
        chart?.replay.stop();
      } catch {
        /* ignore */
      }
      overlayInd?.remove();
      sma?.remove();
      ema?.remove();
      volumeHandle?.remove();
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
        <div
          ref={coverRef}
          aria-hidden
          className="pointer-events-none absolute top-0 z-20"
          style={{ width: 0, right: 56, bottom: TIME_AXIS_PX, background: "var(--bg, #000)" }}
        />
        <div
          ref={yCoverRef}
          aria-hidden
          className="pointer-events-none absolute top-0 right-0 z-20"
          style={{ width: 0, bottom: TIME_AXIS_PX, background: "var(--bg, #000)" }}
        />
        <svg
          ref={revealRef}
          aria-hidden
          className="pointer-events-none absolute top-0 left-0 z-30"
          style={{ display: "none" }}
        />
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">
        {caption}
      </p>
    </>
  );
}
