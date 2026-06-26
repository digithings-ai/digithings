"use client";
/**
 * Reactive "neural net" overlaid on the hero (item 14, v3).
 *
 * A spread-out network that GROWS toward the cursor: as the slow-following head
 * moves, it spawns new nodes with lateral spread and webs them by proximity, so
 * paths grow in the direction of motion while older nodes fade and collapse
 * behind — a living trail. There is no glow here: the single hue is the
 * HeroMesh behind it, which tracks the cursor at the same gradual pace, so the
 * shading trails the net. When the cursor is idle the head wanders gently so the
 * net keeps breathing. pointer-events: none; theme-aware; one static frame under
 * prefers-reduced-motion.
 */
import { useEffect, useRef } from "react";

type Node = { x: number; y: number; born: number };

const PAL_FALLBACK = ["61", "214", "196"];
const MAX = 70;
const MAX_AGE = 2600; // ms a node lives before it has fully collapsed
const DCON = 0.13; // connect radius, normalized to the smaller axis

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

    let W = 0;
    let H = 0;
    let nodes: Node[] = [];
    const head = { x: 0.5, y: 0.46 };
    const target = { x: 0.5, y: 0.46 };
    const lastSpawn = { x: 0.5, y: 0.46 };
    let vx = 0;
    let vy = 0;
    let lastMove = -1e9;

    const rnd = (a: number, b: number) => a + Math.random() * (b - a);

    function init() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      W = canvas!.clientWidth;
      H = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(W * dpr));
      canvas!.height = Math.max(1, Math.round(H * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function spawn(now: number) {
      const sp = Math.hypot(vx, vy) || 1e-6;
      const nx = -vy / sp;
      const ny = vx / sp; // unit perpendicular to motion → lateral spread
      const k = Math.min(0.055, Math.max(0.014, sp * 1.6));
      nodes.push({ x: head.x, y: head.y, born: now });
      nodes.push({ x: head.x + nx * rnd(0.25, 1) * k, y: head.y + ny * rnd(0.25, 1) * k, born: now });
      nodes.push({ x: head.x - nx * rnd(0.25, 1) * k, y: head.y - ny * rnd(0.25, 1) * k, born: now });
      if (nodes.length > MAX) nodes.splice(0, nodes.length - MAX);
    }

    const alphaOf = (n: Node, now: number) => {
      const a = (now - n.born) / MAX_AGE; // 0 (new) .. 1 (dead)
      const fin = Math.min(1, a / 0.08); // quick fade-in
      const fout = Math.min(1, (1 - a) / 0.4); // long fade-out (collapse)
      return Math.max(0, Math.min(fin, fout));
    };

    function frame(now: number) {
      // cursor when recently moved, else a slow autonomous wander
      if (now - lastMove > 700) {
        target.x = 0.5 + Math.sin(now * 0.00013) * 0.26;
        target.y = 0.45 + Math.cos(now * 0.00017) * 0.16;
      }
      const px = head.x;
      const py = head.y;
      head.x += (target.x - head.x) * 0.04; // slow, gradual tracking (was snappy)
      head.y += (target.y - head.y) * 0.04;
      vx = head.x - px;
      vy = head.y - py;
      if (Math.hypot(head.x - lastSpawn.x, head.y - lastSpawn.y) > 0.02) {
        spawn(now);
        lastSpawn.x = head.x;
        lastSpawn.y = head.y;
      }
      nodes = nodes.filter((n) => now - n.born < MAX_AGE);

      ctx!.clearRect(0, 0, W, H);
      const rgb = `${accent[0]},${accent[1]},${accent[2]}`;
      const baseA = light ? 0.6 : 0.72;

      ctx!.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        const ai = alphaOf(nodes[i], now);
        if (ai <= 0) continue;
        for (let j = i + 1; j < nodes.length; j++) {
          const aj = alphaOf(nodes[j], now);
          if (aj <= 0) continue;
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const d = Math.hypot(dx, dy);
          if (d < DCON) {
            ctx!.strokeStyle = `rgba(${rgb},${baseA * 0.55 * Math.min(ai, aj) * (1 - d / DCON)})`;
            ctx!.beginPath();
            ctx!.moveTo(nodes[i].x * W, nodes[i].y * H);
            ctx!.lineTo(nodes[j].x * W, nodes[j].y * H);
            ctx!.stroke();
          }
        }
      }
      for (const n of nodes) {
        const a = alphaOf(n, now);
        if (a <= 0) continue;
        ctx!.fillStyle = `rgba(${rgb},${baseA * a})`;
        ctx!.beginPath();
        ctx!.arc(n.x * W, n.y * H, 1.5, 0, 7);
        ctx!.fill();
      }
    }

    let raf = 0;
    function loop() {
      frame(performance.now());
      raf = requestAnimationFrame(loop);
    }

    function onMove(e: MouseEvent) {
      const r = canvas!.getBoundingClientRect();
      target.x = (e.clientX - r.left) / r.width;
      target.y = (e.clientY - r.top) / r.height;
      lastMove = performance.now();
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
      // one calm static frame: a small settled net near the centre
      const t = performance.now() - 500;
      for (let i = 0; i < 14; i++) nodes.push({ x: 0.5 + rnd(-0.2, 0.2), y: 0.45 + rnd(-0.12, 0.12), born: t });
      frame(performance.now());
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
