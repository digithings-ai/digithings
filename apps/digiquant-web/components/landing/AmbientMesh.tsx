"use client";
/**
 * Subtle ambient mesh backdrop for the subpages (pipeline / strategies / contact).
 *
 * The same teal blob family as the hero's HeroMesh, but quieter and pinned to the
 * top of the page, so the brand hue carries onto the subpages without a full hero.
 * Rendered as an `absolute` canvas inside a `position: relative` `.dq-subpage`, so
 * it only covers the top band (never paints over the footer). It paints over the
 * page's `--bg`; content lives in `.wrap` (z-index 1) and stays above it.
 * Theme-aware (additive glow on dark, soft tint on light) and renders one static
 * frame under prefers-reduced-motion.
 */
import { useEffect, useRef } from "react";

const rnd = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

// teal accent family — a quieter subset of HeroMesh's PAL
const PAL = ["61,214,196", "38,120,110", "63,185,132"];

export function AmbientMesh() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const readLight = () => document.documentElement.getAttribute("data-theme") === "light";
    let light = readLight();

    let W = 0;
    let H = 0;
    let blobs: { c: string; bx: number; by: number; r: number; ph: number; sp: number }[] = [];

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      // blobs biased to the upper band so the hue concentrates behind the header
      blobs = PAL.map((c) => ({
        c,
        bx: rnd(0.25, 0.75),
        by: rnd(0.16, 0.42),
        r: rnd(0.5, 0.85),
        ph: Math.random() * 6.28,
        sp: rnd(0.0001, 0.00022),
      }));
    }

    let tfx = 0.5;
    let fx = 0.5;

    function draw(t: number) {
      fx += (tfx - fx) * 0.04; // gentle, slower than the hero
      ctx!.clearRect(0, 0, W, H);
      // additive glow on dark; on the near-white light base "lighter" can't
      // brighten past white, so fall back to a normal soft teal tint.
      ctx!.globalCompositeOperation = light ? "source-over" : "lighter";
      blobs.forEach((b, i) => {
        let cx = (b.bx + Math.sin(t * b.sp + b.ph) * 0.1) * W;
        const cy = (b.by + Math.cos(t * b.sp * 1.1 + b.ph) * 0.08) * H;
        cx += (fx * W - cx) * (i % 2 ? 0.12 : 0.06);
        const rad = b.r * Math.max(W, H) * 0.5;
        const g = ctx!.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, `rgba(${b.c},${light ? 0.30 : 0.22})`);
        g.addColorStop(1, `rgba(${b.c},0)`);
        ctx!.fillStyle = g;
        ctx!.beginPath();
        ctx!.arc(cx, cy, rad, 0, 7);
        ctx!.fill();
      });
    }

    let raf = 0;
    function loop(t: number) {
      draw(t);
      raf = requestAnimationFrame(loop);
    }

    function onMove(e: MouseEvent) {
      tfx = clamp(e.clientX / window.innerWidth, 0, 1);
    }
    const onTheme = () => {
      light = readLight();
      draw(performance.now());
    };
    const obs = new MutationObserver(onTheme);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onResize = () => {
      init();
      draw(performance.now());
    };

    init();
    draw(performance.now()); // always paint one frame (static fallback)
    window.addEventListener("resize", onResize, { passive: true });

    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate) {
      window.addEventListener("mousemove", onMove, { passive: true });
      raf = requestAnimationFrame(loop);
    }

    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousemove", onMove);
      obs.disconnect();
    };
  }, []);

  return <canvas className="dq-ambient" ref={canvasRef} aria-hidden="true" />;
}
