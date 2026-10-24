"use client";

/**
 * A figure inside a chapter body (DIG-2821, U17).
 *
 * The book's diagrams are the only images that carry the pan-and-zoom
 * interaction, and they are identified by their address, not by a marker in
 * the source: any `src` under `/book/diagrams/` is one. That keeps the rule in
 * one place, so a chapter cannot get a diagram that is quietly missing its
 * interaction, and a prose illustration is not given one it does not want.
 *
 * Anything else renders as a plain image inside a real `<figure>`, with its
 * `title` as the caption. Markdown's `![alt](src "caption")` used to arrive as
 * a `title` attribute nobody rendered, which is a caption lost silently.
 */
import SvgPanZoom from "./SvgPanZoom";
import { DIAGRAM_URL_PREFIX } from "@/lib/book/diagramPaths.ts";

export interface BookFigureProps {
  src?: string;
  alt?: string;
  title?: string;
  width?: number | string;
  height?: number | string;
}

export default function BookFigure({ src = "", alt = "", title, width, height }: BookFigureProps) {
  if (src.startsWith(DIAGRAM_URL_PREFIX)) {
    // SvgPanZoom renders its own <figure> and <figcaption> (the alt text).
    return <SvgPanZoom src={src} alt={alt} />;
  }
  return (
    <figure className="my-8">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="block h-auto w-full border-hair border"
        src={src}
        alt={alt}
        width={width}
        height={height}
        loading="lazy"
        decoding="async"
      />
      {title ? <figcaption className="mt-2 font-mono text-[0.72rem] text-ink-soft">{title}</figcaption> : null}
    </figure>
  );
}
