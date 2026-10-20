"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { paintFrame, toneColors } from "./canvas";
import { claimLoading, nextTickMs, preparedBanner, resolveLive, resolveMotion, sampleBanner } from "./engine";
import { settledFallback } from "./ssr";
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
  replayLoading = false,
  gap,
  className,
}: {
  def: BannerDefinition;
  live?: boolean;
  armed?: boolean;
  /** Play LOADING on every mount. The landing top bar builds with the hero
   *  each visit; the session flag would otherwise skip straight to the settled mark. */
  replayLoading?: boolean;
  gap?: number;
  className?: string;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const { layout } = preparedBanner(def);
  const usedGap = gap ?? layout.gap;
  const width = layout.text.length * layout.font.cols + Math.max(0, layout.text.length - 1) * usedGap;
  // The canvas paints on mount, so a server render and a no-JS page would
  // show an empty box. The settled mark is the fallback: it is the same
  // frame the banner draws when it is still, so the shape is the mark and not
  // an approximation. The colour stays a CSS value so the fallback follows
  // the page theme the way the painted canvas does.
  const fallback = useMemo(() => settledFallback(def, { gap: usedGap }), [def, usedGap]);
  const [painted, setPainted] = useState(false);
  const settledStyle = (
    painted
      ? {}
      : fallback.kind === "mask"
        ? {
            backgroundColor: fallback.color,
            maskImage: fallback.url,
            maskSize: "100% 100%",
            maskRepeat: "no-repeat",
            maskMode: "alpha",
          }
        : {
            backgroundImage: fallback.url,
            backgroundSize: "100% 100%",
            backgroundRepeat: "no-repeat",
          }
  ) as CSSProperties;

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
    const skipLoading =
      motion === "full" ? (replayLoading ? false : !claimLoading(def, store)) : true;
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
    // The canvas now carries the mark itself, so drop the server-rendered
    // fallback in the same task, before the browser paints the frame.
    canvas.style.backgroundColor = "";
    canvas.style.backgroundImage = "";
    canvas.style.maskImage = "";
    setPainted(true);
    return () => {
      if (timer) clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [def, live, armed, replayLoading, usedGap, width, layout.height]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={def.label}
      className={className}
      style={{
        width: "100%",
        aspectRatio: `${width} / ${layout.height}`,
        imageRendering: "pixelated",
        ...settledStyle,
      }}
    />
  );
}
