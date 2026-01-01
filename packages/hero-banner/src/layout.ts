import { fontWith } from "./font";
import type { BannerDefinition, Frame, Layout, Pixel, PixelFont } from "./types";

/** Seeded PRNG. Same generator the digithings and digiquant marks used, so a
 *  ported definition draws the same cells. */
export function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function layoutFor(text: string, font: PixelFont, gap: number): Layout {
  const starts: number[] = [];
  let x = 0;
  for (let i = 0; i < text.length; i += 1) {
    starts.push(x);
    x += font.cols + (i < text.length - 1 ? gap : 0);
  }
  return { text, font, gap, width: Math.max(0, x), height: font.rows, starts };
}

/** The canonical layout: the definition's own gap. Animations work in this grid. */
export function canonicalLayout(def: BannerDefinition): Layout {
  return layoutFor(def.text, fontWith(def.font, def.glyphs), def.gap);
}

/** Lit pixels of the layout, glyph by glyph, then row, then column: the order
 *  the legacy marks drew their random numbers in. */
export function litCells(layout: Layout): { x: number; y: number; glyph: number }[] {
  const out: { x: number; y: number; glyph: number }[] = [];
  for (let g = 0; g < layout.text.length; g += 1) {
    const glyph = layout.font.glyphs[layout.text[g] ?? ""];
    for (let y = 0; y < layout.height; y += 1) {
      const row = glyph?.[y] ?? "";
      for (let c = 0; c < layout.font.cols; c += 1) {
        if (row[c] === "#") out.push({ x: (layout.starts[g] ?? 0) + c, y, glyph: g });
      }
    }
  }
  return out;
}

export function emptyFrame(width: number, height: number): Frame {
  return { width, height, pixels: new Array<Pixel | null>(width * height).fill(null) };
}

export function setPixel(frame: Frame, x: number, y: number, pixel: Pixel | null): void {
  if (x < 0 || y < 0 || x >= frame.width || y >= frame.height) return;
  frame.pixels[y * frame.width + x] = pixel;
}

export function pixelAt(frame: Frame, x: number, y: number): Pixel | null {
  if (x < 0 || y < 0 || x >= frame.width || y >= frame.height) return null;
  return frame.pixels[y * frame.width + x] ?? null;
}

/**
 * Re-pack a canonical frame onto a narrower gap. Glyph columns move left;
 * pixels in dropped gap columns (strays between letters) are dropped.
 */
export function repack(frame: Frame, layout: Layout, gap: number): Frame {
  if (gap >= layout.gap) return frame;
  const target = layoutFor(layout.text, layout.font, gap);
  const out = emptyFrame(target.width, frame.height);
  const cols = layout.font.cols;
  for (let g = 0; g < layout.text.length; g += 1) {
    const from = layout.starts[g] ?? 0;
    const to = target.starts[g] ?? 0;
    const keepGap = g < layout.text.length - 1 ? gap : 0;
    for (let c = 0; c < cols + keepGap; c += 1) {
      for (let y = 0; y < frame.height; y += 1) setPixel(out, to + c, y, pixelAt(frame, from + c, y));
    }
  }
  return out;
}

/** Integer upscale: one pixel becomes a `scale` x `scale` block. */
export function upscale(frame: Frame, scale: number): Frame {
  if (scale <= 1) return frame;
  const out = emptyFrame(frame.width * scale, frame.height * scale);
  for (let y = 0; y < out.height; y += 1) {
    for (let x = 0; x < out.width; x += 1) {
      out.pixels[y * out.width + x] = frame.pixels[Math.floor(y / scale) * frame.width + Math.floor(x / scale)] ?? null;
    }
  }
  return out;
}

/**
 * Gap and scale for a terminal of `cols` x `rows`. Gap shrinks 2 -> 1 -> 0
 * before the mark gives up; scale grows to 2 or 3 only when the scaled mark
 * still leaves room under it (half the rows). Same budget rule as the digichat
 * and digivoice TUIs: two columns of margin.
 */
export function fitTerminal(
  layout: Layout,
  { cols, rows }: { cols: number; rows?: number },
): { gap: number; scale: number } | null {
  const budget = Math.max(1, cols - 2);
  const n = layout.text.length;
  const widthAt = (gap: number) => n * layout.font.cols + Math.max(0, n - 1) * gap;
  for (const scale of [3, 2]) {
    const lines = (layout.height * scale) / 2;
    if (widthAt(layout.gap) * scale <= budget && (rows == null || lines <= rows / 2)) {
      return { gap: layout.gap, scale };
    }
  }
  if (rows != null && rows < layout.height / 2) return null;
  for (let gap = layout.gap; gap >= 0; gap -= 1) {
    if (widthAt(gap) <= budget) return { gap, scale: 1 };
  }
  return null;
}
