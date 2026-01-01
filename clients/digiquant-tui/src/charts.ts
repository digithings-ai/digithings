/** In-house chart primitives for the terminal. A chart is a block of painted
 *  rows, the same shape `PaneBlock`'s `chart` carries today.
 *
 *  Four kinds, and they are the four the desktop data-display audit named:
 *  `line` (braille), `bars`, `stacked`, `heatmap`. A fifth shape the audit
 *  also named — a pie — has no honest terminal form, so `pieAsStacked` draws
 *  it as one 100% stacked bar instead. That mapping is the point of the
 *  module: nothing here silently drops a slice.
 *
 *  In-house on purpose. The TUI is bun-managed and sits outside the npm
 *  workspace closure, so it cannot take a charting dependency without a lock
 *  of its own. Braille, block ramps and the dot table `mark.ts` already packs
 *  the same way are the whole toolkit.
 *
 *  No colours here. A terminal cell is one character; the pane paints the fg
 *  per cell from `theme.ts`. */

import { SHORTCUTS } from "../../../apps/digiquant-web/components/desk/shortcuts";

/** The four paintable kinds, in the order the toggle key cycles them. */
export type ChartKind = "line" | "bars" | "stacked" | "heatmap";

export const CHART_KINDS: readonly ChartKind[] = ["line", "bars", "stacked", "heatmap"];

/** Braille dot bits, two source columns by four source rows. Same table and
 *  same order as the header mark, so one glyph reads the same in both. */
const BRAILLE_DOTS = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
] as const;

/** Eighth blocks, light to full. A column chart reads its own height off these. */
export const BLOCK_RAMP = " ▁▂▃▄▅▆▇█";
/** Density ramp for the heatmap. Every slot here IS a signal, so the lowest
 *  one still paints. A cell with no value at all is the only blank. */
export const HEAT_RAMP = "░▒▓█";
/** What a heatmap cell with no value looks like: nothing. */
export const HEAT_NONE = " ";

export type Size = { width?: number; height?: number };

function sizeOf(size: Size, fallbackWidth: number, fallbackHeight: number): { width: number; height: number } {
  const rawWidth = size.width === undefined ? fallbackWidth : size.width;
  const rawHeight = size.height === undefined ? fallbackHeight : size.height;
  const width = Number.isFinite(rawWidth) ? Math.max(0, Math.floor(rawWidth)) : 0;
  const height = Number.isFinite(rawHeight) ? Math.max(0, Math.floor(rawHeight)) : 0;
  return { width, height };
}

/** A value that can be painted. NaN and the infinities are not data, so they
 *  are dropped at the edge rather than turned into a spike downstream. */
