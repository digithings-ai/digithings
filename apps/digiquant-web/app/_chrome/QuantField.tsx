"use client";

import { useEffect, useRef } from "react";

/** Hero backdrop: a boxy, abstract price panel on canvas. Volume-style columns
 *  of square cells grow in left to right, a stepped line in the accent streams
 *  leftward as new points arrive, and a crosshair follows the pointer. It is
 *  decoration: no axes, no labels, no numbers, and the series is a seeded random
 *  walk, not market data. Colours come from `color` / `accent-color` on the
 *  canvas so it follows the theme. Static frame under reduced motion; the loop
 *  only runs while the hero is on screen. */

const PITCH = 16;
const STEP_MS = 850;

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
    let price = 0.5;
    const nextPrice = () => {
      price = Math.min(0.95, Math.max(0.05, price + (rand() - 0.47) * 0.2));
      return price;
    };
    const nextVolume = () => 0.12 + rand() * rand() * 0.88;

    let cols = 0;
    let rows = 0;
    let dpr = 1;
    const prices: number[] = [];
    const volumes: number[] = [];
    let ink = "";
    let accent = "";
    let pointer: { x: number; y: number } | null = null;
    let start = 0;
    let lastStep = 0;
    let raf = 0;
    let visible = true;

    const resize = () => {
      const rect = host.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      cols = Math.ceil(rect.width / PITCH) + 2;
      rows = Math.ceil(rect.height / PITCH);
      while (prices.length < cols) prices.push(nextPrice());
      while (volumes.length < cols) volumes.push(nextVolume());
      prices.length = cols;
      volumes.length = cols;
      const style = getComputedStyle(canvas);
      ink = style.color;
      accent = style.accentColor && style.accentColor !== "auto" ? style.accentColor : style.color;
    };

    const draw = (now: number) => {
      const elapsed = now - start;
      const shift = reduced ? 0 : Math.min(1, (now - lastStep) / STEP_MS) * PITCH;
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const cell = PITCH - 3;
      const half = PITCH / 2;
      // The chart lives in a strip along the bottom of the hero (9 cells tall) so
      // it never runs behind the wordmark or copy.
      const strip = Math.min(rows, 9);
      const lineRows = strip * 0.6;
      const lineTop = rows - strip + 1;

      for (let c = 0; c < cols; c++) {
        const grown = reduced ? 1 : Math.min(1, Math.max(0, (elapsed - c * 18) / 700));
        const eased = 1 - Math.pow(1 - grown, 3);
        const x = c * PITCH - shift;
        const stack = Math.round(volumes[c] * strip * 0.4 * eased);
        ctx.fillStyle = ink;
        ctx.globalAlpha = 0.09;
        for (let r = 0; r < stack; r++) ctx.fillRect(x, h - (r + 1) * PITCH, cell, cell);
        const py = Math.round(lineTop + (1 - prices[c]) * lineRows) * PITCH;
        ctx.fillStyle = accent;
        ctx.globalAlpha = 0.85 * eased;
        ctx.fillRect(x, py, cell, cell);
        if (c > 0) {
          const prev = Math.round(lineTop + (1 - prices[c - 1]) * lineRows) * PITCH;
          const top = Math.min(py, prev) + cell;
          const gap = Math.abs(py - prev) - cell;
          if (gap > 0) {
            ctx.globalAlpha = 0.35 * eased;
            ctx.fillRect(x - 3 + half - 1, top, 2, gap + 3);
          }
        }
      }

      if (pointer) {
        ctx.globalAlpha = 0.28;
        ctx.strokeStyle = ink;
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pointer.x + 0.5, 0);
        ctx.lineTo(pointer.x + 0.5, h);
        ctx.moveTo(0, pointer.y + 0.5);
        ctx.lineTo(w, pointer.y + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = accent;
        ctx.strokeRect(Math.floor(pointer.x / PITCH) * PITCH - 1, Math.floor(pointer.y / PITCH) * PITCH - 1, cell + 2, cell + 2);
      }
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      if (!lastStep) lastStep = now;
      if (now - lastStep >= STEP_MS) {
        prices.shift();
        volumes.shift();
        prices.push(nextPrice());
        volumes.push(nextVolume());
        lastStep = now;
      }
      draw(now);
      if (visible) raf = requestAnimationFrame(tick);
    };

    const onMove = (e: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      if (reduced) draw(performance.now());
    };
    const onLeave = () => {
      pointer = null;
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

  return <canvas ref={ref} aria-hidden="true" className="absolute inset-0 -z-10 h-full w-full text-ink [accent-color:var(--accent)]" />;
}
