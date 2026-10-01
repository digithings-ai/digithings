"use client";

import { useEffect, useRef } from "react";

/** Hero backdrop: a plain volume-style bar chart along the bottom of the hero.
 *  Flat-topped bars on a baseline, hairline gridlines and a label that says what
 *  it is. The bars grow in left to right, then a new bar arrives from the right
 *  every few seconds. The series is a seeded random walk, not market data, and
 *  the chart says so. Hovering a bar highlights it. Colours come from `color` /
 *  `accent-color` on the canvas so it follows the theme. Static frame under
 *  reduced motion; the loop only runs while the hero is on screen. */

const BAR = 10;
const GAP = 4;
const PITCH = BAR + GAP;
const STEP_MS = 1400;
const CHART_H = 132;
const LABEL_PAD = 22;

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function QuantField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const host = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !host || !ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rand = mulberry32(0x51ad);
    let level = 0.5;
    const nextBar = () => {
      level = Math.min(0.96, Math.max(0.12, level + (rand() - 0.5) * 0.4));
      return level;
    };

    const values: number[] = [];
    let cols = 0;
    let dpr = 1;
    let ink = "";
    let accent = "";
    let mono = "monospace";
    let hover = -1;
    let start = 0;
    let lastStep = 0;
    let raf = 0;
    let visible = true;

    const resize = () => {
      const rect = host.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      cols = Math.ceil(rect.width / PITCH) + 1;
      while (values.length < cols) values.push(nextBar());
      values.length = cols;
      const style = getComputedStyle(canvas);
      ink = style.color;
      accent = style.accentColor && style.accentColor !== "auto" ? style.accentColor : style.color;
      mono = style.fontFamily || mono;
    };

    const draw = (now: number) => {
      const elapsed = now - start;
      const shift = reduced ? 0 : Math.min(1, (now - lastStep) / STEP_MS) * PITCH;
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const base = h - 1;
      const top = base - CHART_H;
      const plot = CHART_H - LABEL_PAD;

      ctx.lineWidth = 1;
      ctx.strokeStyle = ink;
      ctx.globalAlpha = 0.12;
      ctx.setLineDash([2, 4]);
      for (const f of [0.5, 1]) {
        const y = Math.round(base - plot * f) + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.35;
      ctx.beginPath();
      ctx.moveTo(0, base + 0.5);
      ctx.lineTo(w, base + 0.5);
      ctx.stroke();

      for (let c = 0; c < cols; c++) {
        const grown = reduced ? 1 : Math.min(1, Math.max(0, (elapsed - c * 14) / 600));
        const eased = 1 - Math.pow(1 - grown, 3);
        const barH = Math.max(2, Math.round(values[c] * plot * eased));
        const x = Math.round(c * PITCH - shift);
        const latest = c >= cols - 2;
        ctx.fillStyle = latest || c === hover ? accent : ink;
        ctx.globalAlpha = latest || c === hover ? 0.85 : 0.26;
        ctx.fillRect(x, base - barH, BAR, barH);
      }

      ctx.globalAlpha = 0.5;
      ctx.fillStyle = ink;
      ctx.font = `10px ${mono}`;
      ctx.textBaseline = "top";
      ctx.textAlign = "left";
      ctx.fillText("volume · illustrative bars, not market data", 0, top);
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      if (!lastStep) lastStep = now;
      if (now - lastStep >= STEP_MS) {
        values.shift();
        values.push(nextBar());
        lastStep = now;
      }
      draw(now);
      if (visible) raf = requestAnimationFrame(tick);
    };

    const onMove = (e: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      hover = y > rect.height - CHART_H ? Math.floor(x / PITCH) : -1;
      if (reduced) draw(performance.now());
    };
    const onLeave = () => {
      hover = -1;
      if (reduced) draw(performance.now());
    };

    resize();
    start = performance.now();
    lastStep = 0;
    if (reduced) draw(start);
    else raf = requestAnimationFrame(tick);

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !reduced) {
        cancelAnimationFrame(raf);
        lastStep = 0;
        raf = requestAnimationFrame(tick);
      }
    });
    io.observe(host);
    const ro = new ResizeObserver(() => {
      resize();
      if (reduced) draw(performance.now());
    });
    ro.observe(host);
    host.addEventListener("pointermove", onMove);
    host.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="absolute inset-0 -z-10 h-full w-full font-mono text-ink [accent-color:var(--accent)]"
    />
  );
}
