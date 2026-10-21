/**
 * Canonical spacing for the digichat Worked chain.
 *
 * A short scale (`--trace-space-1` … `--trace-space-7`, kept apart from the design tokens' `--space-*`) is the only length source.
 * Semantic tokens (`--trace-*`) are what the chain title, sibling groups,
 * items inside a group, the header-to-body gap and the body padding read.
 * Density reassigns those tokens. Rules in `chat-digichat.css` and
 * `chat-aui.css` reference the tokens and do not carry their own lengths.
 *
 * `default` is the fixed rhythm: room under the Worked title, one gap
 * between every sibling group, a tighter gap inside a group, and a short
 * step from a reasoning header into its text.
 */

export const TRACE_DENSITIES = ["compact", "default", "airy"] as const;
export type TraceDensity = (typeof TRACE_DENSITIES)[number];

export const DEFAULT_TRACE_DENSITY: TraceDensity = "default";

/** localStorage key. Digichat only — the dashboard never reads it. */
export const DENSITY_STORAGE_KEY = "dt-density";

/** The scale, in rem. Density never invents a length outside this list. */
export const TRACE_SPACE_SCALE = {
  1: "0.125rem",
  2: "0.25rem",
  3: "0.375rem",
  4: "0.5rem",
  5: "0.625rem",
  6: "0.75rem",
  7: "1rem",
} as const;

export type TraceSpacingTokens = {
  /** Worked title → first row. */
  titleGap: string;
  /** Between sibling groups, whatever the group type. */
  groupGap: string;
  /** Between items inside one group, and between paragraphs in a body. */
  withinGap: string;
  /** Group header → its body. */
  headerGap: string;
  /** Block padding inside a reasoning / tool body. */
  bodyPad: string;
  /** Inline indent of a reasoning body (the hairline rail). */
  bodyIndent: string;
  /** The chain block against the answer that follows it. */
  chainGap: string;
};

/**
 * Palette copy. The composer menu and `/density` print the same words.
 * Kept here so the ids and the labels cannot drift from the tokens.
 */
export const TRACE_DENSITY_LABELS: Record<TraceDensity, string> = {
  compact: "Compact · tighter",
  default: "Default · balanced rhythm",
  airy: "Airy · more room",
};

export const TRACE_SPACING: Record<TraceDensity, TraceSpacingTokens> = {
  compact: {
    titleGap: TRACE_SPACE_SCALE[3],
    groupGap: TRACE_SPACE_SCALE[2],
    withinGap: TRACE_SPACE_SCALE[1],
    headerGap: "0rem",
    bodyPad: "0rem",
    bodyIndent: TRACE_SPACE_SCALE[5],
    chainGap: TRACE_SPACE_SCALE[4],
  },
  default: {
    titleGap: TRACE_SPACE_SCALE[5],
    groupGap: TRACE_SPACE_SCALE[4],
    withinGap: TRACE_SPACE_SCALE[2],
    headerGap: TRACE_SPACE_SCALE[2],
    bodyPad: TRACE_SPACE_SCALE[1],
    bodyIndent: TRACE_SPACE_SCALE[6],
    chainGap: TRACE_SPACE_SCALE[6],
  },
  airy: {
    titleGap: TRACE_SPACE_SCALE[7],
    groupGap: TRACE_SPACE_SCALE[6],
    withinGap: TRACE_SPACE_SCALE[4],
    headerGap: TRACE_SPACE_SCALE[4],
    bodyPad: TRACE_SPACE_SCALE[3],
    bodyIndent: TRACE_SPACE_SCALE[7],
    chainGap: TRACE_SPACE_SCALE[7],
  },
};

export function isTraceDensity(value: string): value is TraceDensity {
  return (TRACE_DENSITIES as readonly string[]).includes(value);
}

export function normalizeTraceDensity(value: string | null | undefined): TraceDensity | null {
  if (!value) return null;
  const id = value.trim().toLowerCase();
  return isTraceDensity(id) ? id : null;
}

/**
 * A stored user choice wins. An unknown stored value is ignored so a bad
 * key cannot blank the chain. Otherwise the deployment default, then the
 * builtin `default` rhythm.
 */
export function resolveTraceDensity(
  stored: string | null | undefined,
  deployed: string | null | undefined,
): TraceDensity {
  return normalizeTraceDensity(stored) ?? normalizeTraceDensity(deployed) ?? DEFAULT_TRACE_DENSITY;
}

type DensityStorage = {
  getItem(key: string): string | null;
  setItem?(key: string, value: string): void;
};

function safeStorage(): DensityStorage | null {
  try {
    if (typeof localStorage === "undefined") return null;
    return localStorage;
  } catch {
    return null;
  }
}

export function readStoredDensity(storage?: DensityStorage | null): TraceDensity | null {
  const store = storage === undefined ? safeStorage() : storage;
  if (!store) return null;
  try {
    return normalizeTraceDensity(store.getItem(DENSITY_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function writeStoredDensity(density: TraceDensity, storage?: DensityStorage | null): void {
  const store = storage === undefined ? safeStorage() : storage;
  if (!store?.setItem) return;
  try {
    store.setItem(DENSITY_STORAGE_KEY, density);
  } catch {
    /* private mode */
  }
}
