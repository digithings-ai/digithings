"use client";
/**
 * Reference port of the ambient background bloom used on digithings.ai
 * subpages (architecture / chat / modules) and, in a teal-palette variant, on
 * digiquant.io subpages (pipeline / strategies / contact).
 *
 * Source: frontend/digithings-web/components/landing/AmbientMesh.tsx —
 * verbatim (the neutral variant that reads its colour from the live --ink
 * token; digiquant-web's variant hard-codes a quiet teal PAL instead). The
 * `.dq-ambient` CSS is copied into app/effects/effects.css; on this page the
 * canvas is contained in a `.fx-mesh-frame` demo panel rather than pinned
 * behind a whole page.
 *
 * Theme-aware (additive ink glow on dark, dark gray wash on light), leans
 * gently toward the pointer, and renders one static frame under
 * prefers-reduced-motion. Without JS the canvas stays blank — the bloom is
 * decorative (aria-hidden) and the content above it never depends on it.
 */
import { useEffect, useRef } from "react";

const rnd = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

// Neutral platform palette: the ambient glow reads its colour from the live
// --ink token (monochrome) rather than the teal module accent.
const BLOB_COUNT = 3;
const hexToRgb = (hex: string): string => {
  const h = hex.replace("#", "").trim();
  const full = h.length === 3 ? h.replace(/(.)/g, "$1$1") : h;
  const n = parseInt(full, 16);
  return Number.isNaN(n) ? "236,238,240" : `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

export function AmbientMesh() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const readLight = () => document.documentElement.getAttribute("data-theme") === "light";
    const readInk = () =>
      hexToRgb(getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#ECEEF0");
    let light = readLight();
    let ink = readInk();

    let W = 0;
    let H = 0;
    let blobs: { bx: number; by: number; r: number; ph: number; sp: number }[] = [];

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      // blobs biased to the upper band so the hue concentrates behind the header
      blobs = Array.from({ length: BLOB_COUNT }, () => ({
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
      // additive glow on dark; on light, darken with ink-tinted blobs (source-over
      // on the transparent canvas composites as a soft gray wash over --bg).
      ctx!.globalCompositeOperation = light ? "source-over" : "lighter";
      blobs.forEach((b, i) => {
        let cx = (b.bx + Math.sin(t * b.sp + b.ph) * 0.1) * W;
        const cy = (b.by + Math.cos(t * b.sp * 1.1 + b.ph) * 0.08) * H;
        cx += (fx * W - cx) * (i % 2 ? 0.12 : 0.06);
        const rad = b.r * Math.max(W, H) * 0.5;
        const g = ctx!.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, `rgba(${ink},${light ? 0.14 : 0.12})`);
        g.addColorStop(1, `rgba(${ink},0)`);
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
      ink = readInk();
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
