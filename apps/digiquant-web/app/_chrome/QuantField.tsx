"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  AXIS_Y_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_BUILD_MAX_MS,
  CHART_INTRO_MS,
  COPY_DONE_MS,
  GRID_START_MS,
  INDICATOR_START_MS,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart (the live backbone, not a demo).
 *
 *  Sequence (reduced motion skips staging):
 *  1. Mount Vela at t≈0 (plot rect real; series+volume hidden; grid off).
 *  2. Chrome settles (~0.7s); handoff <300ms into construct strokes.
 *  3. SVG strokes: X L→R, right Y B→T, then faint grid (~0.8s). Construction,
 *     not a black mask peel over a finished chart. No host opacity fade.
 *  4. Enable Vela grid/candles; replay bars so volume rises with each candle (~2s).
 *     Viewport is left-anchored (fixed past `from`, growing `to`) so candles fill
 *     L→R in time — not Vela's default right-pinned view (which looks RTL).
 *  5. Indicators added at bars start so replay reveals them L→R with the sweep.
 *  Hard 10s cap from first paint force-finishes the chart.
 *
 *  Wheel: keep chart zoom-out while the gesture is live; after zoom settle (or
 *  once the zoom-out budget is spent) release so the page scrolls past the
 *  landing. Hover crosshair + horizontal drag still work. */

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

const CANDLES_HIDDEN = {
  candles: {
    bodyVisible: false,
    wickVisible: false,
    borderVisible: false,
  },
  grid: {
    vertLines: { visible: false },
    horzLines: { visible: false },
  },
} as const;

const CANDLES_VISIBLE = {
  candles: {
    bodyVisible: true,
    wickVisible: true,
    borderVisible: true,
  },
  grid: {
    vertLines: { visible: true },
    horzLines: { visible: true },
  },
} as const;

