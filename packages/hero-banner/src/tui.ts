import { pixelAt } from "./layout";
import { sampleBanner, terminalFit, type SampleOptions } from "./engine";
import type { BannerDefinition, Frame, Palette, Phase, Pixel } from "./types";

/**
 * Terminal renderer. A terminal cell is about twice as tall as it is wide, so
 * one cell holds two square pixels: ▀ (top), ▄ (bottom), █ (both, one colour),
 * or ▀ with fg top and bg bottom (both, two colours). One colour mode per run:
 * truecolor (38;2) or the xterm-256 cube (38;5), never both.
 */

export type ColorMode = "truecolor" | "256";
export type TermColor = { hex: string } | { cube: number };
export type TermCell = { ch: string; fg: TermColor | null; bg: TermColor | null };

export function colorModeFrom(env: Record<string, string | undefined>): ColorMode {
  const v = (env.COLORTERM ?? "").toLowerCase();
  return v === "truecolor" || v === "24bit" ? "truecolor" : "256";
}

const hexToRgb = (hex: string): [number, number, number] => {
  const n = Number.parseInt(hex.replace("#", "").slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const rgbToHex = ([r, g, b]: [number, number, number]) =>
  `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;

const CUBE = [0, 95, 135, 175, 215, 255];

/** Nearest xterm-256 colour (6x6x6 cube or the 24-step grey ramp). */
export function nearestCube([r, g, b]: [number, number, number]): number {
  const level = (v: number) => {
    let best = 0;
    for (let i = 1; i < CUBE.length; i += 1) if (Math.abs(CUBE[i]! - v) < Math.abs(CUBE[best]! - v)) best = i;
    return best;
  };
  const [ri, gi, bi] = [level(r), level(g), level(b)];
  const cubeRgb = [CUBE[ri]!, CUBE[gi]!, CUBE[bi]!];
  const cubeDist = (cubeRgb[0]! - r) ** 2 + (cubeRgb[1]! - g) ** 2 + (cubeRgb[2]! - b) ** 2;
  const mean = (r + g + b) / 3;
  const step = Math.max(0, Math.min(23, Math.round((mean - 8) / 10)));
  const grey = 8 + step * 10;
  const greyDist = (grey - r) ** 2 + (grey - g) ** 2 + (grey - b) ** 2;
  return greyDist < cubeDist ? 232 + step : 16 + 36 * ri + 6 * gi + bi;
}

/** A pixel's colour: its tone, blended onto `ground` by alpha. A full-alpha
 *  pixel is the tone's own hex or cube, untouched. */
export function pixelColor(pixel: Pixel, palette: Palette, mode: ColorMode): TermColor {
  const tone = palette[pixel.tone] ?? palette.ink;
  if (pixel.alpha >= 0.999) return mode === "truecolor" ? { hex: tone.hex.toLowerCase() } : { cube: tone.cube };
  const a = Math.max(0, pixel.alpha);
  const fg = hexToRgb(tone.hex);
  const bg = hexToRgb(palette.ground.hex);
  const mixed: [number, number, number] = [0, 1, 2].map((i) => bg[i]! + (fg[i]! - bg[i]!) * a) as [number, number, number];
  return mode === "truecolor" ? { hex: rgbToHex(mixed) } : { cube: nearestCube(mixed) };
}

const same = (a: TermColor, b: TermColor) =>
  "hex" in a ? "hex" in b && a.hex === b.hex : "cube" in b && a.cube === b.cube;

export function halfBlocks(frame: Frame, palette: Palette, mode: ColorMode): TermCell[][] {
  const lines: TermCell[][] = [];
  for (let y = 0; y < frame.height; y += 2) {
    const row: TermCell[] = [];
    for (let x = 0; x < frame.width; x += 1) {
      const top = pixelAt(frame, x, y);
      const bot = pixelAt(frame, x, y + 1);
      if (!top && !bot) {
        row.push({ ch: " ", fg: null, bg: null });
      } else if (top && bot) {
        const t = pixelColor(top, palette, mode);
        const b = pixelColor(bot, palette, mode);
        row.push(same(t, b) ? { ch: "█", fg: t, bg: null } : { ch: "▀", fg: t, bg: b });
      } else if (top) {
        row.push({ ch: "▀", fg: pixelColor(top, palette, mode), bg: null });
      } else {
        row.push({ ch: "▄", fg: pixelColor(bot!, palette, mode), bg: null });
      }
    }
    lines.push(row);
  }
  return lines;
}

export type BannerLines = {
  lines: TermCell[][];
  /** Columns the mark uses (before any centring). */
  width: number;
  phase: Phase;
  gap: number;
  scale: number;
  /** The terminal is too small for the pixel mark: one text line instead. */
  compact: boolean;
};

/**
 * The banner for a terminal of `cols` x `rows`, at one moment. Picks gap and
 * scale to fit; below the minimum it falls back to the text on one line.
 */
export function bannerLines(
  def: BannerDefinition,
  options: Omit<SampleOptions, "gap" | "scale"> & { cols: number; rows?: number; mode: ColorMode; scale?: number },
): BannerLines {
  const fit = terminalFit(def, { cols: options.cols, rows: options.rows });
  if (!fit) {
    const ink = pixelColor({ tone: "ink", alpha: 1 }, def.palette, options.mode);
    const text = def.text.slice(0, Math.max(0, options.cols));
    return {
      lines: [[...text].map((ch) => ({ ch, fg: ink, bg: null }))],
      width: text.length,
      phase: "still",
      gap: 0,
      scale: 1,
      compact: true,
    };
  }
  const sample = sampleBanner(def, { ...options, gap: fit.gap, scale: options.scale ?? fit.scale });
  return {
    lines: halfBlocks(sample.frame, def.palette, options.mode),
    width: sample.frame.width,
    phase: sample.phase,
    gap: sample.gap,
    scale: sample.scale,
    compact: false,
  };
}

const sgr = (c: TermColor, layer: 38 | 48) => {
  if ("hex" in c) {
    const [r, g, b] = hexToRgb(c.hex);
    return `${layer};2;${r};${g};${b}`;
  }
  return `${layer};5;${c.cube}`;
};

/** Plain ANSI lines, for terminals without OpenTUI and for snapshots. */
export function toAnsi(lines: TermCell[][]): string[] {
  return lines.map((row) =>
    row
      .map((cell) => {
        if (!cell.fg && !cell.bg) return cell.ch;
        const codes = [cell.fg ? sgr(cell.fg, 38) : "", cell.bg ? sgr(cell.bg, 48) : ""].filter(Boolean).join(";");
        return `\x1b[${codes}m${cell.ch}\x1b[0m`;
      })
      .join(""),
  );
}

export const toPlain = (lines: TermCell[][]) => lines.map((row) => row.map((c) => c.ch).join(""));

/** A colour as OpenTUI takes it: a hex string. Cube indices map to their xterm RGB. */
export function termColorHex(c: TermColor): string {
  if ("hex" in c) return c.hex;
  const n = c.cube;
  if (n >= 232) {
    const v = 8 + (n - 232) * 10;
    return rgbToHex([v, v, v]);
  }
  if (n >= 16) {
    const i = n - 16;
    return rgbToHex([CUBE[Math.floor(i / 36)]!, CUBE[Math.floor(i / 6) % 6]!, CUBE[i % 6]!]);
  }
  const base = ["#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080", "#c0c0c0", // canon-allow: the xterm-256 base palette table is the terminal's own colour standard, not app theming
    "#808080", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff"]; // canon-allow: the xterm-256 base palette table is the terminal's own colour standard, not app theming
  return base[n] ?? "#ffffff"; // canon-allow: terminal fallback; the table above is the xterm-256 standard
}
