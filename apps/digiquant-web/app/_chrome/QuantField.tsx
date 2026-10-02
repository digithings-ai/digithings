"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  AXIS_X_MS,
  AXIS_Y_MS,
  AXIS_Y_START_MS,
  BARS_START_MS,
  candleSweepRange,
  CHART_BUILD_MAX_MS,
  COPY_DONE_MS,
  EMA_COLOR,
  EMA_LENGTH,
  GRID_MS,
  GRID_START_MS,
  INDICATOR_START_MS,
  SMA_COLOR,
  SMA_LENGTH,
  heroOverlayInputs,
  paddedPriceWindow,
  revealHiddenPlotFraction,
  revealYDomain,
  type HeroBar,
  type HeroOverlay,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart.
 *
 *  Clock is lib/hero-build.ts, from first paint:
 *  1. Chrome is the wordmark + copy (QuantWordmark / .hero-rise). This component
 *     does not wait on BUILD_DONE_MS.
 *  2. At COPY_DONE_MS, construct strokes: X left→right, right Y bottom→top, then
 *     the grid. Series and volume stay hidden. Not a clip over finished candles.
 *  3. The finished chart is already laid out: full series, locked price and
 *     volume domains, SMA 20, EMA 50, and one overlay. Bars then uncover
 *     left→right. Nothing rescales as a bar appears.
 *  4. The same locked scale carries the indicator lines. They uncover with the
 *     bars. They do not get a second pass that moves the axis.
 *  Reduced motion skips the sweeps. A failed feed still lets chrome finish and
 *  says the chart is unavailable. Hard stop at CHART_BUILD_MAX_MS.
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

const HIDDEN_THEME = { ...THEME, textColor: "transparent", gridColor: "transparent", borderColor: "transparent" };

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

const GRID_H = [1, 2, 3, 4] as const;
const GRID_V = [1, 2, 3, 4, 5] as const;

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
  const price = paddedPriceWindow(revealYDomain(bars, 0, overlay));
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

