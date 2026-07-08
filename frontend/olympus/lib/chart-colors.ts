/**
 * Chart color source — the ONLY place recharts colors come from (#1402).
 *
 * Two families live here:
 *
 * 1. SEMANTIC colors (up/down/warn/accent/axis/…): read from the canon
 *    [data-theme] tokens at render via `useChartColors()`, so charts reskin
 *    with the theme exactly like the DOM does. Recharts needs concrete color
 *    strings in SVG props, hence the getComputedStyle read (cached once per
 *    theme flip) instead of `var(--token)` strings.
 *
 * 2. CATEGORICAL / benchmark series (sleeve palette, SPY/QQQ…, currencies,
 *    event markers, signal legs): FIXED literals. This block is the
 *    sanctioned raw-hex allowlist for the whole app — series identity must
 *    stay stable across themes and must not collapse into one another
 *    (e.g. in dark mode --up equals --accent, which would merge OPEN and ADD
 *    event markers if they were token-driven). Preserve these hues; do not
 *    add raw hex anywhere else in olympus.
 */

import { useSyncExternalStore } from 'react';

/* ── 1. Semantic, token-driven ─────────────────────────────────────────── */

export type ChartColors = {
  /** P&L gain — canon --up (digiquant phosphor in dark, deep teal on paper). */
  up: string;
  /** P&L loss — canon --down. */
  down: string;
  /** Caution / watch — canon --warn. */
  warn: string;
  /** Primary series + selection chrome — canon --accent. */
  accent: string;
  /** Axis ticks, labels, neutral series — canon --ink-mute. */
  axis: string;
  /** Secondary text in tooltips/legends — canon --ink-soft. */
  inkSoft: string;
  /** Emphasis text — canon --ink. */
  ink: string;
  /** Gridlines / hairline borders — canon --hair. */
  hair: string;
  /** Canvas color, e.g. marker knock-out strokes — canon --bg. */
  bg: string;
  /** Panel surface — canon --surface. */
  surface: string;
  /** Recessed inset (tooltip backgrounds) — canon --term-bg. */
  termBg: string;
};

const TOKEN_MAP: Record<keyof ChartColors, string> = {
  up: '--up',
  down: '--down',
  warn: '--warn',
  accent: '--accent',
  axis: '--ink-mute',
  inkSoft: '--ink-soft',
  ink: '--ink',
  hair: '--hair',
  bg: '--bg',
  surface: '--surface',
  termBg: '--term-bg',
};

/** SSR / pre-mount defaults — the dark-theme token values verbatim. */
const DARK_FALLBACK: ChartColors = {
  up: '#3DD6C4',
  down: '#E5533E',
  warn: '#E0B341',
  accent: '#3DD6C4',
  axis: '#6B7177',
  inkSoft: '#9AA0A6',
  ink: '#ECEEF0',
  hair: 'rgba(255, 255, 255, 0.09)',
  bg: '#0A0E0C',
  surface: '#121417',
  termBg: '#08090B',
};

function readChartColors(): ChartColors {
  const cs = getComputedStyle(document.documentElement);
  const out = { ...DARK_FALLBACK };
  for (const key of Object.keys(TOKEN_MAP) as (keyof ChartColors)[]) {
    const v = cs.getPropertyValue(TOKEN_MAP[key]).trim();
    if (v) out[key] = v;
  }
  return out;
}

let cache: { theme: string | null; colors: ChartColors } | null = null;

/** Resolved token colors, read from the document once per theme flip. */
export function getChartColors(): ChartColors {
  if (typeof window === 'undefined') return DARK_FALLBACK;
  const theme = document.documentElement.getAttribute('data-theme');
  if (!cache || cache.theme !== theme) cache = { theme, colors: readChartColors() };
  return cache.colors;
}

function subscribeToTheme(onStoreChange: () => void): () => void {
  const observer = new MutationObserver(onStoreChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  });
  return () => observer.disconnect();
}

/**
 * Theme-reactive chart colors. Serves the dark fallbacks on the server
 * (hydration-safe), the live token values on the client; re-reads when
 * ThemeProvider flips data-theme on <html>. The per-theme cache in
 * getChartColors keeps the snapshot referentially stable between flips.
 */
export function useChartColors(): ChartColors {
  return useSyncExternalStore(subscribeToTheme, getChartColors, () => DARK_FALLBACK);
}

/**
 * `#RRGGBB`/`#RGB` → `rgba(...)` at the given alpha; non-hex colors are
 * passed through unchanged (best effort for rgba()/color() token values).
 */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(color.trim());
  if (!m) return color;
  let hex = m[1];
  if (hex.length === 3) hex = hex.split('').map((c) => c + c).join('');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/* ── 2. Categorical / benchmark series — SANCTIONED FIXED LITERALS ─────── */

/**
 * Rotating palette for N-way categorical series (sleeve allocation bands,
 * holdings contribution). Hue identity is load-bearing across sessions —
 * keep fixed.
 */
export const CATEGORICAL_SERIES: readonly string[] = [
  '#3B82F6',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#06B6D4',
  '#F97316',
  '#EC4899',
  '#6366F1',
  '#14B8A6',
] as const;

/** Benchmark overlay hues (performance workspace). */
export const BENCHMARK_COLORS: Record<string, string> = {
  SPY: '#a1a1aa',
  QQQ: '#8b5cf6',
  IWM: '#f472b6',
  EEM: '#22c55e',
  TLT: '#06b6d4',
  GLD: '#f59e0b',
  IBIT: '#f97316',
};

/** twelve-x currency hues (consensus bars / matrix). */
export const CURRENCY_COLORS: Record<string, string> = {
  USD: '#3B82F6',
  EUR: '#10B981',
  JPY: '#F59E0B',
  GBP: '#EF4444',
  CHF: '#8B5CF6',
  CAD: '#06B6D4',
  AUD: '#F97316',
  NZD: '#EC4899',
  SEK: '#6366F1',
  NOK: '#14B8A6',
};

/** Fallback for currencies outside the G10 map. */
export const CURRENCY_FALLBACK = '#94a3b8';

/**
 * Position-event markers (price/contribution charts). Deliberately FIXED,
 * not token-driven: in the dark theme --up === --accent (both the digiquant
 * phosphor), which would make OPEN and ADD markers indistinguishable. The
 * four-way legend coding needs four stable hues.
 */
export const EVENT_COLORS: Record<'OPEN' | 'EXIT' | 'ADD' | 'TRIM' | 'DEFAULT', string> = {
  OPEN: '#22c55e',
  EXIT: '#ef4444',
  ADD: '#38bdf8',
  TRIM: '#f59e0b',
  DEFAULT: '#71717a',
};

/** Intelligence composite signal legs (IntelligenceTab / WhyPanel). */
export const SIGNAL_SERIES: Record<'consensus' | 'event' | 'breadth', string> = {
  consensus: '#3B82F6',
  event: '#10B981',
  breadth: '#8B5CF6',
};

/** WhyPanel leg-score bars — consensus blue family, light-to-dark ramp. */
export const LEG_COLORS: readonly string[] = ['#3B82F6', '#6db6ff', '#8B5CF6'] as const;

/** Rolling-metrics chart: Sharpe vs volatility series. */
export const ROLLING_SERIES: Record<'sharpe' | 'vol', string> = {
  sharpe: '#8b5cf6',
  vol: '#06b6d4',
};
