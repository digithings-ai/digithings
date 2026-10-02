"use client";

import { useEffect, useRef, useState } from "react";
import type { IndicatorHandle, Vela } from "@luxalgo/vela";
import { BUILD_DONE_MS } from "@/lib/hero-build";
import { HERO_PRODUCTS } from "@/lib/live/hero-feed";

/** Hero backdrop: a LuxAlgo Vela chart (the live backbone, not a demo).
 *
 *  One random BTC, ETH or SOL product + one overlay load per reload (no timed
 *  cycling). Candles reveal progressively left→right on the wordmark clock.
 *  Wheel: keep chart zoom-out while the gesture is live; after zoom settle (or
 *  once the zoom-out budget is spent) release so the page scrolls past the
 *  landing. Hover crosshair + horizontal drag still work. Axis stays auto.
 *  Reduced motion skips the sweep. */

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

/** Idle gap after the last zoom wheel before we treat the zoom as settled. */
const WHEEL_IDLE_MS = 140;
/** Cumulative vertical deltaY spent on zoom-out before we force page unlock
 *  (covers continuous trackpad flicks that never idle mid-gesture). */
const ZOOM_OUT_BUDGET = 720;

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

    // Page-scroll release state for the hero wheel (Vela always preventDefaults).
    let pageUnlocked = false;
    let zoomOutUsed = 0;
    let idleTimer: ReturnType<typeof setTimeout> | null = null;

    const atPageTop = () => window.scrollY <= 1;

    const onWheelCapture = (e: WheelEvent) => {
      // Horizontal / shift pan stays on the chart.
      if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;

      if (pageUnlocked) {
        if (atPageTop() && e.deltaY < 0) {
          // Back at the top scrolling up — allow zoom-in again.
          pageUnlocked = false;
          zoomOutUsed = 0;
          return;
        }
        // Block Vela so it cannot preventDefault; page scrolls normally.
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

      // Still in the zoom phase — let Vela handle this event.
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        idleTimer = null;
        // After zoom settle at the top, next wheel scrolls the page.
        if (!dead && atPageTop() && zoomOutUsed > 0) pageUnlocked = true;
      }, WHEEL_IDLE_MS);
    };

    host.addEventListener("wheel", onWheelCapture, { capture: true, passive: true });

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
      // Vela sets touch-action:none on attach; restore vertical page pan for touch.
      host.style.touchAction = "pan-y";
      chart.data.registerProvider("coinbase", new CoinbaseProvider());
      chart.addNativeIndicator("sma", { inputs: { length: 20, color: "#E8F7FF" } });
      chart.addNativeIndicator("ema", { inputs: { length: 50, color: "#F5C16C" } });
      overlay = chart.addNativeIndicator(picked.type);
      setCaption(label(picked.label));
      if (!reduced) {
        // Progressive L→R reveal on the wordmark clock; hover + h-drag stay live.
        host.animate(
          [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)" }],
          { duration: BUILD_DONE_MS, easing: "ease-out" },
        );
      }
    })().catch(() => {
      if (!dead) setCaption("LuxAlgo Vela · chart unavailable");
    });

    return () => {
      dead = true;
      if (idleTimer) clearTimeout(idleTimer);
      host.removeEventListener("wheel", onWheelCapture, { capture: true });
      overlay?.remove();
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
