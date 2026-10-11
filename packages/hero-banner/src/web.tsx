"use client";

import { useEffect, useRef } from "react";

import { paintFrame, toneColors } from "./canvas";
import { claimLoading, nextTickMs, preparedBanner, resolveLive, resolveMotion, sampleBanner } from "./engine";
import type { BannerDefinition } from "./types";

/**
 * Web hero banner: the same definition the terminal draws, on a canvas.
 * Width follows the container; pixels stay square and whole at the device
 * pixel ratio. LOADING plays once per tab (sessionStorage); reduced motion
 * paints the settled mark and never starts a timer. `armed` holds the banner
 * blank until a scroll-triggered surface lets it start (footer marks).
 */
export function HeroBanner({
  def,
  live,
  armed = true,
  gap,
  className,
}: {
  def: BannerDefinition;
  live?: boolean;
  armed?: boolean;
  gap?: number;
  className?: string;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const { layout } = preparedBanner(def);
  const usedGap = gap ?? layout.gap;
  const width = layout.text.length * layout.font.cols + Math.max(0, layout.text.length - 1) * usedGap;

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !armed) return;
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const motion = resolveMotion({ prefersReduced: media?.matches === true });
    let store: Storage | null = null;
    try {
      store = window.sessionStorage;
    } catch {
      store = null;
    }
    const skipLoading = motion === "full" ? !claimLoading(def, store) : true;
    const liveOn = resolveLive(def, { config: live });
    const origin = performance.now();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let raf = 0;

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth || width;
      const pixel = Math.max(1, Math.floor((cssWidth * dpr) / width));
      if (canvas.width !== width * pixel || canvas.height !== layout.height * pixel) {
        canvas.width = width * pixel;
        canvas.height = layout.height * pixel;
      }
      const sample = sampleBanner(def, { t: performance.now() - origin, live: liveOn, motion, skipLoading, gap: usedGap });
      const styles = getComputedStyle(canvas);
      paintFrame(ctx, sample.frame, { pixel, colors: toneColors(def.palette, (v) => styles.getPropertyValue(v)) });
      const wait = nextTickMs(def, sample.phase);
      if (wait != null) timer = setTimeout(() => (raf = requestAnimationFrame(draw)), wait);
    };
    draw();
    return () => {
      if (timer) clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [def, live, armed, usedGap, width, layout.height]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={def.label}
      className={className}
      style={{ width: "100%", aspectRatio: `${width} / ${layout.height}`, imageRendering: "pixelated" }}
    />
  );
}
