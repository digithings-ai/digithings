"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import {
  CHART_INTRO_MS,
  COPY_DONE_MS,
  INDICATOR_STAGGER_MS,
} from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart (the live backbone, not a demo).
 *
 *  Sequence (reduced motion skips staging):
 *  1. Logo + copy + buttons settle first (`COPY_DONE_MS`).
 *  2. Chart fades in and Vela intro-grows candles L→R.
 *  3. SMA → EMA → overlay mount on a stagger so the graph constructs itself.
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
/** Soft fade of the chart host once the copy phase ends. */
const CHART_FADE_MS = 520;

export function QuantField() {
  const ref = useRef<HTMLDivElement>(null);
  const [caption, setCaption] = useState("LuxAlgo Vela");

  useEffect(() => {
    const host = ref.current;
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

    // Hold the chart invisible until the copy phase finishes.
    host.style.opacity = reduced ? "1" : "0";

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
              intro: { style: "grow", duration: CHART_INTRO_MS },
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
        return;
      }

      // Fade the live chart in, then stage indicators over the intro.
      host.style.transition = `opacity ${CHART_FADE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`;
      // Force style flush before opacity so the transition runs.
      void host.offsetWidth;
      host.style.opacity = "1";
      // Full-viewport host — remeasure after layout so candles fill the hero.
      chart.resize();
      requestAnimationFrame(() => {
        if (!dead) chart?.resize();
      });

      later(Math.round(CHART_INTRO_MS * 0.28), () => {
        chart?.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
      });
      later(Math.round(CHART_INTRO_MS * 0.28) + INDICATOR_STAGGER_MS, () => {
        chart?.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
      });
      later(Math.round(CHART_INTRO_MS * 0.28) + INDICATOR_STAGGER_MS * 2, () => {
        overlay = chart?.addNativeIndicator(picked.type) ?? null;
        setCaption(label(picked.label));
      });
    };

    const startDelay = reduced ? 0 : COPY_DONE_MS;
    later(startDelay, () => {
      void mountChart().catch(() => {
        if (!dead) {
          host.style.opacity = "1";
          setCaption("LuxAlgo Vela · chart unavailable");
        }
      });
    });

    return () => {
      dead = true;
      if (idleTimer) clearTimeout(idleTimer);
      for (const id of timers) clearTimeout(id);
      host.removeEventListener("wheel", onWheelCapture, { capture: true });
      overlay?.remove();
      chart?.destroy();
    };
  }, []);

  return (
    <>
      <div
        ref={ref}
        aria-label={caption}
        className="absolute inset-0 -z-10 h-full min-h-full w-full [transform:translateZ(0)]"
      />
      <p className="pointer-events-none absolute bottom-3 left-4 z-10 m-0 font-mono text-[0.66rem] text-ink-mute">{caption}</p>
    </>
  );
}