function paintable(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Low and high of the values that can be painted. Null when none can. */
export function extent(values: readonly unknown[]): { min: number; max: number } | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let seen = 0;
  for (const value of values) {
    if (!paintable(value)) continue;
    seen += 1;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  return seen === 0 ? null : { min, max };
}

/** Where a value lands on a `levels`-step ramp, 0 to `levels - 1`. A flat
 *  series has no spread to read, so it sits at the bottom rather than at an
 *  undefined 0/0. Out-of-range values clamp; a value above the max is real. */
export function ramp(value: number, min: number, max: number, levels: number): number {
  if (levels <= 1) return 0;
  if (!paintable(value)) return 0;
  if (max <= min) return 0;
  const bucket = Math.round(((value - min) / (max - min)) * (levels - 1));
  return Math.min(levels - 1, Math.max(0, bucket));
}

/** Resample a series to `width` columns by nearest source value. */
export function resample(values: readonly number[], width: number): number[] {
  if (width <= 0 || values.length === 0) return [];
  if (values.length === 1) return new Array(width).fill(values[0] ?? 0);
  const out: number[] = [];
  for (let col = 0; col < width; col++) {
    const at = Math.round((col * (values.length - 1)) / (width - 1));
    out.push(values[Math.min(Math.max(at, 0), values.length - 1)] ?? 0);
  }
  return out;
}

/** One braille cell for two columns by four rows. Blank stays a space. */
export function brailleCell(on: (column: number, row: number) => boolean): string {
  let bits = 0;
  for (let i = 0; i < BRAILLE_DOTS.length; i++) {
    const pair = BRAILLE_DOTS[i] ?? [0, 0];
    if (on(0, i)) bits |= pair[0];
    if (on(1, i)) bits |= pair[1];
  }
  return bits === 0 ? " " : String.fromCharCode(0x2800 + bits);
}

/** Braille line plot. One character cell is two columns by four rows, so a
 *  `width` x `height` box needs exactly `ceil(width / 2)` characters per row.
 *  An odd width leaves the last cell's right column blank.
 *
 *  A dot lights when its row, counted from the BOTTOM of the box, is at or
 *  below the value's own row. That is what makes a low value paint the floor
 *  of the box and a high value fill it. */
export function brailleLine(values: readonly unknown[], size: Size = {}): string[] {
  const { width, height } = sizeOf(size, 40, 8);
  if (width <= 0 || height <= 0) return [];
  const cellRows = height * 4;
  const cols = Math.ceil(width / 2);
  const clean = values.filter(paintable);
  const span = extent(clean);
  const blank = new Array(height).fill(" ".repeat(cols));
  if (clean.length === 0 || !span) return blank;
  const flat = span.max <= span.min;
  const samples = resample(clean, width);
  const lines: string[] = [];
  for (let row = 0; row < height; row++) {
    let line = "";
    for (let col = 0; col < cols; col++) {
      const x = col * 2;
      line += brailleCell((dx, dy) => {
        const at = x + dx;
        if (at >= width) return false;
        const value = samples[at];
        if (value === undefined) return false;
        // A flat series has no spread, so it draws one solid row on the floor.
        const valueRow = flat ? 0 : Math.round(((value - span.min) / (span.max - span.min)) * (cellRows - 1));
        const fromBottom = cellRows - 1 - (row * 4 + dy);
        return fromBottom <= valueRow;
      });
    }
    lines.push(line);
  }
  return lines;
}

/** One column per value, drawn with the eighth-block ramp. A column is
 *  uniform: the same block repeated up its own height, so the eye reads the
 *  column and not a texture. A value at or above the max paints a full block
 *  column, and nothing is ever drawn taller than the box. */
export function barChart(values: readonly unknown[], size: Size = {}): string[] {
  const { width, height } = sizeOf(size, 40, 8);
  if (width <= 0 || height <= 0) return [];
  const clean = values.filter(paintable);
  if (clean.length === 0) return new Array(height).fill(" ".repeat(width));
  const span = extent(clean)!;
  const flat = span.max <= span.min;
  const samples = resample(clean, width);
  const top = BLOCK_RAMP.length - 1;
  const lines: string[] = [];
  for (let row = 0; row < height; row++) {
    const fromTop = height - 1 - row;
    let line = "";
    for (let col = 0; col < width; col++) {
      const value = samples[col];
      if (value === undefined) {
        line += " ";
        continue;
      }
      // A flat series has no spread, so every column is full height.
      const filled = flat ? height : Math.max(1, Math.round(((value - span.min) / (span.max - span.min)) * height));
      if (fromTop >= filled) {
        line += " ";
        continue;
      }
      const level = filled >= height ? top : Math.max(1, Math.round((filled / height) * top));
      line += BLOCK_RAMP[Math.min(top, Math.max(1, level))] ?? " ";
    }
    lines.push(line);
  }
  return lines;
}

export type Series = { label: string; values: readonly number[] };

/** Stacked columns. Each column stacks its series bottom-up in the order the
 *  series are given, so the first series is the base of every column and the
 *  legend order is the paint order. One block per series keeps the segments
 *  separable, which is the whole point of stacking them. */
export function stackedBars(series: readonly Series[], size: Size = {}): string[] {
  const { width, height } = sizeOf(size, 40, 8);
  if (width <= 0 || height <= 0) return [];
  const usable = series.filter((item) => Array.isArray(item?.values));
  const flat = usable.flatMap((item) => item.values);
  if (usable.length === 0 || extent(flat.filter(paintable)) === null) {
    return new Array(height).fill(" ".repeat(width));
  }
  const columns = usable.map((item) => resample(item.values.filter(paintable), width));
  const lines: string[] = [];
  for (let row = 0; row < height; row++) {
    const fromTop = height - 1 - row;
    let line = "";
    for (let col = 0; col < width; col++) {
      const total = columns.reduce((acc, values) => acc + Math.max(0, values[col] ?? 0), 0);
      if (!(total > 0)) {
        line += " ";
        continue;
      }
      // Each segment claims a share of the column, bottom-up, and the first
      // segment to cover this row wins. Segments are at least one row tall so
      // no slice is invisible while another is drawn.
      let claimed = 0;
      let glyph = " ";
      for (let s = 0; s < usable.length; s++) {
        const value = Math.max(0, columns[s]?.[col] ?? 0);
        const rows = value <= 0 ? 0 : Math.max(1, Math.round((value / total) * height));
        if (rows > 0 && fromTop >= claimed && fromTop < claimed + rows) {
          glyph = BLOCK_RAMP[Math.min(BLOCK_RAMP.length - 1, 1 + (s % (BLOCK_RAMP.length - 1)))] ?? " ";
        }
        claimed += rows;
      }
      line += glyph;
    }
    lines.push(line);
  }
  return lines;
}

/** A value grid as a density map. Short rows are padded with no value, and a
 *  cell with no value paints blank while every real value paints a ramp
 *  slot, so "no data" and "lowest reading" can never be confused. */
export function heatmap(rows: readonly (readonly unknown[])[], size: Size = {}): string[] {
  const { width, height } = sizeOf(size, 40, 8);
  if (width <= 0 || height <= 0) return [];
  const source = rows.filter((row) => Array.isArray(row));
  const span = extent(source.flat().filter(paintable));
  const lines: string[] = [];
  for (let row = 0; row < height; row++) {
    const sourceRow = source[row]?.filter(paintable);
    const values = sourceRow && sourceRow.length ? resample(sourceRow, width) : [];
    let line = "";
    for (let col = 0; col < width; col++) {
      const value = values[col];
      if (value === undefined || !span) line += HEAT_NONE;
      else line += HEAT_RAMP[ramp(value, span.min, span.max, HEAT_RAMP.length)] ?? HEAT_NONE;
    }
    lines.push(line);
  }
  return lines;
}

export type PieSlice = { label: string; value: number };

/** A pie as a 100% stacked bar. Every slice keeps its own contiguous run of
 *  columns and its own block, so no slice is merged into a neighbour: a
 *  one-hundredth slice still gets a column. This is the shape a terminal can
 *  read where a circle cannot exist. */
export function pieAsStacked(slices: readonly PieSlice[], size: Size = {}): string[] {
  const { width, height } = sizeOf(size, 40, 1);
  const usable = slices.filter((slice) => paintable(slice?.value) && slice.value > 0);
  if (usable.length === 0 || width <= 0 || height <= 0) return [];
  const total = usable.reduce((acc, slice) => acc + slice.value, 0);
  // Largest remainder, so the runs always sum to exactly the box width.
  const exact = usable.map((slice) => (slice.value / total) * width);
  const counts = exact.map((value) => Math.floor(value));
  let left = width - counts.reduce((acc, n) => acc + n, 0);
  const order = exact
    .map((value, i) => ({ i, rest: value - Math.floor(value) }))
    .sort((a, b) => b.rest - a.rest || a.i - b.i);
  for (let k = 0; k < order.length && left > 0; k++) {
    const at = order[k];
    if (!at) continue;
    counts[at.i] = (counts[at.i] ?? 0) + 1;
    left -= 1;
  }
  const top = BLOCK_RAMP.length - 1;
  const lines: string[] = [];
  for (let row = 0; row < height; row++) {
    let line = "";
    for (let col = 0; col < width; col++) {
      // Runs are laid end to end, so the test is against the running total.
      let slice = -1;
      let start = 0;
      for (let s = 0; s < usable.length; s++) {
        const run = counts[s] ?? 0;
        if (col >= start && col < start + run) {
          slice = s;
          break;
        }
        start += run;
      }
      line += slice < 0 ? " " : BLOCK_RAMP[Math.min(top, Math.max(1, slice + 1))] ?? " ";
    }
    lines.push(line);
  }
  return lines;
}

/** A pie as its own label row: `label  share`. The stacked bar gives the
 *  shape, this gives the names, because a bar of blocks names nothing. */
export function pieLegend(slices: readonly PieSlice[]): string[] {
  const usable = slices.filter((slice) => paintable(slice?.value) && slice.value > 0);
  const total = usable.reduce((acc, slice) => acc + slice.value, 0);
  if (total <= 0) return [];
  return usable.map((slice) => `${slice.label}  ${((slice.value / total) * 100).toFixed(1)}%`);
}

/** The key that steps a pane to the next chart kind. The web app declares its
 *  own key map in `apps/digiquant-web/components/desk/shortcuts.ts`, and that
 *  file says the keys match this terminal where it has one. So the key here is
 *  not chosen freely: it is a key the web map has not claimed, and
 *  `chartToggleKeyIsFree` fails the day the web claims it. */
export const CHART_TOGGLE_KEY = "c";

/** Every key the web map already spells, its own column and the `tui` one.
 *  Split on whitespace only: the map's own column separates alternatives with
 *  a slash, and `/` is itself one of the keys. */
export function claimedKeys(): string[] {
  const keys: string[] = [];
  for (const row of SHORTCUTS) {
    for (const column of [row.keys, row.tui ?? ""]) {
      for (const token of column.split(/\s+/)) {
        const key = token.trim().toLowerCase();
        if (key && key !== "or") keys.push(key);
      }
    }
  }
  return keys;
}

/** True while the web map leaves this key to the terminal. */
export function chartToggleKeyIsFree(key: string = CHART_TOGGLE_KEY): boolean {
  return !claimedKeys().includes(key.toLowerCase());
}

/** Step to the next kind. Any other key leaves the kind alone, so a pane
 *  that forwards stray keys cannot silently change what is drawn. */
export function toggleChartKind(kind: ChartKind, key: string): ChartKind {
  if (key.toLowerCase() !== CHART_TOGGLE_KEY) return kind;
  const at = CHART_KINDS.indexOf(kind);
  return CHART_KINDS[(at < 0 ? 0 : at + 1) % CHART_KINDS.length] as ChartKind;
}

/** Draw by kind. One entry point, so a pane never switches on the kind itself
 *  and so the pie mapping is impossible to bypass. A payload of rows paints a
 *  heatmap under any kind that has no series of its own. */
export function drawChart(kind: ChartKind, data: unknown, size: Size = {}): string[] {
  const rows = Array.isArray(data) ? (data as unknown[]) : [];
  if (kind === "bars") return barChart(rows, size);
  if (kind === "stacked") return stackedBars(rows as Series[], size);
  if (kind === "heatmap") return heatmap(rows as unknown[][], size);
  if (rows.length > 0 && rows.every((row) => Array.isArray(row))) return heatmap(rows as unknown[][], size);
  return brailleLine(rows, size);
}