const GRID_LINES_H = [18, 36, 54, 72] as const;
const GRID_LINES_V = [16, 32, 48, 64, 80] as const;

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<SVGSVGElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
    const overlay = overlayRef.current;
    if (!host) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const product = HERO_PRODUCTS[Math.floor(Math.random() * HERO_PRODUCTS.length)] ?? HERO_PRODUCTS[0];
    const picked = CYCLE[Math.floor(Math.random() * CYCLE.length)] ?? CYCLE[0];
    let dead = false;
    let chart: Vela | null = null;
    let overlayInd: IndicatorHandle | null = null;
    let sma: IndicatorHandle | null = null;
    let ema: IndicatorHandle | null = null;
    let finished = false;
    let axesStarted = false;
    let barsStarted = false;
    let axesComplete = false;
    let chromeReady = reduced;
    let chartReady = false;
    let hasBars = false;
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    const later = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        if (!dead) fn();
      }, ms);
      timers.push(id);
      return id;
    };

    if (overlay) overlay.dataset.phase = reduced ? "done" : "armed";

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

    const label = (name: string) =>
      `LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · ${name}`;

    const applySafe = (config: unknown) => {
      try {
        chart?.renderer.applyConfig(config);
      } catch {
        /* renderer without rich config — keep going */
      }
    };

    const addIndicators = () => {
      if (!chart || sma) return;
      sma = chart.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
      ema = chart.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
      overlayInd = chart.addNativeIndicator(picked.type);
      setCaption(label(picked.label));
    };

    const showComplete = () => {
      if (finished || dead) return;
      finished = true;
      barsStarted = true;
      if (overlay) overlay.dataset.phase = "done";
      applySafe(CANDLES_VISIBLE);
      try {
        chart?.renderer.set({ theme: THEME });
      } catch {
        /* ignore */
      }
      try {
        chart?.replay.stop();
      } catch {
        /* ignore */
      }
      addIndicators();
      chart?.resize();
    };

    const restoreTheme = () => {
      try {
        chart?.renderer.set({ theme: THEME });
      } catch {
        /* ignore */
      }
    };

    /** Keep the viewport left-anchored while replay reveals bars.
     *  Vela defaults to rightOffset near the latest bar, which makes early
     *  candles cluster on the right and shove history left (RTL). Instead pin
     *  `from` at the oldest revealed time and grow `to` with the cursor so
     *  past stays left and new candles/volume/indicators appear on the right. */
    const leftAnchorVisible = (cursorTime: number, firstTime: number) => {
      if (!chart || dead || finished) return;
      const from = firstTime;
      // One-bar pad keeps a non-zero span on the first step and a sliver of
      // empty future on the right so the newest candle is not glued to the edge.
      const barMs = 60_000; // hero timeframe is 1m
      const to = Math.max(cursorTime + barMs, from + barMs);
      try {
        chart.setVisibleRange({ from, to });
      } catch {
        /* renderer without range control — keep going */
      }
    };

    const startBars = () => {
      if (!chart || dead || finished || barsStarted) return;
      barsStarted = true;
      applySafe(CANDLES_VISIBLE);
      restoreTheme();
      if (overlay) overlay.dataset.phase = "done";

      later(INDICATOR_START_MS, () => {
        addIndicators();
      });

      const bounds = chart.replay.bounds;
      if (bounds) {
        const firstTime = bounds.first;
        void (async () => {
          try {
            if (!chart || dead || finished) return;
            const already = chart.replay.state.active;
            if (!already) {
              await chart.replay.start({ from: firstTime });
            }
            if (dead || finished || !chart) return;

            const anchorFromStep = (ev: { cursorTime: number }) => {
              leftAnchorVisible(ev.cursorTime, firstTime);
            };
            chart.on("replay:step", anchorFromStep);
            chart.on("replay:start", anchorFromStep);
            // Seed immediately so the first revealed bar(s) paint on the left,
            // not clustered at the default right edge before the first step.
            const cursor = chart.replay.state.cursorTime ?? firstTime;
            leftAnchorVisible(cursor, firstTime);

            const remaining = Math.max(1, chart.replay.state.remaining || 240);
            const interval = Math.max(8, Math.round(BARS_SWEEP_MS / remaining));
            chart.replay.play(interval);
            chart.on("replay:end", () => {
              /* full history restored; live resumes — leave default view */
            });
          } catch {
            // Fallback: Vela intro grow (volume may not sync per-bar).
            try {
              chart?.renderer.set({
                animations: { intro: { style: "grow", duration: CHART_INTRO_MS } },
              });
            } catch {
              /* ignore */
            }
          }
        })();
        return;
      }

      try {
        chart.renderer.set({
          animations: { intro: { style: "grow", duration: CHART_INTRO_MS } },
        });
      } catch {
        /* ignore */
      }
    };

    const runAxesThenBars = () => {
      if (!chart || dead || axesStarted) return;
      axesStarted = true;

      applySafe(CANDLES_HIDDEN);

      // Prefetch replay to the first bar so the plot stays empty during strokes.
      const bounds = chart.replay.bounds;
      if (bounds && hasBars) {
        void chart.replay.start({ from: bounds.first }).catch(() => undefined);
      }

      if (overlay) {
        overlay.dataset.phase = "x";
        later(AXIS_Y_START_MS, () => {
          if (overlay && !finished) overlay.dataset.phase = "xy";
        });
        later(GRID_START_MS, () => {
          if (overlay && !finished) overlay.dataset.phase = "grid";
        });
      }

      later(BARS_START_MS, () => {
        if (dead || finished) return;
        axesComplete = true;
        if (hasBars) {
          startBars();
        } else {
          // Axes ran on an empty plot; candles wait for bars (10s cap still applies).
          if (overlay) overlay.dataset.phase = "done";
        }
      });
    };

    const tryStartAxes = () => {
      if (reduced) return;
      if (chromeReady && chartReady) runAxesThenBars();
    };

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
        theme: { ...THEME, gridColor: "transparent" },
        upColor: UP,
        downColor: DOWN,
        volume: true,
        drawings: false,
        animations: reduced
          ? false
          : {
              intro: false,
              zoom: true,
              pan: true,
              autoscale: true,
            },
      });
      host.style.touchAction = "pan-y";
      chart.data.registerProvider("coinbase", new CoinbaseProvider());
      applySafe(CANDLES_HIDDEN);

      chart.on("load:end", (ev) => {
        if (dead) return;
        hasBars = (ev?.bars ?? 0) > 0;
        if (!hasBars && axesComplete && !finished) {
          setCaption("LuxAlgo Vela · chart unavailable");
        }
        if (hasBars && axesComplete && !finished && !barsStarted) {
          startBars();
        }
      });

      if (reduced) {
        await chart.ready().catch(() => undefined);
        if (dead) return;
        hasBars = Boolean(chart.replay.bounds);
        applySafe(CANDLES_VISIBLE);
        try {
          chart.renderer.set({ theme: THEME });
        } catch {
          /* ignore */
        }
        addIndicators();
        if (!hasBars) setCaption("LuxAlgo Vela · chart unavailable");
        if (overlay) overlay.dataset.phase = "done";
        finished = true;
        return;
      }

      await chart.ready().catch(() => undefined);
      if (dead) return;
      hasBars = Boolean(chart.replay.bounds);
      chartReady = true;
      chart.resize();
      tryStartAxes();
    };

    // Mount immediately so the plot rect is real during chrome (plan: do not wait on wordmark).
    void mountChart().catch(() => {
      if (!dead) {
        chartReady = true;
        if (overlay) overlay.dataset.phase = "done";
        setCaption("LuxAlgo Vela · chart unavailable");
        tryStartAxes();
      }
    });

    if (!reduced) {
      later(COPY_DONE_MS, () => {
        chromeReady = true;
        tryStartAxes();
      });
    }

    later(CHART_BUILD_MAX_MS, () => {
      if (!hasBars && chart) {
        setCaption("LuxAlgo Vela · chart unavailable");
      }
      showComplete();
    });

    return () => {
      dead = true;
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
      chart?.destroy();
    };
  }, []);

  return (
    <>
      <div className="absolute inset-0 -z-10 h-full min-h-full w-full">
        <div
          ref={ref}
          aria-label={caption}
          className="absolute inset-0 h-full w-full [transform:translateZ(0)]"
        />
        <svg
          ref={overlayRef}
          className="hero-construct"
          data-phase="armed"
          aria-hidden="true"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {GRID_LINES_H.map((y) => (
            <line
              key={`h${y}`}
              className="hero-construct__grid"
              x1="2"
              y1={y}
              x2="92"
              y2={y}
            />
          ))}
          {GRID_LINES_V.map((x) => (
            <line
              key={`v${x}`}
              className="hero-construct__grid"
              x1={x}
              y1="4"
              x2={x}
              y2="96"
            />
          ))}
          <line className="hero-construct__x" x1="2" y1="96" x2="92" y2="96" />
          <line className="hero-construct__y" x1="92" y1="96" x2="92" y2="4" />
        </svg>
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
