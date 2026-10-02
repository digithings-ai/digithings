"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  AXIS_Y_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_INTRO_MS,
  COPY_DONE_MS,
  GRID_START_MS,
  INDICATOR_START_MS,
  INDICATOR_STAGGER_MS,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

const CHART_FADE_MS = 220;

/** Hero backdrop: a LuxAlgo Vela chart (the live backbone, not a demo).
 *
 *  Sequence (reduced motion skips staging):
 *  1. Logo + copy + buttons settle first (`COPY_DONE_MS` — short handoff).
 *  2. X-axis reveals L→R, right Y-axis B→T, then grid.
 *  3. Candles + volume construct L→R together via bar replay (~5s total chart phase).
 *  4. Indicators stream once bars are underway.
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

const GRID_OFF = {
  grid: {
    vertLines: { visible: false },
    horzLines: { visible: false },
  },
} as const;

const GRID_ON = {
  grid: {
    vertLines: { visible: true },
    horzLines: { visible: true },
  },
} as const;

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const maskRef = useRef<HTMLDivElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
    const mask = maskRef.current;
    if (!host) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const product = HERO_PRODUCTS[Math.floor(Math.random() * HERO_PRODUCTS.length)] ?? HERO_PRODUCTS[0];
    const picked = CYCLE[Math.floor(Math.random() * CYCLE.length)] ?? CYCLE[0];
    let dead = false;
    let chart: Vela | null = null;
    let overlay: IndicatorHandle | null = null;
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    const later = (ms: number, fn: () => void) => {
      const id = setTimeout(() => {
        if (!dead) fn();
      }, ms);
      timers.push(id);
      return id;
    };

    host.style.opacity = reduced ? "1" : "0";
    if (mask) mask.dataset.phase = reduced ? "done" : "armed";

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

    const fadeIn = () => {
      host.style.transition = `opacity ${CHART_FADE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`;
      void host.offsetWidth;
      host.style.opacity = "1";
      chart?.resize();
      requestAnimationFrame(() => {
        if (!dead) chart?.resize();
      });
    };

    const stageIndicators = (baseDelay: number) => {
      later(baseDelay + INDICATOR_START_MS, () => {
        chart?.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
      });
      later(baseDelay + INDICATOR_START_MS + INDICATOR_STAGGER_MS, () => {
        chart?.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
      });
      later(baseDelay + INDICATOR_START_MS + INDICATOR_STAGGER_MS * 2, () => {
        overlay = chart?.addNativeIndicator(picked.type) ?? null;
        setCaption(label(picked.label));
      });
    };

    const runAxisGridThenBars = async () => {
      if (!chart || dead) return;

      try {
        chart.renderer.applyConfig(GRID_OFF);
      } catch {
        /* renderer without rich config — keep going */
      }

      await chart.ready().catch(() => undefined);
      if (dead) return;

      const bounds = chart.replay.bounds;
      let usedReplay = false;

      if (bounds) {
        try {
          await chart.replay.start({ from: bounds.first });
          usedReplay = !dead && chart.replay.state.active;
        } catch {
          usedReplay = false;
        }
      }

      if (dead) return;
      fadeIn();

      if (mask) {
        mask.dataset.phase = "x";
        later(AXIS_Y_START_MS, () => {
          if (mask) mask.dataset.phase = "xy";
        });
        later(GRID_START_MS, () => {
          if (mask) mask.dataset.phase = "grid";
          try {
            chart?.renderer.applyConfig(GRID_ON);
          } catch {
            /* ignore */
          }
        });
        later(BARS_START_MS, () => {
          if (mask) mask.dataset.phase = "done";
        });
      } else {
        later(GRID_START_MS, () => {
          try {
            chart?.renderer.applyConfig(GRID_ON);
          } catch {
            /* ignore */
          }
        });
      }

      later(BARS_START_MS, () => {
        if (!chart || dead) return;

        if (usedReplay) {
          const remaining = Math.max(1, chart.replay.state.remaining || 240);
          const interval = Math.max(8, Math.round(BARS_SWEEP_MS / remaining));
          chart.replay.play(interval);
          stageIndicators(0);
          chart.on("replay:end", () => {
            /* full history restored; live resumes */
          });
          return;
        }

        // Fallback: Vela intro grow (volume may not sync per-bar).
        try {
          chart.renderer.set({
            animations: { intro: { style: "grow", duration: CHART_INTRO_MS } },
          });
        } catch {
          /* ignore */
        }
        stageIndicators(Math.round(CHART_INTRO_MS * 0.22));
      });
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
        theme: THEME,
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

      if (reduced) {
        chart.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
        chart.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
        overlay = chart.addNativeIndicator(picked.type);
        setCaption(label(picked.label));
        host.style.opacity = "1";
        if (mask) mask.dataset.phase = "done";
        return;
      }

      await runAxisGridThenBars();
    };

    const startDelay = reduced ? 0 : COPY_DONE_MS;
    later(startDelay, () => {
      void mountChart().catch(() => {
        if (!dead) {
          host.style.opacity = "1";
          if (mask) mask.dataset.phase = "done";
          setCaption("LuxAlgo Vela · chart unavailable");
        }
      });
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
      overlay?.remove();
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
        <div
          ref={maskRef}
          className="hero-axis-mask"
          data-phase="armed"
          aria-hidden="true"
        >
          <div className="hero-axis-mask__x" />
          <div className="hero-axis-mask__y" />
        </div>
      </div>
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
