"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  AXIS_X_MS,
  AXIS_Y_MS,
  AXIS_Y_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_BUILD_MAX_MS,
  COPY_DONE_MS,
  EMA_COLOR,
  EMA_LENGTH,
  GRID_MS,
  GRID_START_MS,
  INDICATOR_START_MS,
  INDICATOR_SWEEP_MS,
  SMA_COLOR,
  SMA_LENGTH,
  heroIndicatorStrokes,
  heroOverlayInputs,
  revealStroke,
  type HeroBar,
  type HeroOverlay,
  type HeroStroke,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart.
 *
 *  Clock is lib/hero-build.ts, from first paint:
 *  1. Chrome is the wordmark + copy (QuantWordmark / .hero-rise). This component
 *     does not wait on BUILD_DONE_MS.
 *  2. At COPY_DONE_MS, construct strokes: X left→right, right Y bottom→top, then
 *     the grid. Series and volume stay hidden. Not a clip over finished candles.
 *  3. Candles and volume then sweep left→right together (replay; bar i's volume
 *     is added with bar i).
 *  4. SMA 20, EMA 50, and one overlay travel left→right after that sweep, then
 *     hand off to the same native studies.
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
      try {
        chart?.replay.stop();
      } catch {
        /* ignore */
      }
      chart?.resize();
    };

    const paintIndicators = (strokes: HeroStroke[], index: number) => {
      if (!chart) return;
      let visible = false;
      strokes.forEach((stroke, slot) => {
        const points = revealStroke(stroke, book, index);
        if (points.length < 2) return;
        visible = true;
        const anchors = points.map((point) => ({ time: point.time, price: point.price }));
        const existing = drawingIds[slot];
        if (!existing) {
          const drawn = chart?.drawings.add("polyline", {
            anchors,
            style: { lineColor: stroke.color, lineWidth: 2, lineStyle: "solid" },
          });
          if (drawn) {
            drawingIds[slot] = drawn.id;
            try {
              chart?.drawings.lock(drawn.id, true);
            } catch {
              /* lock is cosmetic */
            }
          }
          return;
        }
        try {
          chart?.drawings.update(existing, { anchors });
        } catch {
          /* one missed frame — the next tick retries */
        }
      });
      if (visible) {
        setCaption(`LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${picked.label}`);
      }
    };

    const runIndicatorSweep = () => {
      if (dead || finished || indicatorStarted) return;
      indicatorStarted = true;
      beat("indicators");
      if (book.length < 2 || !chart) {
        clearDrawings();
        mountNative();
        finished = true;
        beat(hasBars ? "done" : "unavailable");
        return;
      }
      const strokes = heroIndicatorStrokes(book, overlayKind);
      const elapsed = performance.now() - t0;
      const room = CHART_BUILD_MAX_MS - elapsed - 40;
      const duration = Math.max(180, Math.min(INDICATOR_SWEEP_MS, room));
      const started = performance.now();
      const tick = (now: number) => {
        if (dead || finished) return;
        const progress = Math.min(1, (now - started) / duration);
        const index = Math.round(progress * (book.length - 1));
        paintIndicators(strokes, index);
        if (progress < 1) {
          raf = requestAnimationFrame(tick);
          return;
        }
        clearDrawings();
        mountNative();
        finished = true;
        beat("done");
        chart?.resize();
      };
      raf = requestAnimationFrame(tick);
    };

    const maybeIndicators = () => {
      if (dead || finished || indicatorStarted) return;
      if (!indicatorDue || !replayEnded) return;
      if (!hasBars) {
        unavailable();
        finished = true;
        return;
      }
      runIndicatorSweep();
    };

    const leftAnchor = (cursorTime: number, firstTime: number) => {
      if (!chart || dead || finished) return;
      const to = Math.max(cursorTime + BAR_MS, firstTime + BAR_MS);
      try {
        chart.setVisibleRange({ from: firstTime, to });
      } catch {
        /* renderer without range control */
      }
    };

    const startBars = () => {
      if (!chart || dead || finished || barsStarted) return;
      if (!hasBars && !chart.replay.bounds) return;
      barsStarted = true;
      beat("bars");
      const bounds = chart.replay.bounds;
      if (!bounds) {
        replayEnded = true;
        revealHost();
        applySafe(CANDLES_VISIBLE);
        theme(THEME);
        overlay.dataset.phase = "done";
        maybeIndicators();
        return;
      }
      const firstTime = bounds.first;
      void (async () => {
        try {
          if (!chart || dead || finished) return;
          if (!chart.replay.state.active) await chart.replay.start({ from: firstTime });
          if (dead || finished || !chart) return;
          if (!volumeHandle) volumeHandle = chart.addNativeIndicator("volume");
          applySafe(CANDLES_VISIBLE);
          theme(THEME);
          revealHost();
          overlay.dataset.phase = "done";
          setCaption(`${baseCaption} · volume`);
          const anchor = (ev: { cursorTime: number }) => leftAnchor(ev.cursorTime, firstTime);
          chart.on("replay:step", anchor);
          chart.on("replay:start", anchor);
          const cursor = chart.replay.state.cursorTime ?? firstTime;
          leftAnchor(cursor, firstTime);
          if (!chart.replay.state.active) {
            replayEnded = true;
            try {
              chart.setVisibleRange({ from: bounds.first, to: bounds.last + BAR_MS });
            } catch {
              /* ignore */
            }
            maybeIndicators();
            return;
          }
          chart.on("replay:end", () => {
            replayEnded = true;
            try {
              chart?.setVisibleRange({ from: bounds.first, to: bounds.last + BAR_MS });
            } catch {
              /* ignore */
            }
            maybeIndicators();
          });
          const remaining = Math.max(1, chart.replay.state.remaining || 240);
          const interval = Math.max(4, BARS_SWEEP_MS / remaining);
          chart.replay.play(interval);
        } catch {
          replayEnded = true;
          revealHost();
          applySafe(CANDLES_VISIBLE);
          theme(THEME);
          overlay.dataset.phase = "done";
          maybeIndicators();
        }
      })();
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
          : { intro: false, zoom: true, pan: true, autoscale: true },
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
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
