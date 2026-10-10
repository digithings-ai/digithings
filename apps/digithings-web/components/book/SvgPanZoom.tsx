"use client";

/**
 * A book diagram in its own bounded viewport (DIG-2821).
 *
 * The figure is a box with `overflow: hidden`, and every interaction happens
 * inside it: the page never zooms and never scrolls because of a gesture made
 * over a diagram.
 *
 *  - pinch (trackpad pinch arrives as ctrl+wheel) and ctrl/cmd+wheel zoom
 *    around the pointer, always;
 *  - a plain wheel scrolls the PAGE until the reader clicks into the diagram,
 *    then zooms the diagram until Esc or a click outside — a long chapter must
 *    not trap the scroll wheel on every figure it passes;
 *  - drag pans, two-finger touch pinches, both clamped so the drawing cannot be
 *    thrown out of its box;
 *  - real buttons for zoom in, zoom out, reset and full screen, plus + / - / 0
 *    on the keyboard.
 *
 * The wheel listener is attached natively with `passive: false`. React's
 * `onWheel` is passive, so `preventDefault()` there is ignored and the browser
 * zooms or scrolls the page anyway — which is exactly the bug this replaced.
 *
 * Two files per diagram: the light and dark renders (scripts/book/
 * render-diagrams.mjs). Which one shows is decided by CSS on the page's
 * `data-theme` (lib/book/printCss.ts), so there is no hydration flash and print
 * always gets the light file.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const STEP = 1.25;

export interface SvgPanZoomProps {
  src: string;
  alt: string;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

const IDENTITY: View = { scale: 1, x: 0, y: 0 };

export function darkVariant(src: string): string {
  return src.replace(/\.svg$/, ".dark.svg");
}

/** Keep the scaled drawing covering the box: no panning it out of view. */
function clampView(v: View, w: number, h: number): View {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale));
  const minX = w - w * scale;
  const minY = h - h * scale;
  return { scale, x: Math.min(0, Math.max(minX, v.x)), y: Math.min(0, Math.max(minY, v.y)) };
}

export default function SvgPanZoom({ src, alt }: SvgPanZoomProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>(IDENTITY);
  const [active, setActive] = useState(false);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ view: View; x: number; y: number; dist: number } | null>(null);

  const apply = useCallback((next: (v: View) => View) => {
    const box = boxRef.current;
    if (!box) return;
    const { width, height } = box.getBoundingClientRect();
    setView((v) => clampView(next(v), width, height));
  }, []);

  /** Zoom by `factor` keeping the point (px, py), box-relative, fixed. */
  const zoomAt = useCallback(
    (factor: number, px?: number, py?: number) =>
      apply((v) => {
        const box = boxRef.current!.getBoundingClientRect();
        const cx = px ?? box.width / 2;
        const cy = py ?? box.height / 2;
        const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
        const k = scale / v.scale;
        return { scale, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
      }),
    [apply],
  );

  const reset = useCallback(() => setView(IDENTITY), []);

  // Native, non-passive wheel listener: the only way to stop the page zoom.
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const onWheel = (e: WheelEvent) => {
      const pinch = e.ctrlKey || e.metaKey;
      if (!pinch && !active) return; // let the page scroll
      e.preventDefault();
      e.stopPropagation();
      const r = box.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * (pinch ? 0.01 : 0.002));
      zoomAt(factor, e.clientX - r.left, e.clientY - r.top);
    };
    box.addEventListener("wheel", onWheel, { passive: false });
    return () => box.removeEventListener("wheel", onWheel);
  }, [active, zoomAt]);

  // Deactivate on a click anywhere outside the figure.
  useEffect(() => {
    if (!active) return;
    const off = (e: PointerEvent) => {
      if (!boxRef.current?.parentElement?.contains(e.target as Node)) setActive(false);
    };
    document.addEventListener("pointerdown", off);
    return () => document.removeEventListener("pointerdown", off);
  }, [active]);

  const onPointerDown = (e: React.PointerEvent) => {
    setActive(true);
    boxRef.current?.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    startGesture();
  };
  const startGesture = () => {
    const pts = [...pointers.current.values()];
    if (pts.length === 0) return (gesture.current = null);
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    const dist = pts.length > 1 ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0;
    gesture.current = { view, x: cx, y: cy, dist };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!pointers.current.has(e.pointerId) || !gesture.current) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    const pts = [...pointers.current.values()];
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    let scale = g.view.scale;
    if (pts.length > 1 && g.dist > 0) {
      scale = g.view.scale * (Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) / g.dist);
    }
    const r = boxRef.current!.getBoundingClientRect();
    const ox = g.x - r.left;
    const oy = g.y - r.top;
    const k = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale)) / g.view.scale;
    apply(() => ({
      scale: g.view.scale * k,
      x: ox - (ox - g.view.x) * k + (cx - g.x),
      y: oy - (oy - g.view.y) * k + (cy - g.y),
    }));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    startGesture();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "+" || e.key === "=") zoomAt(STEP);
    else if (e.key === "-") zoomAt(1 / STEP);
    else if (e.key === "0") reset();
    else if (e.key === "Escape") setActive(false);
    else return;
    e.preventDefault();
  };

  const fullscreen = () => {
    const fig = boxRef.current?.parentElement;
    if (!fig) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void fig.requestFullscreen?.().then(reset);
  };

  const transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  const btn = "border border-hair px-2 py-0.5 font-mono text-[0.75rem] text-ink-soft";

  return (
    <figure className="book-figure my-8" data-book-diagram="">
      <div
        ref={boxRef}
        role="img"
        aria-label={alt}
        tabIndex={0}
        data-active={active ? "" : undefined}
        className="book-figure__viewport relative overflow-hidden border border-hair"
        style={{ touchAction: "none", overscrollBehavior: "contain", cursor: view.scale > 1 ? "grab" : "zoom-in" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(e) => {
          const r = boxRef.current!.getBoundingClientRect();
          zoomAt(2, e.clientX - r.left, e.clientY - r.top);
        }}
        onKeyDown={onKeyDown}
      >
        <div style={{ transform, transformOrigin: "0 0", willChange: "transform" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="book-figure__light block w-full select-none" src={src} alt="" draggable={false} />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="book-figure__dark block w-full select-none" src={darkVariant(src)} alt="" draggable={false} />
        </div>
      </div>
      <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 font-mono text-[0.75rem] text-ink-soft">
        <span>{alt}</span>
        <span className="book-screen-only inline-flex gap-2">
          <button type="button" className={btn} style={{ cursor: "pointer" }} onClick={() => zoomAt(STEP)} aria-label="zoom in">+</button>
          <button type="button" className={btn} style={{ cursor: "pointer" }} onClick={() => zoomAt(1 / STEP)} aria-label="zoom out">−</button>
          <button type="button" className={btn} style={{ cursor: "pointer" }} onClick={reset}>reset</button>
          <button type="button" className={btn} style={{ cursor: "pointer" }} onClick={fullscreen}>full screen</button>
        </span>
      </figcaption>
    </figure>
  );
}
