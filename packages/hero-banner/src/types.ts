/**
 * Banner definition format. One definition is the single source for every
 * surface: the terminal renderers and the web renderer read the same object.
 * Spec: docs/architecture/hero-banner-spec.md.
 */

/** A colour both renderers can paint. `hex` is truecolor and canvas; `cube` is
 *  the xterm-256 index used when the terminal has no truecolor. `cssVar` lets
 *  the web renderer follow the page theme instead of `hex`. */
export type Tone = { hex: string; cube: number; cssVar?: string };

/** Named tones. `ink` is the settled mark, `ground` is what alpha blends onto. */
export type Palette = { ink: Tone; ground: Tone } & Record<string, Tone>;

/** Glyph rows, top to bottom. `#` is a lit pixel, anything else is empty. */
export type Glyph = readonly string[];

export type PixelFont = {
  /** Pixel columns per glyph. Every glyph in the font has this width. */
  cols: number;
  /** Pixel rows per glyph. Even, so a half-block terminal row holds two. */
  rows: number;
  glyphs: Readonly<Record<string, Glyph>>;
};

/** One painted pixel. `tone` names a palette entry; `alpha` blends it onto `ground`. */
export type Pixel = { tone: string; alpha: number };

/** A frame in glyph-pixel space, row-major. `null` is an empty pixel. */
export type Frame = { width: number; height: number; pixels: (Pixel | null)[] };

export type Phase = "loading" | "live" | "still";

/** Where the glyphs sit in the canonical (definition-gap) grid. */
export type Layout = {
  text: string;
  font: PixelFont;
  gap: number;
  width: number;
  height: number;
  /** x of each glyph's first column. */
  starts: number[];
};

/** A motion recipe. `prepare` runs once per definition (seeded, deterministic);
 *  the frame functions are pure in time, so any renderer can sample any moment. */
export type Animation<State = unknown> = {
  kind: string;
  prepare(layout: Layout, def: BannerDefinition): State;
  /** Length of the LOADING (intro) animation. */
  loadingMs(state: State): number;
  /** LOADING frame, `t` ms after the banner mounted. */
  loading(state: State, t: number): Frame;
  /** LIVE frame. `tLive` counts from the start of LIVE; `tMount` from mount
   *  (equal to `tLive` when the intro was skipped). */
  live(state: State, tLive: number, tMount: number): Frame;
  /** The settled mark: the frame for reduced motion and for live off. */
  still(state: State): Frame;
  /** Repaint interval while LIVE runs. */
  liveTickMs: number;
};

export type BannerDefinition = {
  /** Module id, lowercase (digithings, digiquant, ...). */
  id: string;
  /** Banner text. ALL CAPS: the hero-banner exception to lowercase names. */
  text: string;
  /** Accessible name. The module name, lowercase. */
  label: string;
  font: PixelFont;
  /** Per-module glyph overrides on top of `font`. */
  glyphs?: Readonly<Record<string, Glyph>>;
  /** Preferred columns between glyphs. Narrow surfaces drop to 1, then 0. */
  gap: number;
  palette: Palette;
  animation: Animation<any>;
  /** LIVE default. The surface can override (config on/off). */
  live: boolean;
  /** Seed for every random choice the animation makes. */
  seed: number;
};

export type Motion = "full" | "reduced";
