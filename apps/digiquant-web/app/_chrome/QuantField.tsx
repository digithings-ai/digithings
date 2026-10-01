"use client";

import { useEffect, useRef } from "react";
import {
  applyTick,
  fetchHeroCandles,
  HERO_GRANULARITY_S,
  HERO_PRODUCTS,
  openHeroTicker,
  type FeedCandle,
} from "@/lib/live/hero-feed";
import { formatPrice } from "@/lib/live/market-bar";

/** Hero backdrop: a candlestick chart that fills the hero behind the wordmark.
 *
 *  Live path: a random one of BTC, ETH or SOL (USD) is picked on load. Real one-minute
 *  candles backfill the chart and the public price feed moves the forming candle, so
 *  the last candle, the price line and the label tick as trades arrive. Hovering shows
 *  the open, high, low and close of the candle under the pointer.
 *
 *  Fallback path: until the feed answers, when it fails, and under reduced motion
 *  (a static snapshot, no socket), the chart is a seeded random walk labelled
 *  "simulated". Simulated candles use index points, never prices.
 *
 *  Colours come from `color`, `--up`, `--down` and `--bg` on the canvas so it follows
 *  the theme. The draw loop only runs while the hero is on screen. */

const BODY = 7;
const GAP = 5;
const PITCH = BODY + GAP;
const AXIS_W = 72;
const STEP_MS = 1600;
const SLIDE_MS = 320;
const SIM_NAMES = ["SIM-A", "SIM-B", "SIM-C"] as const;

