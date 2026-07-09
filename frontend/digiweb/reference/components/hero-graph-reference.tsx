"use client";

/**
 * Reveal-field hero graph — the cursor-following node web from the digithings.ai
 * and digiquant.io landing heroes. A fixed field of nodes is scattered across
 * the frame; the cursor is a lens that lights up and webs together nearby nodes
 * while the trailing side dissolves. A faint ghost keeps a latent trace
 * everywhere. Reads the live --accent token (re-dresses per livery + theme);
 * one static centered frame under reduced motion. Verbatim behaviour from the
 * production HeroGraph, adapted to track the pointer within this demo frame.
 */
import { useEffect, useRef } from "react";

type Node = { hx: number; hy: number; ph: number; sp: number; amp: number; x: number; y: number; vis: number };

const PAL_FALLBACK = ["154", "160", "166"];
const N = 72;
const REVEAL = 0.55;
const GHOST = 0.06;
const EASE = 0.04;
const VIS_EASE = 0.05;

export function HeroGraphReference() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const readAccent = () => {
      const probe = document.createElement("span");
      probe.style.cssText = "color:var(--accent);position:absolute;left:-9999px";
      document.body.appendChild(probe);
      const col = getComputedStyle(probe).color;
      probe.remove();
      const m = col.match(/[\d.]+/g);
      return m && m.length >= 3 ? [m[0], m[1], m[2]] : PAL_FALLBACK;
    };
    let accent = readAccent();
    let light = document.documentElement.getAttribute("data-theme") === "light";

    const rnd = (a: number, b: number) => a + Math.random() * (b - a);
    const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
    const smooth = (e: number) => (e <= 0 ? 0 : e >= 1 ? 1 : e * e * (3 - 2 * e));

    let W = 0;
    let H = 0;
    let linkD = 120;
    let nodes: Node[] = [];
    const c = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };

    function build() {
      const cell = Math.sqrt((W * H) / N);
      const cols = Math.max(2, Math.round(W / cell));
      const rows = Math.max(2, Math.round(H / cell));
      const sx = W / cols;
      const sy = H / rows;
      linkD = Math.max(sx, sy) * 1.7;
      nodes = [];
      for (let r = 0; r < rows; r++) {
        for (let col = 0; col < cols; col++) {
          nodes.push({
            hx: (col + 0.5) * sx + rnd(-0.5, 0.5) * sx * 0.7,
            hy: (r + 0.5) * sy + rnd(-0.5, 0.5) * sy * 0.7,
            ph: Math.random() * 6.28,
            sp: rnd(0.0004, 0.001),
            amp: Math.min(sx, sy) * 0.16,
            x: 0,
            y: 0,
            vis: 0,
          });
        }
      }
    }

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      build();
    }

    function step(t: number, instant: boolean) {
      c.x += (c.tx - c.x) * EASE;
      c.y += (c.ty - c.y) * EASE;
      const cx = c.x * W;
      const cy = c.y * H;
      const R = REVEAL * Math.min(W, H);
      const fall = R * 0.85;
      for (const nd of nodes) {
        nd.x = nd.hx + Math.sin(t * nd.sp + nd.ph) * nd.amp;
        nd.y = nd.hy + Math.cos(t * nd.sp * 0.9 + nd.ph) * nd.amp;
        const d = Math.hypot(nd.x - cx, nd.y - cy);
        const target = GHOST + (1 - GHOST) * (1 - smooth((d - R) / fall));
        nd.vis += instant ? target - nd.vis : (target - nd.vis) * VIS_EASE;
      }

      const rgb = `${accent[0]},${accent[1]},${accent[2]}`;
      const baseA = light ? 0.62 : 0.78;
      ctx!.clearRect(0, 0, W, H);
      ctx!.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        if (a.vis < 0.04) continue;
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          if (b.vis < 0.04) continue;
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < linkD * linkD) {
            const d = Math.sqrt(d2);
            const al = (1 - d / linkD) * 0.5 * a.vis * b.vis * baseA;
            if (al > 0.012) {
              ctx!.strokeStyle = `rgba(${rgb},${al})`;
              ctx!.beginPath();
              ctx!.moveTo(a.x, a.y);
              ctx!.lineTo(b.x, b.y);
              ctx!.stroke();
            }
          }
        }
      }
      for (const nd of nodes) {
        if (nd.vis < 0.02) continue;
        ctx!.fillStyle = `rgba(${rgb},${baseA * nd.vis})`;
        ctx!.beginPath();
        ctx!.arc(nd.x, nd.y, 1.6, 0, 7);
        ctx!.fill();
      }
    }

    let raf = 0;
    function loop(t: number) {
      step(t, false);
      raf = requestAnimationFrame(loop);
    }

    // Track the pointer WITHIN this frame (the production hero tracks the whole
    // viewport; here the lens follows the cursor across the demo panel).
    function onMove(e: MouseEvent) {
      const r = canvas!.getBoundingClientRect();
      c.tx = clamp((e.clientX - r.left) / r.width, 0, 1);
      c.ty = clamp((e.clientY - r.top) / r.height, 0, 1);
    }
    const onTheme = () => {
      accent = readAccent();
      light = document.documentElement.getAttribute("data-theme") === "light";
    };
    const obs = new MutationObserver(onTheme);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onResize = () => {
      init();
      step(0, true);
    };

    init();

    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate) {
      step(0, true);
      canvas.addEventListener("mousemove", onMove, { passive: true });
      raf = requestAnimationFrame(loop);
    } else {
      step(0, true);
    }
    window.addEventListener("resize", onResize, { passive: true });

    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      canvas.removeEventListener("mousemove", onMove);
      obs.disconnect();
    };
  }, []);

  // .hg-canvas (positioning/sizing) migrates to Tailwind utilities; the
  // decorative canvas paints via the 2D context above, and its .hg-frame
  // wrapper (crosshair cursor, overflow clip) lives in the page markup + CSS.
  return (
    <canvas
      className="absolute inset-0 w-full h-full block pointer-events-none"
      ref={canvasRef}
      aria-hidden="true"
    />
  );
}
