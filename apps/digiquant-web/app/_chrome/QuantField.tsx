"use client";

import { useEffect, useRef } from "react";

/** Hero backdrop: an illustrative candlestick chart along the bottom of the hero,
 *  with a dashed crosshair that follows the pointer anywhere in the hero. Candles
 *  advance: every few seconds the chart slides one place left and a new candle
 *  forms on the right (body and wicks grow from the open to the close). The series
 *  is a seeded random walk, not market data, and the chart says so. Colours come
 *  from `color`, `--up` and `--down` on the canvas so it follows the theme. Static
 *  frame under reduced motion; the loop only runs while the hero is on screen. */

const BODY = 9;
const GAP = 6;
const PITCH = BODY + GAP;
const STEP_MS = 1600;
const SLIDE_MS = 300;
const CHART_H = 200;
const LABEL_PAD = 26;

type Candle = { o: number; c: number; h: number; l: number };

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

export function QuantField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const host = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !host || !ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rand = mulberry32(0x51ad);
    let last = 0.5;
    const nextCandle = (): Candle => {
      const o = last;
      const drift = (0.5 - o) * 0.12;
      const c = Math.min(0.94, Math.max(0.1, o + drift + (rand() - 0.5) * 0.24));
      const h = Math.min(1, Math.max(o, c) + rand() * 0.09);
      const l = Math.max(0, Math.min(o, c) - rand() * 0.09);
      last = c;
      return { o, c, h, l };
    };

    const candles: Candle[] = [];
    let cols = 0;
    let dpr = 1;
    let ink = "";
    let up = "";
    let down = "";
    let accent = "";
    let mono = "monospace";
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
      cols = Math.ceil(rect.width / PITCH) + 1;
      while (candles.length < cols) candles.push(nextCandle());
      candles.length = cols;
      const style = getComputedStyle(canvas);
      ink = style.color;
      up = style.getPropertyValue("--up").trim() || style.color;
      down = style.getPropertyValue("--down").trim() || style.color;
      accent = style.accentColor && style.accentColor !== "auto" ? style.accentColor : style.color;
      mono = style.fontFamily || mono;
    };

    const draw = (now: number) => {
      const elapsed = now - start;
      const sinceStep = reduced ? STEP_MS : now - lastStep;
      const slide = reduced ? 0 : PITCH * (1 - easeOut(Math.min(1, sinceStep / SLIDE_MS)));
      const forming = reduced ? 1 : easeOut(Math.min(1, sinceStep / (STEP_MS * 0.85)));
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const base = h - 1;
      const top = base - CHART_H;
      const plot = CHART_H - LABEL_PAD;
      const y = (v: number) => Math.round(base - v * plot);

      ctx.lineWidth = 1;
      ctx.strokeStyle = ink;
      ctx.globalAlpha = 0.12;
      ctx.setLineDash([2, 4]);
      for (const f of [0.25, 0.5, 0.75, 1]) {
        const gy = y(f) + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(w, gy);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.35;
      ctx.beginPath();
      ctx.moveTo(0, base + 0.5);
      ctx.lineTo(w, base + 0.5);
      ctx.stroke();

      for (let i = 0; i < cols; i++) {
        const fresh = i === cols - 1;
        const k = candles[i];
        const grown = reduced ? 1 : Math.min(1, Math.max(0, (elapsed - i * 12) / 500));
        const o = k.o;
        const c = fresh ? o + (k.c - o) * forming : k.c;
        const hi = fresh ? Math.max(o, c) + (k.h - Math.max(o, k.c)) * forming : k.h;
        const lo = fresh ? Math.min(o, c) - (Math.min(o, k.c) - k.l) * forming : k.l;
        const x = Math.round(i * PITCH + slide);
        const rising = c >= o;
        ctx.fillStyle = rising ? up : down;
        ctx.globalAlpha = (fresh ? 0.95 : 0.5) * grown;
        const wickX = x + Math.floor(BODY / 2);
        ctx.fillRect(wickX, y(hi), 1, Math.max(1, y(lo) - y(hi)));
        const bodyTop = y(Math.max(o, c));
        ctx.fillRect(x, bodyTop, BODY, Math.max(2, y(Math.min(o, c)) - bodyTop));
      }

      ctx.globalAlpha = 0.5;
      ctx.fillStyle = ink;
      ctx.font = `10px ${mono}`;
      ctx.textBaseline = "top";
      ctx.textAlign = "left";
      ctx.fillText("candles · illustrative series, not market data", 0, top);

      if (pointer) {
        ctx.globalAlpha = 0.28;
        ctx.strokeStyle = ink;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(pointer.x + 0.5, 0);
        ctx.lineTo(pointer.x + 0.5, h);
        ctx.moveTo(0, pointer.y + 0.5);
        ctx.lineTo(w, pointer.y + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = accent;
        ctx.strokeRect(Math.floor(pointer.x / PITCH) * PITCH - 1, Math.floor(pointer.y / PITCH) * PITCH - 1, PITCH - 1, PITCH - 1);
      }
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      if (!lastStep) lastStep = now;
      if (now - lastStep >= STEP_MS) {
        candles.shift();
        candles.push(nextCandle());
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

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="absolute inset-0 -z-10 h-full w-full font-mono text-ink [accent-color:var(--accent)]"
    />
  );
}
