"use client";
/**
 * Reactive "neural orb" overlaid on the hero (item 14, v4).
 *
 * A contained OVAL cluster of interconnected nodes that sits centered on the
 * shading orb (HeroMesh hue) and tracks the cursor at the same gradual pace, so
 * the two move together. It is NOT a trail/snake — the cluster holds its shape
 * and rotates slowly. When the cursor is idle the orb stays where it was and
 * keeps cycling gently. No glow here (the mesh is the single hue).
 * pointer-events: none; theme-aware; one static frame under reduced-motion.
 */
import { useEffect, useRef } from "react";

type Node = { ang: number; rx: number; ry: number; breathe: number; phase: number };

const PAL_FALLBACK = ["61", "214", "196"];

export function HeroGraph() {
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
      const c = getComputedStyle(probe).color;
      probe.remove();
      const m = c.match(/[\d.]+/g);
      return m && m.length >= 3 ? [m[0], m[1], m[2]] : PAL_FALLBACK;
    };
    let accent = readAccent();
    let light = document.documentElement.getAttribute("data-theme") === "light";

    const N = 18;
    let W = 0;
    let H = 0;
    let RX = 0; // oval radii in px (wider than tall)
    let RY = 0;
    let nodes: Node[] = [];
    // centre tracks the cursor at the mesh's gradual pace; holds position when idle
    const c = { x: 0.5, y: 0.46, tx: 0.5, ty: 0.46 };

    const rnd = (a: number, b: number) => a + Math.random() * (b - a);

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      const m = Math.min(W, H);
      RX = m * 0.15;
      RY = m * 0.1;
      if (nodes.length !== N) {
        nodes = Array.from({ length: N }, (_, i) => ({
          ang: (i / N) * Math.PI * 2 + rnd(-0.18, 0.18),
          // mix of outer-shell and a few inner nodes → an orb, not just a ring
          rx: i % 4 === 0 ? rnd(0.2, 0.5) : rnd(0.7, 1),
          ry: i % 4 === 0 ? rnd(0.2, 0.5) : rnd(0.7, 1),
          breathe: 0.0005 + Math.random() * 0.0007,
          phase: Math.random() * 6.28,
        }));
      }
    }

    function draw(t: number) {
      // gradual ease toward the cursor (same feel as the mesh); idle → holds
      c.x += (c.tx - c.x) * 0.045;
      c.y += (c.ty - c.y) * 0.045;
      const cx = c.x * W;
      const cy = c.y * H;
      const spin = t * 0.00018; // slow global rotation → gentle idle cycling

      const px: number[] = [];
      const py: number[] = [];
      for (const n of nodes) {
        const a = n.ang + spin;
        const br = 0.9 + 0.1 * Math.sin(t * n.breathe + n.phase);
        px.push(cx + Math.cos(a) * n.rx * RX * br);
        py.push(cy + Math.sin(a) * n.ry * RY * br);
      }

      ctx!.clearRect(0, 0, W, H);
      const rgb = `${accent[0]},${accent[1]},${accent[2]}`;
      const baseA = light ? 0.6 : 0.72;
      const DCON = RX * 1.15; // contained webbing within the orb

      ctx!.lineWidth = 1;
      for (let i = 0; i < N; i++) {
        // spoke to centre
        ctx!.strokeStyle = `rgba(${rgb},${baseA * 0.22})`;
        ctx!.beginPath();
        ctx!.moveTo(cx, cy);
        ctx!.lineTo(px[i], py[i]);
        ctx!.stroke();
        for (let j = i + 1; j < N; j++) {
          const d = Math.hypot(px[i] - px[j], py[i] - py[j]);
          if (d < DCON) {
            ctx!.strokeStyle = `rgba(${rgb},${baseA * 0.45 * (1 - d / DCON)})`;
            ctx!.beginPath();
            ctx!.moveTo(px[i], py[i]);
            ctx!.lineTo(px[j], py[j]);
            ctx!.stroke();
          }
        }
      }
      for (let i = 0; i < N; i++) {
        ctx!.fillStyle = `rgba(${rgb},${baseA})`;
        ctx!.beginPath();
        ctx!.arc(px[i], py[i], 1.5, 0, 7);
        ctx!.fill();
      }
      ctx!.fillStyle = `rgba(${rgb},${baseA})`;
      ctx!.beginPath();
      ctx!.arc(cx, cy, 2.4, 0, 7);
      ctx!.fill();
    }

    let raf = 0;
    function loop(t: number) {
      draw(t);
      raf = requestAnimationFrame(loop);
    }

    function onMove(e: MouseEvent) {
      const r = canvas!.getBoundingClientRect();
      c.tx = (e.clientX - r.left) / r.width;
      c.ty = (e.clientY - r.top) / r.height;
    }
    const onTheme = () => {
      accent = readAccent();
      light = document.documentElement.getAttribute("data-theme") === "light";
    };
    const obs = new MutationObserver(onTheme);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onResize = () => init();

    init();
    window.addEventListener("resize", onResize, { passive: true });

    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate) {
      window.addEventListener("mousemove", onMove, { passive: true });
      raf = requestAnimationFrame(loop);
    } else {
      draw(0);
    }

    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousemove", onMove);
      obs.disconnect();
    };
  }, []);

  return <canvas className="dqhero-graph" ref={canvasRef} aria-hidden="true" />;
}
