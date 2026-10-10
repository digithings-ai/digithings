"use client";

/**
 * Pan and zoom for a book's diagram (DIG-2821).
 *
 * The image is always a plain `<img src="/book/diagrams/<id>.svg">`. This adds
 * the interaction on top of it and never replaces it: with no script, or with
 * the interaction closed, what remains is the same image the PDF prints. That
 * is the whole reason the diagrams are static files rather than a live render.
 *
 * Implemented with transforms on a wrapper rather than a pan/zoom library:
 * the surface is one image, and a dependency for drag plus wheel on one
 * element is a dependency that has to be audited for the rest of its life.
 *
 * Controls are real `<button>`s, so the control is reachable by keyboard. The
 * pointer affordance lives in a style attribute rather than a `cursor-*`
 * utility — `scripts/check_frontend_canon.py` rejects app-local cursor
 * utilities outside the reference gallery.
 */
import { useCallback, useRef, useState } from "react";

const MIN_SCALE = 1;
const MAX_SCALE = 6;

export interface SvgPanZoomProps {
  src: string;
  alt: string;
}

export default function SvgPanZoom({ src, alt }: SvgPanZoomProps) {
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const clamp = useCallback((next: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, next)), []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!open) return;
    setScale((s) => clamp(s + (e.deltaY < 0 ? 0.25 : -0.25)));
  }, [clamp, open]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (!open) return;
    drag.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }, [offset.x, offset.y, open]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setOffset({ x: d.ox + (e.clientX - d.x), y: d.oy + (e.clientY - d.y) });
  }, []);

  const onPointerUp = useCallback(() => {
    drag.current = null;
  }, []);

  const reset = useCallback(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setOpen(false);
  }, []);

  return (
    <figure className="my-8">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="block w-full text-left"
        style={{ cursor: open ? "zoom-out" : "zoom-in" }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          className="w-full"
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: open ? "none" : "transform 120ms ease-out",
          }}
          onWheel={open ? onWheel : undefined}
          onPointerDown={open ? onPointerDown : undefined}
          onPointerMove={open ? onPointerMove : undefined}
          onPointerUp={open ? onPointerUp : undefined}
        />
      </button>
      <figcaption className="font-mono text-[0.75rem] text-ink-soft">
        {open ? (
          <span className="inline-flex gap-3">
            <button type="button" onClick={() => setScale((s) => clamp(s + 0.5))} style={{ cursor: "pointer" }}>
              zoom in
            </button>
            <button type="button" onClick={() => setScale((s) => clamp(s - 0.5))} style={{ cursor: "pointer" }}>
              zoom out
            </button>
            <button type="button" onClick={reset} style={{ cursor: "pointer" }}>
              close
            </button>
          </span>
        ) : (
          <span>select the figure to pan and zoom</span>
        )}
      </figcaption>
    </figure>
  );
}
