"use client";
/**
 * Reactive "neural mass" overlaid on the hero (item 14).
 *
 * A single dense core of interconnected nodes — a living neural graph — that
 * eases toward the cursor and, while moving, stretches and scales along the
 * direction of motion (with a teal hue that expands with it). At rest it settles
 * into a compact, slowly-breathing mass near the centre. Layered above the mesh
 * veil, below the headline (pointer-events: none). Theme-aware (teal accent,
 * re-read on a data-theme change) and motion-safe: under prefers-reduced-motion
 * it paints one calm static frame at the centre.
 */
import { useEffect, useRef } from "react";

type Node = { ang: number; rad: number; spin: number; breathe: number; phase: number };

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

    const N = 22;
    let W = 0;
    let H = 0;
    let R = 0; // base mass radius in px (scales with viewport)
    let nodes: Node[] = [];

    // core eases toward the cursor; velocity drives the directional stretch
    const core = { x: 0.5, y: 0.46, tx: 0.5, ty: 0.46, vx: 0, vy: 0 };

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      R = Math.min(W, H) * 0.17;
      if (nodes.length !== N) {
        nodes = Array.from({ length: N }, (_, i) => ({
          // a denser core (small radius) ringed by a looser shell
          ang: (i / N) * Math.PI * 2 + Math.random() * 0.5,
          rad: (i % 3 === 0 ? 0.25 : 0.6 + Math.random() * 0.55),
          spin: (Math.random() - 0.5) * 0.0009,
          breathe: 0.0006 + Math.random() * 0.0008,
          phase: Math.random() * 6.28,
        }));
      }
    }

    function draw(t: number) {
      ctx!.clearRect(0, 0, W, H);

      const prevx = core.x;
      const prevy = core.y;
      core.x += (core.tx - core.x) * 0.07;
      core.y += (core.ty - core.y) * 0.07;
      // smoothed velocity (normalized units/frame)
      core.vx = core.vx * 0.8 + (core.x - prevx) * 0.2;
      core.vy = core.vy * 0.8 + (core.y - prevy) * 0.2;
      const speed = Math.hypot(core.vx, core.vy);
      const dirAng = Math.atan2(core.vy, core.vx);
      // stretch along motion, gentle squash across it; scale the whole mass up a touch
      const stretch = Math.min(speed * 26, 1.5);
      const along = 1 + stretch;
      const across = 1 / (1 + stretch * 0.35);
      const scale = 1 + Math.min(speed * 10, 0.5);
      const cos = Math.cos(dirAng);
      const sin = Math.sin(dirAng);

      const cx = core.x * W;
      const cy = core.y * H;
      const rgb = `${accent[0]},${accent[1]},${accent[2]}`;
      const baseA = light ? 0.62 : 0.7;

      // positions of each node, anisotropically stretched in the motion direction
      const px: number[] = [];
      const py: number[] = [];
      for (const n of nodes) {
        const a = n.ang + t * n.spin;
        const r = n.rad * R * scale * (0.85 + 0.15 * Math.sin(t * n.breathe + n.phase));
        // offset in mass-local axes (ox along motion, oy across)
        let ox = Math.cos(a) * r;
        let oy = Math.sin(a) * r;
        ox *= along;
        oy *= across;
        // rotate local axes into the motion direction
        px.push(cx + ox * cos - oy * sin);
        py.push(cy + ox * sin + oy * cos);
      }

      // hue: a soft radial glow centred on the mass, expanding with motion
      const glowR = R * scale * (1.7 + stretch * 0.6);
      const g = ctx!.createRadialGradient(cx, cy, 0, cx, cy, glowR);
      g.addColorStop(0, `rgba(${rgb},${light ? 0.2 : 0.22})`);
      g.addColorStop(1, `rgba(${rgb},0)`);
      ctx!.fillStyle = g;
      ctx!.beginPath();
      ctx!.arc(cx, cy, glowR, 0, 7);
      ctx!.fill();

      // edges: each node to the core, plus near-neighbour webbing → a neural mass
      ctx!.lineWidth = 1;
      for (let i = 0; i < N; i++) {
        ctx!.strokeStyle = `rgba(${rgb},${baseA * 0.32})`;
        ctx!.beginPath();
        ctx!.moveTo(cx, cy);
        ctx!.lineTo(px[i], py[i]);
        ctx!.stroke();
        for (let j = i + 1; j < N; j++) {
          const d = Math.hypot(px[i] - px[j], py[i] - py[j]);
          if (d < R * 0.95) {
            ctx!.strokeStyle = `rgba(${rgb},${baseA * 0.5 * (1 - d / (R * 0.95))})`;
            ctx!.beginPath();
            ctx!.moveTo(px[i], py[i]);
            ctx!.lineTo(px[j], py[j]);
            ctx!.stroke();
          }
        }
      }

      // nodes
      for (let i = 0; i < N; i++) {
        ctx!.fillStyle = `rgba(${rgb},${baseA})`;
        ctx!.beginPath();
        ctx!.arc(px[i], py[i], 1.6, 0, 7);
        ctx!.fill();
      }
      // bright core
      ctx!.fillStyle = `rgba(${rgb},${baseA})`;
      ctx!.beginPath();
      ctx!.arc(cx, cy, 2.6, 0, 7);
      ctx!.fill();
    }

    let raf = 0;
    function loop(t: number) {
      draw(t);
      raf = requestAnimationFrame(loop);
    }

    function onMove(e: MouseEvent) {
      const r = canvas!.getBoundingClientRect();
      core.tx = (e.clientX - r.left) / r.width;
      core.ty = (e.clientY - r.top) / r.height;
    }
    const onTheme = () => {
      accent = readAccent();
      light = document.documentElement.getAttribute("data-theme") === "light";
      draw(performance.now());
    };
    const obs = new MutationObserver(onTheme);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onResize = () => {
      init();
      draw(performance.now());
    };

    init();
    draw(performance.now());
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

  return <canvas className="dqhero-graph" ref={canvasRef} aria-hidden="true" />;
}
