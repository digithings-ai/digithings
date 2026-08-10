"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * ProductFrame — the "real surface, cropped" technique promoted from the
 * design reference (layout-patterns/product-frame): a product screenshot is
 * authored once on a FIXED artboard (800×300 by default), then scaled
 * proportionally to fit its container so it never reflows and stays
 * pixel-faithful at any width. CSS calc() can't derive a unitless scale from
 * lengths, so a ResizeObserver measures the container and writes the factor
 * straight to the node (no per-frame React state). With no JS the artboard
 * renders unscaled inside the overflow-hidden frame — a crop, never a break.
 * An optional overlay tag labels the crop. Content is children-driven.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/data-layout.css";
 *                 @source "<path-to>/digiweb/web/src/components/data-layout";
 */
export type ProductFrameProps = {
  /** Mono overlay tag naming the crop — "atlas · research". */
  tag?: string;
  /** Fixed artboard width the children are authored against (px). */
  artboardWidth?: number;
  /** Fixed artboard height — with width, sets the frame's aspect ratio (px). */
  artboardHeight?: number;
  className?: string;
  children: ReactNode;
};

export function ProductFrame({
  tag,
  artboardWidth = 800,
  artboardHeight = 300,
  className,
  children,
}: ProductFrameProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const artboardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const vp = viewportRef.current;
    const art = artboardRef.current;
    if (!vp || !art) return;
    const apply = (w: number) => {
      art.style.scale = String(Math.min(1, w / artboardWidth));
    };
    apply(vp.clientWidth);
    const ro = new ResizeObserver((entries) => apply(entries[0].contentRect.width));
    ro.observe(vp);
    return () => ro.disconnect();
  }, [artboardWidth]);

  return (
    <div
      className={`pf-viewport${className ? ` ${className}` : ""}`}
      ref={viewportRef}
      style={{ aspectRatio: `${artboardWidth} / ${artboardHeight}` }}
    >
      <div
        className="pf-artboard"
        ref={artboardRef}
        style={{ width: artboardWidth, height: artboardHeight }}
      >
        {children}
      </div>
      {tag ? <span className="pf-tag">{tag}</span> : null}
    </div>
  );
}