function lineLength(el: SVGLineElement): number {
  const x1 = Number(el.getAttribute("x1"));
  const y1 = Number(el.getAttribute("y1"));
  const x2 = Number(el.getAttribute("x2"));
  const y2 = Number(el.getAttribute("y2"));
  const len = Math.hypot(x2 - x1, y2 - y1);
  return Number.isFinite(len) && len > 0 ? len : 1;
}

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const coverRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<SVGSVGElement>(null);
  const xRef = useRef<SVGLineElement>(null);
  const yRef = useRef<SVGLineElement>(null);
  const gridRef = useRef<SVGGElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
    const frame = frameRef.current;
    const overlay = overlayRef.current;
    const xLine = xRef.current;
    const yLine = yRef.current;
    const grid = gridRef.current;
    if (!host || !frame || !overlay || !xLine || !yLine || !grid) return;

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
    let replayEnded = false;
    let indicatorDue = false;
    let indicatorStarted = false;
    let hasBars = false;
    let book: HeroBar[] = [];
    const drawingIds: string[] = [];
    let raf = 0;
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    const t0 = performance.now();
    const baseCaption = `LuxAlgo Vela · ${product} · 1m`;
    setCaption(baseCaption);
    frame.dataset.heroBeat = reduced ? "chrome" : "chrome";

    const later = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        if (!dead) fn();
      }, ms);
      timers.push(id);
    };

    const beat = (name: string) => {
      frame.dataset.heroBeat = name;
    };

    const applySafe = (config: unknown) => {
      try {
        chart?.renderer.applyConfig(config);
      } catch {
        /* renderer without rich config — keep going */
      }
    };

    const theme = (next: typeof THEME) => {
      try {
        chart?.renderer.set({ theme: next });
      } catch {
        /* ignore */
      }
    };

    const unavailable = () => {
      setCaption("LuxAlgo Vela · chart unavailable");
      beat("unavailable");
    };

    const clearDrawings = () => {
      const live = chart;
      const ids = drawingIds.filter((id) => id.length > 0);
      drawingIds.length = 0;
      if (!live) return;
      for (const id of ids) {
        try {
          live.drawings.remove(id);
        } catch {
          /* already gone */
        }
      }
    };

    const mountNative = () => {
      if (!chart || nativeOn) return;
      nativeOn = true;
      sma = chart.addNativeIndicator("sma", { inputs: { length: SMA_LENGTH, color: SMA_COLOR } });
      ema = chart.addNativeIndicator("ema", { inputs: { length: EMA_LENGTH, color: EMA_COLOR } });
      overlayInd = chart.addNativeIndicator(picked.type, { inputs: heroOverlayInputs(overlayKind) });
      setCaption(`LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${picked.label}`);
    };

    const revealHost = () => {
      host.style.opacity = "1";
    };

    const showComplete = () => {
      if (dead || finished) return;
      finished = true;
      if (raf) cancelAnimationFrame(raf);
      overlay.dataset.phase = "done";
      revealHost();
      applySafe(CANDLES_VISIBLE);
      theme(THEME);
      if (hasBars || book.length > 0) {
        if (!volumeHandle && chart) {
          try {
            volumeHandle = chart.addNativeIndicator("volume");
          } catch {
            /* volume already mounted */
          }
        }
        clearDrawings();
        mountNative();
        beat("done");
      } else {
        unavailable();
      }
      if (coverRef.current) coverRef.current.style.width = "0px";
      lockFrame(loadedSeries());
      try {
        chart?.replay.stop();
      } catch {
        /* ignore */
      }
      chart?.resize();
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

    /** Cover the plot only. The price scale and time axis stay visible at the locked frame. */
    const paintCover = (elapsed: number, barCount: number) => {
      const cover = coverRef.current;
      if (!cover) return false;
      const hidden = barCount > 1 ? revealHiddenPlotFraction(elapsed, barCount) : 1;
      const rawGutter = getComputedStyle(host).getPropertyValue("--vela-scale-gutter");
      const rawBottom = getComputedStyle(host).getPropertyValue("--vela-bottom-gutter");
      const gutter = Number.parseFloat(rawGutter);
      const bottom = Number.parseFloat(rawBottom);
      const right = Number.isFinite(gutter) && gutter > 0 ? gutter : 56;
      const timeAxis = Number.isFinite(bottom) && bottom > 0 ? bottom : TIME_AXIS_PX;
      const plot = Math.max(0, host.clientWidth - right);
      cover.style.top = "0px";
      cover.style.right = `${right}px`;
      cover.style.bottom = `${timeAxis}px`;
      cover.style.left = "auto";
      cover.style.width = hidden <= 0 ? "0px" : `${hidden * plot}px`;
      return hidden > 0;
    };

    const maybeIndicators = () => {
      if (dead || finished || indicatorStarted) return;
      if (!indicatorDue || !replayEnded) return;
      if (!hasBars && book.length === 0) {
        unavailable();
        finished = true;
        return;
      }
      indicatorStarted = true;
      clearDrawings();
      mountNative();
      lockFrame(loadedSeries());
      finished = true;
      beat(hasBars || book.length > 0 ? "done" : "unavailable");
    };

    const startBars = () => {
      if (!chart || dead || finished || barsStarted) return;
      const rowsNow = loadedSeries();
      if (rowsNow.length < 2) {
        if (hasBars || chart.replay.bounds) later(40, () => startBars());
        return;
      }
      barsStarted = true;
      beat("bars");
      const frozen = rowsNow.map((bar) => ({ ...bar }));
      try {
        if (!volumeHandle) volumeHandle = chart.addNativeIndicator("volume");
        mountNative();
        indicatorStarted = true;
        applySafe(CANDLES_VISIBLE);
        theme(THEME);
        overlay.dataset.phase = "done";
        lockFrame(frozen);
        const started = performance.now();
        const tick = (now: number) => {
          if (dead || finished) return;
          lockFrame(frozen);
          if (paintCover(now - started, frozen.length)) {
            raf = requestAnimationFrame(tick);
            return;
          }
          lockFrame(frozen);
          if (coverRef.current) coverRef.current.style.width = "0px";
          replayEnded = true;
          finished = true;
          beat("done");
          chart?.resize();
        };
        paintCover(0, frozen.length);
        revealHost();
        raf = requestAnimationFrame(tick);
      } catch {
        if (coverRef.current) coverRef.current.style.width = "0px";
        replayEnded = true;
        revealHost();
        applySafe(CANDLES_VISIBLE);
        theme(THEME);
        overlay.dataset.phase = "done";
        maybeIndicators();
      }
    };

    const placeLines = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      if (w < 8 || h < 8) return;
      const raw = getComputedStyle(host).getPropertyValue("--vela-scale-gutter");
      const gutter = Number.parseFloat(raw);
      const right = Math.max(24, w - (Number.isFinite(gutter) && gutter > 0 ? gutter : 56));
      const bottom = Math.max(TIME_AXIS_PX + 8, h - TIME_AXIS_PX);
      overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
      xLine.setAttribute("x1", "0");
      xLine.setAttribute("y1", String(bottom));
      xLine.setAttribute("x2", String(right));
      xLine.setAttribute("y2", String(bottom));
      yLine.setAttribute("x1", String(right));
      yLine.setAttribute("y1", String(bottom));
      yLine.setAttribute("x2", String(right));
      yLine.setAttribute("y2", "1");
      const hs = grid.querySelectorAll<SVGLineElement>('[data-g="h"]');
      const vs = grid.querySelectorAll<SVGLineElement>('[data-g="v"]');
      hs.forEach((line, i) => {
        const y = ((i + 1) / (hs.length + 1)) * bottom;
        line.setAttribute("x1", "0");
        line.setAttribute("x2", String(right));
        line.setAttribute("y1", String(y));
        line.setAttribute("y2", String(y));
      });
      vs.forEach((line, i) => {
        const x = ((i + 1) / (vs.length + 1)) * right;
        line.setAttribute("x1", String(x));
        line.setAttribute("x2", String(x));
        line.setAttribute("y1", "0");
        line.setAttribute("y2", String(bottom));
      });
    };

    const growLine = (el: SVGLineElement, ms: number) => {
      const len = lineLength(el);
      el.style.strokeWidth = "1.25";
      el.style.transition = "none";
      el.style.strokeDasharray = `${len}`;
      el.style.strokeDashoffset = `${len}`;
      requestAnimationFrame(() => {
        if (dead || finished) return;
        el.style.transition = `stroke-dashoffset ${ms}ms cubic-bezier(0.22, 1, 0.36, 1)`;
        el.style.strokeDashoffset = "0";
      });
    };

    const runAxes = () => {
      if (dead || finished || reduced) return;
      beat("axes");
      placeLines();
      applySafe(CANDLES_HIDDEN);
      theme(HIDDEN_THEME);
      overlay.dataset.phase = "x";
      grid.style.opacity = "0";
      growLine(xLine, AXIS_X_MS);
      later(AXIS_Y_START_MS, () => {
        if (finished) return;
        overlay.dataset.phase = "xy";
        growLine(yLine, AXIS_Y_MS);
      });
      later(GRID_START_MS, () => {
        if (finished) return;
        overlay.dataset.phase = "grid";
        grid.style.transition = `opacity ${GRID_MS}ms ease`;
        grid.style.opacity = "1";
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
        theme: reduced ? THEME : HIDDEN_THEME,
        upColor: UP,
        downColor: DOWN,
        volume: reduced,
        drawings: false,
        animations: reduced
          ? false
          : { intro: false, zoom: true, pan: true, autoscale: false },
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
      chart.resize();
      // Axes already draw from their own placeLines. A late ready() must not
      // move the strokes under an in-flight dashoffset.
      if (frame.dataset.heroBeat === "chrome") placeLines();

      if (reduced) {
        revealHost();
        applySafe(CANDLES_VISIBLE);
        theme(THEME);
        if (hasBars) mountNative();
        else unavailable();
        overlay.dataset.phase = "done";
        finished = true;
        beat(hasBars ? "done" : "unavailable");
        return;
      }

      if (performance.now() - t0 >= COPY_DONE_MS + BARS_START_MS) startBars();
    };

    if (reduced) {
      overlay.dataset.phase = "done";
      revealHost();
    } else {
      host.style.opacity = "0";
      overlay.dataset.phase = "armed";
    }

    void mountChart().catch(() => {
      if (!dead) unavailable();
    });

    if (!reduced) {
      later(COPY_DONE_MS, () => runAxes());
      later(COPY_DONE_MS + BARS_START_MS, () => startBars());
      later(COPY_DONE_MS + BARS_START_MS + INDICATOR_START_MS, () => {
        indicatorDue = true;
        maybeIndicators();
      });
    }

    later(CHART_BUILD_MAX_MS, () => {
      if (!hasBars && book.length === 0) unavailable();
      showComplete();
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
      clearDrawings();
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
          className="absolute inset-0 h-full w-full opacity-0 [transform:translateZ(0)]"
        />
        <svg
          ref={overlayRef}
          className="hero-construct"
          data-phase="armed"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          <g ref={gridRef} className="hero-construct__grid" style={{ opacity: 0 }}>
            {GRID_H.map((n) => (
              <line key={`h${n}`} data-g="h" />
            ))}
            {GRID_V.map((n) => (
              <line key={`v${n}`} data-g="v" />
            ))}
          </g>
          <line ref={xRef} className="hero-construct__x" />
          <line ref={yRef} className="hero-construct__y" />
        </svg>
        <div
          ref={coverRef}
          aria-hidden
          className="pointer-events-none absolute top-0 z-20"
          style={{ width: 0, right: 56, bottom: TIME_AXIS_PX, background: "var(--bg)" }}
        />
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