type Mode = "sim" | "live";

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
    const product = HERO_PRODUCTS[Math.floor(Math.random() * HERO_PRODUCTS.length)] ?? HERO_PRODUCTS[0];
    const simIndex = Math.floor(Math.random() * SIM_NAMES.length);
    const simName = SIM_NAMES[simIndex] ?? SIM_NAMES[0];

    const rand = mulberry32(0x51ad + simIndex * 977);
    let simClose = 100;
    let simT = 0;
    const nextSim = (): FeedCandle => {
      const o = simClose;
      const c = Math.max(40, o + (100 - o) * 0.04 + (rand() - 0.5) * 2.6);
      const h = Math.max(o, c) + rand() * 1.1;
      const l = Math.min(o, c) - rand() * 1.1;
      simClose = c;
      return { t: simT++, o, h, l, c };
    };

    let mode: Mode = "sim";
    let modeSince = 0;
    let ticking = false;
    let candles: FeedCandle[] = Array.from({ length: 400 }, nextSim);
    let shown = { ...candles[candles.length - 1] };
    let slideStart = 0;
    let scale = { lo: 0, hi: 1, ready: false };
    let pointer: { x: number; y: number } | null = null;
    let dpr = 1;
    let ink = "";
    let up = "";
    let down = "";
    let accent = "";
    let bg = "#000";
    let mono = "monospace";
    let lastStep = 0;
    let lastFrame = 0;
    let raf = 0;
    let visible = true;
    let disposed = false;

    const px = (v: number) => (mode === "live" ? formatPrice(v) : v.toFixed(2));
    const stamp = (k: FeedCandle) =>
      mode === "live" ? new Date(k.t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : `#${k.t}`;
    const name = () => (mode === "live" ? product : simName);

    const resetShown = (open: boolean) => {
      const k = candles[candles.length - 1];
      shown = open ? { t: k.t, o: k.o, h: k.o, l: k.o, c: k.o } : { ...k };
    };

    const readTheme = () => {
      const style = getComputedStyle(canvas);
      ink = style.color;
      up = style.getPropertyValue("--up").trim() || style.color;
      down = style.getPropertyValue("--down").trim() || style.color;
      bg = style.getPropertyValue("--bg").trim() || "#000";
      accent = style.accentColor && style.accentColor !== "auto" ? style.accentColor : style.color;
      mono = style.fontFamily || mono;
    };

    const resize = () => {
      const rect = host.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      readTheme();
    };

    const label = () => {
      if (mode === "sim") return `${simName} · simulated candles · not market data`;
      if (reduced) return `${product} · 1m candles · snapshot`;
      return ticking ? `live · ${product} · 1m candles` : `${product} · 1m candles · connecting`;
    };

    const draw = (now: number) => {
      const dt = lastFrame ? Math.min(100, now - lastFrame) : 16;
      lastFrame = now;
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      const axisX = w - AXIS_W;
      const cols = Math.max(1, Math.floor(axisX / PITCH));
      const view = candles.slice(-cols);
      const n = view.length;
      const last = candles[candles.length - 1];

      const follow = reduced ? 1 : 1 - Math.exp(-dt / (mode === "live" ? 140 : 420));
      shown.t = last.t;
      shown.c += (last.c - shown.c) * follow;
      shown.h += (Math.max(last.h, shown.c) - shown.h) * follow;
      shown.l += (Math.min(last.l, shown.c) - shown.l) * follow;
      shown.o = last.o;

      let lo = Infinity;
      let hi = -Infinity;
      for (let i = 0; i < n; i++) {
        const k = i === n - 1 ? shown : view[i];
        lo = Math.min(lo, k.l);
        hi = Math.max(hi, k.h);
      }
      const pad = (hi - lo || 1) * 0.1;
      const targetLo = lo - pad;
      const targetHi = hi + pad;
      const sf = reduced || !scale.ready ? 1 : 1 - Math.exp(-dt / 260);
      scale = { lo: scale.lo + (targetLo - scale.lo) * sf, hi: scale.hi + (targetHi - scale.hi) * sf, ready: true };

      const plotTop = h * 0.1;
      const plotBottom = h * 0.9;
      const y = (v: number) => plotBottom - ((v - scale.lo) / (scale.hi - scale.lo || 1)) * (plotBottom - plotTop);
      const valueAt = (py: number) => scale.lo + ((plotBottom - py) / (plotBottom - plotTop)) * (scale.hi - scale.lo);

      const slide = reduced ? 0 : PITCH * (1 - easeOut(Math.min(1, (now - slideStart) / SLIDE_MS)));
      const fade = reduced ? 1 : Math.min(1, (now - modeSince) / 500);

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.font = `10px ${mono}`;
      ctx.textBaseline = "middle";

      ctx.lineWidth = 1;
      ctx.strokeStyle = ink;
      ctx.fillStyle = ink;
      ctx.setLineDash([2, 4]);
      ctx.textAlign = "left";
      for (const f of [0.15, 0.35, 0.5, 0.65, 0.85]) {
        const gy = Math.round(plotBottom - f * (plotBottom - plotTop)) + 0.5;
        ctx.globalAlpha = 0.1;
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(axisX, gy);
        ctx.stroke();
        ctx.globalAlpha = 0.34 * fade;
        ctx.fillText(px(valueAt(gy)), axisX + 10, gy);
      }
      ctx.setLineDash([]);

      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, axisX, h);
      ctx.clip();
      for (let i = 0; i < n; i++) {
        const fresh = i === n - 1;
        const k = fresh ? shown : view[i];
        const x = Math.round(axisX - (n - i) * PITCH + slide);
        const rising = k.c >= k.o;
        ctx.fillStyle = rising ? up : down;
        ctx.globalAlpha = (fresh ? 0.95 : 0.4) * fade;
        const wickX = x + Math.floor(BODY / 2);
        ctx.fillRect(wickX, Math.round(y(k.h)), 1, Math.max(1, Math.round(y(k.l) - y(k.h))));
        const bodyTop = Math.round(y(Math.max(k.o, k.c)));
        ctx.fillRect(x, bodyTop, BODY, Math.max(2, Math.round(y(Math.min(k.o, k.c))) - bodyTop));
      }
      ctx.restore();

      const lastY = Math.round(y(shown.c)) + 0.5;
      const rising = shown.c >= shown.o;
      ctx.strokeStyle = rising ? up : down;
      ctx.fillStyle = rising ? up : down;
      ctx.globalAlpha = 0.55 * fade;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(0, lastY);
      ctx.lineTo(axisX, lastY);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.95 * fade;
      ctx.fillRect(axisX + 4, lastY - 8, AXIS_W - 8, 16);
      ctx.fillStyle = bg;
      ctx.fillText(px(shown.c), axisX + 10, lastY);

      const glow = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.min(w * 0.42, h * 0.78));
      glow.addColorStop(0, bg);
      glow.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.72;
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, h);

      ctx.globalAlpha = 0.5;
      ctx.fillStyle = ink;
      ctx.textAlign = "left";
      ctx.fillText(label(), 16, h - 18);

      if (pointer && pointer.x < axisX) {
        const idx = Math.min(n - 1, Math.max(0, Math.round((pointer.x - (axisX - n * PITCH + slide) - BODY / 2) / PITCH)));
        const k = idx === n - 1 ? shown : view[idx];
        const cx = Math.round(axisX - (n - idx) * PITCH + slide) + Math.floor(BODY / 2) + 0.5;
        ctx.globalAlpha = 0.3;
        ctx.strokeStyle = ink;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(cx, 0);
        ctx.lineTo(cx, h);
        ctx.moveTo(0, pointer.y + 0.5);
        ctx.lineTo(axisX, pointer.y + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.globalAlpha = 1;
        ctx.fillStyle = ink;
        ctx.fillRect(axisX + 4, pointer.y - 8, AXIS_W - 8, 16);
        ctx.fillStyle = bg;
        ctx.textAlign = "left";
        ctx.fillText(px(valueAt(pointer.y)), axisX + 10, pointer.y);

        const change = k.o ? ((k.c - k.o) / k.o) * 100 : 0;
        const head = `${name()} · ${mode === "live" ? `${HERO_GRANULARITY_S / 60}m ` : ""}${stamp(k)}`;
        const body = `O ${px(k.o)}  H ${px(k.h)}  L ${px(k.l)}  C ${px(k.c)}  ${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;
        ctx.font = `11px ${mono}`;
        const boxW = Math.ceil(Math.max(ctx.measureText(head).width, ctx.measureText(body).width)) + 20;
        const boxH = 44;
        const bx = Math.max(8, Math.min(axisX - boxW - 8, pointer.x + 18 > axisX - boxW - 8 ? pointer.x - boxW - 18 : pointer.x + 18));
        const by = Math.max(8, Math.min(h - boxH - 8, pointer.y + 18 > h - boxH - 8 ? pointer.y - boxH - 18 : pointer.y + 18));
        ctx.globalAlpha = 0.94;
        ctx.fillStyle = bg;
        ctx.fillRect(bx, by, boxW, boxH);
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = ink;
        ctx.strokeRect(bx + 0.5, by + 0.5, boxW - 1, boxH - 1);
        ctx.globalAlpha = 1;
        ctx.fillStyle = ink;
        ctx.textBaseline = "alphabetic";
        ctx.fillText(head, bx + 10, by + 17);
        ctx.fillStyle = k.c >= k.o ? up : down;
        ctx.fillText(body, bx + 10, by + 34);
        ctx.font = `10px ${mono}`;
        ctx.textBaseline = "middle";

        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = accent;
        ctx.strokeRect(cx - Math.floor(BODY / 2) - 2.5, y(k.h) - 2.5, BODY + 4, Math.max(6, y(k.l) - y(k.h)) + 5);
      }
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      if (mode === "sim" && !reduced) {
        if (!lastStep) lastStep = now;
        if (now - lastStep >= STEP_MS) {
          candles.shift();
          candles.push(nextSim());
          resetShown(true);
          slideStart = now;
          lastStep = now;
        }
      }
      draw(now);
      if (visible) raf = requestAnimationFrame(tick);
    };

    const redrawStatic = () => {
      if (reduced) draw(performance.now());
    };

    const onMove = (e: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      redrawStatic();
    };
    const onLeave = () => {
      pointer = null;
      redrawStatic();
    };

    resize();
    resetShown(false);
    modeSince = performance.now();
    if (reduced) draw(modeSince);
    else raf = requestAnimationFrame(tick);

    const abort = new AbortController();
    let stopTicker = () => {};
    void fetchHeroCandles(product, abort.signal)
      .then((history) => {
        if (disposed || history.length < 12) return;
        candles = history;
        mode = "live";
        modeSince = performance.now();
        scale = { ...scale, ready: false };
        resetShown(false);
        slideStart = modeSince;
        if (reduced) {
          draw(modeSince);
          return;
        }
        stopTicker = openHeroTicker(
          product,
          (price, sec) => {
            const before = candles[candles.length - 1]?.t;
            applyTick(candles, price, sec);
            if (candles[candles.length - 1].t !== before) {
              resetShown(true);
              slideStart = performance.now();
            }
          },
          (open) => {
            ticking = open;
          },
        );
      })
      .catch(() => {
        /* feed unreachable: the simulated series stays */
      });

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !reduced) {
        cancelAnimationFrame(raf);
        lastStep = 0;
        lastFrame = 0;
        raf = requestAnimationFrame(tick);
      }
    });
    io.observe(host);
    const ro = new ResizeObserver(() => {
      resize();
      redrawStatic();
    });
    ro.observe(host);
    host.addEventListener("pointermove", onMove);
    host.addEventListener("pointerleave", onLeave);
    return () => {
      disposed = true;
      abort.abort();
      stopTicker();
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
