import { canonicalLayout, fitTerminal, repack, upscale } from "./layout";
import type { BannerDefinition, Frame, Layout, Motion, Phase } from "./types";

/** `prepare` once per definition; frames are then pure in time. */
const prepared = new WeakMap<BannerDefinition, { layout: Layout; state: unknown }>();

export function preparedBanner(def: BannerDefinition): { layout: Layout; state: unknown } {
  let entry = prepared.get(def);
  if (!entry) {
    assertDefinition(def);
    const layout = canonicalLayout(def);
    entry = { layout, state: def.animation.prepare(layout, def) };
    prepared.set(def, entry);
  }
  return entry;
}

/** Banner text is ALL CAPS (hero-banner exception); the label is the lowercase name. */
export function assertDefinition(def: BannerDefinition): void {
  if (def.text !== def.text.toUpperCase()) throw new Error(`hero-banner ${def.id}: text must be ALL CAPS`);
  if (def.label !== def.label.toLowerCase()) throw new Error(`hero-banner ${def.id}: label must be lowercase`);
  if (def.font.rows % 2 !== 0) throw new Error(`hero-banner ${def.id}: font rows must be even`);
  for (const ch of def.text) {
    if (!def.glyphs?.[ch] && !def.font.glyphs[ch]) throw new Error(`hero-banner ${def.id}: no glyph for "${ch}"`);
  }
  for (const tone of ["ink", "ground"]) {
    if (!def.palette[tone]) throw new Error(`hero-banner ${def.id}: palette needs "${tone}"`);
  }
}

export type SampleOptions = {
  /** ms since the banner mounted. */
  t: number;
  /** LIVE on/off. Defaults to the definition. */
  live?: boolean;
  motion?: Motion;
  /** The intro already played (this session / this process): start in LIVE. */
  skipLoading?: boolean;
  gap?: number;
  scale?: number;
};

export type Sample = { frame: Frame; phase: Phase; gap: number; scale: number };

/**
 * The banner at one moment. Reduced motion is the settled mark, always. With
 * LIVE off the mark settles after LOADING and stays.
 */
export function sampleBanner(def: BannerDefinition, options: SampleOptions): Sample {
  const { layout, state } = preparedBanner(def);
  const anim = def.animation;
  const live = options.live ?? def.live;
  const gap = Math.min(layout.gap, Math.max(0, options.gap ?? layout.gap));
  const scale = Math.max(1, Math.floor(options.scale ?? 1));
  const t = Number.isFinite(options.t) ? Math.max(0, options.t) : 0;
  let phase: Phase;
  let frame: Frame;
  const loadingMs = anim.loadingMs(state);
  if (options.motion === "reduced") {
    phase = "still";
    frame = anim.still(state);
  } else if (!options.skipLoading && t < loadingMs) {
    phase = "loading";
    frame = anim.loading(state, t);
  } else if (live) {
    phase = "live";
    frame = anim.live(state, options.skipLoading ? t : t - loadingMs, t);
  } else {
    phase = "still";
    frame = anim.still(state);
  }
  return { frame: upscale(repack(frame, layout, gap), scale), phase, gap, scale };
}

/** How long until the banner needs a repaint. `null`: it is still; stop the timer. */
export function nextTickMs(def: BannerDefinition, phase: Phase): number | null {
  if (phase === "loading") return 40;
  if (phase === "live") return def.animation.liveTickMs;
  return null;
}

export function terminalFit(def: BannerDefinition, size: { cols: number; rows?: number }) {
  return fitTerminal(preparedBanner(def).layout, size);
}

type Env = Record<string, string | undefined>;

function flag(value: string | undefined): boolean | null {
  if (value == null || value === "") return null;
  const v = value.trim().toLowerCase();
  if (["0", "false", "off", "no"].includes(v)) return false;
  return true;
}

/**
 * Reduced motion: `prefers-reduced-motion: reduce` on the web, `NO_MOTION` or
 * `HERO_BANNER_MOTION=reduce|off` in a terminal. Any one of them wins.
 */
export function resolveMotion({ env, prefersReduced }: { env?: Env; prefersReduced?: boolean } = {}): Motion {
  if (prefersReduced) return "reduced";
  if (flag(env?.NO_MOTION) === true) return "reduced";
  const m = env?.HERO_BANNER_MOTION?.trim().toLowerCase();
  if (m === "reduce" || m === "reduced" || m === "off" || m === "none") return "reduced";
  return "full";
}

/** LIVE on/off: explicit surface config, then `HERO_BANNER_LIVE`, then the definition. */
export function resolveLive(def: BannerDefinition, { env, config }: { env?: Env; config?: boolean } = {}): boolean {
  if (config != null) return config;
  return flag(env?.HERO_BANNER_LIVE) ?? def.live;
}

export type PlayedStore = { getItem(key: string): string | null; setItem(key: string, value: string): void };

export const playedKey = (def: BannerDefinition) => `hero-banner:${def.id}:played`;

/**
 * LOADING plays once per session (a browser tab, or a terminal process).
 * The first call claims the play; later calls start in LIVE.
 */
export function claimLoading(def: BannerDefinition, store: PlayedStore | null): boolean {
  if (!store) return true;
  try {
    if (store.getItem(playedKey(def)) === "1") return false;
    store.setItem(playedKey(def), "1");
    return true;
  } catch {
    return true;
  }
}

/** In-memory store: one per process, for terminals. */
export function memoryStore(): PlayedStore {
  const map = new Map<string, string>();
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => void map.set(k, v) };
}
