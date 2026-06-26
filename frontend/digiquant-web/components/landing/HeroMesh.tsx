"use client";
/**
 * Full-bleed animated mesh-gradient hero (Stripe-style), ported from the locked
 * v7 prototype (frontend/design/demos/digiquant-landing/07-scroll-driven.html).
 *
 * The mesh blobs ease toward the cursor and parallax/fade as the hero scrolls
 * away. Theme-safe: the base fill is read from the live `--bg` token (re-read on
 * a `data-theme` change), not hardcoded — so it never paints a black hero in
 * light mode. Under prefers-reduced-motion it renders one calm static frame and
 * the entrance classes resolve to their final state via CSS.
 */
import { useEffect, useRef, type ReactNode } from "react";

const rnd = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

// teal accent family (RGB triples) — matches the v7 palette / brand accent
const PAL = ["61,214,196", "38,120,110", "63,185,132", "30,90,120"];

export function HeroMesh({ children }: { children: ReactNode }) {
  const heroRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const hero = heroRef.current;
    const canvas = canvasRef.current;
    const inner = innerRef.current;
    if (!hero || !canvas) return;

    // staggered entrance reveal
    const loadedT = window.setTimeout(() => hero.classList.add("loaded"), 80);

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      hero.classList.add("loaded");
      return () => window.clearTimeout(loadedT);
    }

    const readBg = () =>
      getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#0B0C0E";
    const readLight = () => document.documentElement.getAttribute("data-theme") === "light";
    let bg = readBg();
    let light = readLight();

    let blobs: { c: string; bx: number; by: number; r: number; ph: number; sp: number }[] = [];
    let MW = 0;
    let MH = 0;

    function initMesh() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      MW = canvas!.clientWidth;
      MH = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(MW * dpr));
      canvas!.height = Math.max(1, Math.round(MH * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      blobs = PAL.map((c) => ({
        c,
        bx: rnd(0.2, 0.8),
        by: rnd(0.2, 0.8),
        r: rnd(0.5, 0.9),
        ph: Math.random() * 6.28,
        sp: rnd(0.00012, 0.00026),
      }));
    }

    let sn = 0; // scroll-normalized 0..1 over the hero height
    let tfx = 0.5;
    let tfy = 0.42;
    let fx = 0.5;
    let fy = 0.42;

    function drawMesh(t: number) {
      fx += (tfx - fx) * 0.045; // slow ease — follows the cursor, never snaps
      fy += (tfy - fy) * 0.045;
      ctx!.globalCompositeOperation = "source-over";
      ctx!.fillStyle = bg;
      ctx!.fillRect(0, 0, MW, MH);
      // Additive glow reads beautifully on the dark base; on the near-white
      // light base "lighter" can't brighten past white, so the mesh vanishes —
      // fall back to a normal blend (soft teal tint) there.
      ctx!.globalCompositeOperation = light ? "source-over" : "lighter";
      blobs.forEach((b, i) => {
        let cx = (b.bx + Math.sin(t * b.sp + b.ph) * 0.14 + sn * (i % 2 ? 0.06 : -0.06)) * MW;
        let cy = (b.by + Math.cos(t * b.sp * 1.1 + b.ph) * 0.14 - sn * 0.16) * MH;
        cx += (fx * MW - cx) * (0.2 + (i % 2 ? 0.1 : 0));
        cy += (fy * MH - cy) * (0.2 + (i % 2 ? 0.1 : 0));
        const rad = b.r * Math.max(MW, MH) * (0.5 + (i % 2 ? 0.08 : 0));
        const g = ctx!.createRadialGradient(cx, cy, 0, cx, cy, rad);
        g.addColorStop(0, `rgba(${b.c},${(light ? 0.3 : 0.5) - sn * (light ? 0.1 : 0.18)})`);
        g.addColorStop(1, `rgba(${b.c},0)`);
        ctx!.fillStyle = g;
        ctx!.beginPath();
        ctx!.arc(cx, cy, rad, 0, 7);
        ctx!.fill();
      });
    }

    let raf = 0;
    function loop(t: number) {
      drawMesh(t);
      raf = requestAnimationFrame(loop);
    }

    function onMouseMove(e: MouseEvent) {
      const r = hero!.getBoundingClientRect();
      tfx = clamp(e.clientX / window.innerWidth, 0, 1);
      tfy = clamp((e.clientY - r.top) / r.height, -0.25, 1.25);
    }

    function heroScroll() {
      const h = hero!.offsetHeight || 1;
      sn = clamp(window.scrollY / h, 0, 1);
      if (inner) {
        inner.style.transform = `translateY(${sn * 70}px)`;
        inner.style.opacity = String(1 - sn * 1.1);
      }
    }

    const onThemeChange = () => {
      bg = readBg();
      light = readLight();
      drawMesh(performance.now()); // repaint with the new base colour + blend
    };
    const themeObserver = new MutationObserver(onThemeChange);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    // Read the media query directly (not Framer's hook): its hydration default
    // is "reduced", which would otherwise leave the animation loop unstarted.
    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const onResize = () => {
      initMesh();
      drawMesh(performance.now()); // setting canvas.width clears the bitmap — repaint
    };

    initMesh();
    heroScroll();
    drawMesh(performance.now()); // always paint at least one frame (static fallback)

    window.addEventListener("resize", onResize, { passive: true });
    window.addEventListener("scroll", heroScroll, { passive: true });

    if (animate) {
      window.addEventListener("mousemove", onMouseMove, { passive: true });
      raf = requestAnimationFrame(loop);
    }

    return () => {
      window.clearTimeout(loadedT);
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", heroScroll);
      window.removeEventListener("mousemove", onMouseMove);
      themeObserver.disconnect();
    };
  }, []);

  return (
    <header className="dqhero" id="hero" ref={heroRef}>
      <canvas className="dqhero-canvas" ref={canvasRef} aria-hidden="true" />
      <div className="dqhero-veil" aria-hidden="true" />
      <div className="dqhero-inner" ref={innerRef}>
        {children}
      </div>
    </header>
  );
}
