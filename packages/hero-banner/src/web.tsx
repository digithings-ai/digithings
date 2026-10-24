"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { paintFrame, toneColors } from "./canvas";
import { createClock } from "./clock";
import { claimLoading, nextTickMs, preparedBanner, resolveLive, resolveMotion, sampleBanner } from "./engine";
import { settledFallback } from "./ssr";
import type { BannerDefinition } from "./types";

/**
 * Web hero banner: the same definition the terminal draws, on a canvas.
 * Width follows the container; pixels stay square and whole at the device
 * pixel ratio. LOADING plays once per tab (sessionStorage); reduced motion
 * paints the settled mark and never starts a timer. `armed` holds the banner
 * blank until a scroll-triggered surface lets it start (footer marks).
 *
 * The repaint loop only runs while the mark is on screen and the tab is
 * visible: pausing banks the animation time, so a banner scrolled back into
 * view resumes mid-build rather than jumping to the end of its script.
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

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    let motion = resolveMotion({ prefersReduced: reduced?.matches === true });
    let store: Storage | null = null;
    try {
      store = window.sessionStorage;
    } catch {
      store = null;
    }
    const skipLoading = motion === "full" ? (replayLoading ? false : !claimLoading(def, store)) : true;
    const liveOn = resolveLive(def, { config: live });
    const clock = createClock(performance.now());

    let timer: ReturnType<typeof setTimeout> | null = null;
    let raf = 0;
    let visible = document.visibilityState !== "hidden";
    let onScreen = true;
    let colors: Record<string, string> | null = null;

    const running = () => visible && onScreen && motion !== "reduced";

    const resolveColors = (): Record<string, string> => {
      const styles = getComputedStyle(canvas);
      return toneColors(def.palette, (name) => styles.getPropertyValue(name));
    };

    const stop = (): void => {
      if (timer) clearTimeout(timer);
      if (raf) cancelAnimationFrame(raf);
      timer = null;
      raf = 0;
    };

    const schedule = (wait: number): void => {
      if (!running() || timer) return;
      timer = setTimeout(() => {
        timer = null;
        raf = requestAnimationFrame(draw);
      }, wait);
    };

    const draw = (): void => {
      timer = null;
      raf = 0;
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth || width;
      const pixel = Math.max(1, Math.floor((cssWidth * dpr) / width));
      if (canvas.width !== width * pixel || canvas.height !== layout.height * pixel) {
        canvas.width = width * pixel;
        canvas.height = layout.height * pixel;
      }
      // Read the theme once per paint, not once per pixel, and refresh it only
      // when the theme actually changes: getComputedStyle here forces a style
      // flush that has no business inside a 40ms loop.
      if (!colors) colors = resolveColors();
      const sample = sampleBanner(def, {
        t: clock.elapsed(performance.now()),
        live: liveOn,
        motion,
        skipLoading,
        gap: usedGap,
      });
      paintFrame(ctx, sample.frame, { pixel, colors });
      const wait = nextTickMs(def, sample.phase);
      if (wait != null) schedule(wait);
    };

    /** Start or stop the loop for the current tab, viewport and motion state. */
    const sync = (): void => {
      if (!running()) {
        clock.pause(performance.now());
        stop();
        return;
      }
      clock.resume(performance.now());
      if (!timer && !raf) draw();
    };

    const onVisibilityChange = (): void => {
      visible = document.visibilityState !== "hidden";
      sync();
    };

    const onMotionChange = (): void => {
      motion = resolveMotion({ prefersReduced: reduced?.matches === true });
      stop();
      if (motion === "reduced") {
        clock.pause(performance.now());
        draw();
      } else {
        sync();
      }
    };

    const onThemeChange = (): void => {
      colors = null;
      if (!timer && !raf) draw();
    };

    draw();
    // The canvas now carries the mark itself, so drop the server-rendered
    // fallback in the same task, before the browser paints the frame.
    canvas.style.backgroundColor = "";
    canvas.style.backgroundImage = "";
    canvas.style.maskImage = "";
    setPainted(true);

    const intersection =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver((entries) => {
            const entry = entries[entries.length - 1];
            onScreen = entry ? entry.isIntersecting : true;
            sync();
          });
    intersection?.observe(canvas);
    // A theme class lands on <html>; the mark's tones are CSS variables, so
    // they have to be re-resolved when it changes.
    const themeWatch =
      typeof MutationObserver === "undefined" ? null : new MutationObserver(onThemeChange);
    themeWatch?.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
    document.addEventListener("visibilitychange", onVisibilityChange);
    reduced?.addEventListener?.("change", onMotionChange);
    scheme?.addEventListener?.("change", onThemeChange);

    return () => {
      stop();
      intersection?.disconnect();
      themeWatch?.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      reduced?.removeEventListener?.("change", onMotionChange);
      scheme?.removeEventListener?.("change", onThemeChange);
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
