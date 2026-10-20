"use client";

/**
 * A figure inside a chapter body (DIG-2821).
 *
 * The book's diagrams are the only images that carry the pan-and-zoom
 * interaction, and they are identified by their address, not by a marker in
 * the source: any `src` under `/book/diagrams/` is one. That keeps the rule in
 * one place, so a chapter cannot get a diagram that is quietly missing its
 * interaction, and a prose illustration is not given one it does not want.
 *
 * Anything else renders as a plain `<img>`, because an unknown remote image has
 * nothing to pan.
 */
import SvgPanZoom, { type SvgPanZoomProps } from "./SvgPanZoom";
import { DIAGRAM_URL_PREFIX } from "@/lib/book/diagramPaths.ts";

export interface BookFigureProps {
  src?: string;
  alt?: string;
  title?: string;
}

export default function BookFigure({ src = "", alt = "" }: BookFigureProps) {
  if (src.startsWith(DIAGRAM_URL_PREFIX)) {
    return <SvgPanZoom src={src} alt={alt} />;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="my-6 w-full" src={src} alt={alt} />;
}

export type { SvgPanZoomProps };
