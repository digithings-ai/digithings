/**
 * The settled mark, in a form the server can paint.
 *
 * The web port draws a banner into a canvas on mount, so a server render and
 * a no-JS page show an empty box where the old SVG carried the settled
 * wordmark. This module renders the same settled frame the terminal draws
 * (`still`), so the fallback is the mark itself and not an approximation.
 *
 * The shape travels as a CSS mask and the colour as a plain CSS value
 * (`var(--ink)` for a themed tone, the tone hex otherwise). A data-URI SVG is
 * its own document: it cannot read `var(--ink)` or `currentColor` from the
 * host, so a baked hex would draw the mark in the wrong colour in the light
 * theme.
 */
import { sampleBanner } from "./engine";
import type { BannerDefinition, Frame } from "./types";

/** Options for the settled fallback. `gap` matches the canvas gap. */
export type SettledOptions = { gap?: number };

/** How the fallback has to be applied. */
export type SettledKind = "mask" | "image";

/** A server-renderable version of the settled mark. */
export type SettledFallback = {
  /** CSS colour of the mark: `var(--ink)` for a themed tone, the hex otherwise. */
  color: string;
  /** `mask` = the shape is a mask and the colour comes from CSS. `image` = the shape carries its own colours. */
  kind: SettledKind;
  /** `url("data:image/svg+xml,…")`, ready for `mask-image` or `background-image`. */
  url: string;
  /** True when the settled frame needs more than one colour. */
  multiTone: boolean;
};

type Run = { x: number; y: number; w: number };
type Group = { color: string; hex: string | null; alpha: number; runs: Run[] };

function toneOf(def: BannerDefinition, name: string): { css: string | null; hex: string | null } {
  const tone = (def.palette as Record<string, { hex?: string; cssVar?: string } | undefined>)[name];
  if (!tone) return { css: null, hex: null };
  return { css: tone.cssVar ? `var(${tone.cssVar})` : null, hex: tone.hex ?? null };
}

/** Group the lit cells by colour and alpha, merging horizontal runs per row. */
function groupFrame(def: BannerDefinition, frame: Frame): Group[] {
  const groups = new Map<string, Group>();
  for (let y = 0; y < frame.height; y += 1) {
    let x = 0;
    while (x < frame.width) {
      const pixel = frame.pixels[y * frame.width + x];
      if (!pixel || pixel.alpha <= 0) {
        x += 1;
        continue;
      }
      const tone = toneOf(def, pixel.tone);
      const color = tone.css ?? tone.hex ?? "#ffffff";
      const alpha = Math.min(1, pixel.alpha);
      const key = `${color}|${alpha}`;
      let group = groups.get(key);
      if (!group) {
        group = { color, hex: tone.hex ?? null, alpha, runs: [] };
        groups.set(key, group);
      }
      let w = 1;
      while (x + w < frame.width) {
        const next = frame.pixels[y * frame.width + x + w];
        if (!next || next.alpha <= 0) break;
        const nextTone = toneOf(def, next.tone);
        const nextColor = nextTone.css ?? nextTone.hex ?? "#ffffff";
        if (`${nextColor}|${Math.min(1, next.alpha)}` !== key) break;
        w += 1;
      }
      group.runs.push({ x, y, w });
      x += w;
    }
  }
  return [...groups.values()];
}

function pathOf(group: Group): string {
  return group.runs.map((run) => `M${run.x} ${run.y}h${run.w}v1h-${run.w}z`).join("");
}

function svgDoc(frame: Frame, paths: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${frame.width} ${frame.height}"` +
    ` width="${frame.width}" height="${frame.height}" shape-rendering="crispEdges"` +
    ` preserveAspectRatio="none">${paths}</svg>`
  );
}

/** encodeURIComponent leaves ! ' ( ) * alone; a CSS url("…") token needs them escaped too. */
function encodeSvg(svg: string): string {
  return encodeURIComponent(svg).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function dataUrl(svg: string): string {
  return `url("data:image/svg+xml,${encodeSvg(svg)}")`;
}

function build(def: BannerDefinition, options: SettledOptions): { frame: Frame; groups: Group[] } {
  const frame = settledFrame(def, options);
  return { frame, groups: groupFrame(def, frame) };
}

/** The settled frame: what the banner shows when it is still. */
export function settledFrame(def: BannerDefinition, options: SettledOptions = {}): Frame {
  return sampleBanner(def, { t: 0, motion: "reduced", gap: options.gap }).frame;
}

/**
 * The settled mark as an SVG document. `colored` bakes the tone hexes in;
 * the default draws a black shape, which is what a CSS mask wants.
 */
export function settledSvg(def: BannerDefinition, options: SettledOptions = {}, colored = false): string {
  const { frame, groups } = build(def, options);
  const paths = groups
    .map((group) => `<path d="${pathOf(group)}" fill="${colored ? (group.hex ?? "#ffffff") : "#000000"}" fill-opacity="${group.alpha}"/>`)
    .join("");
  return svgDoc(frame, paths);
}

/** The settled mark as a CSS value the browser can paint without JavaScript. */
export function settledFallback(def: BannerDefinition, options: SettledOptions = {}): SettledFallback {
  const { groups } = build(def, options);
  const colors = new Set(groups.map((group) => group.color));
  const multiTone = colors.size > 1;
  const color = groups[0]?.color ?? "#ffffff";
  const svg = multiTone ? settledSvg(def, options, true) : settledSvg(def, options);
  return { color, kind: multiTone ? "image" : "mask", url: dataUrl(svg), multiTone };
}
