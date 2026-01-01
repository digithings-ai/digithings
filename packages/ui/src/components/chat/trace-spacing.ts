/**
 * Canonical spacing and type rhythm for the digichat thread.
 *
 * A short scale (`--trace-space-1` … `--trace-space-8`, kept apart from the design tokens' `--space-*`) is the only length source.
 * `DENSITY_TOKENS` is the one density set: four stack gaps, body padding,
 * two line heights and two letter-spacings. Every mode (compact / default /
 * airy) reassigns it on `.digichat-thread[data-density=…]`.
 * The semantic `--trace-*` names are aliases of that set, kept so the rules
 * that already read them keep working. Rules in `chat-digichat.css` and
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
  8: "1.25rem",
} as const;

/**
 * One density set, mirrored by the CSS custom properties in
 * `styles/chat-aui.css` (`--density-*`) and pinned by
 * `styles/density-tokens.contract.test.ts`. Every length is on
 * `TRACE_SPACE_SCALE`; the line heights and trackings are unitless.
 */
export type DensityTokens = {
  /** Tightest stack gap: items inside a group, paragraphs, list items. */
  gap1: string;
  /** Sibling gap: messages, chain groups, block separation. */
  gap2: string;
  /** Roomier step: title → first row, block → next block. */
  gap3: string;
  /** Largest step: message → message. */
  gap4: string;
  /** Inset inside a reasoning / tool body, and the composer's own padding. */
  pad: string;
  /** Body line height (answers, prose). */
  leading: string;
  /** Trace / mono line height (reasoning, tool dumps, code). */
  leadingTight: string;
  /** Body letter spacing. */
  tracking: string;
  /** Mono / trace letter spacing. */
  trackingMono: string;
};

export const DENSITY_TOKENS: Record<TraceDensity, DensityTokens> = {
  compact: {
    gap1: TRACE_SPACE_SCALE[1],
    gap2: TRACE_SPACE_SCALE[2],
    gap3: TRACE_SPACE_SCALE[3],
    gap4: TRACE_SPACE_SCALE[4],
    pad: "0rem",
    leading: "1.45",
    leadingTight: "1.3",
    tracking: "-0.005em",
    trackingMono: "0em",
  },
  default: {
    gap1: TRACE_SPACE_SCALE[2],
    gap2: TRACE_SPACE_SCALE[4],
    gap3: TRACE_SPACE_SCALE[5],
    gap4: TRACE_SPACE_SCALE[6],
    pad: TRACE_SPACE_SCALE[1],
    leading: "1.6",
    leadingTight: "1.4",
    tracking: "0em",
    trackingMono: "0.01em",
  },
  airy: {
    gap1: TRACE_SPACE_SCALE[3],
    gap2: TRACE_SPACE_SCALE[6],
    gap3: TRACE_SPACE_SCALE[7],
    gap4: TRACE_SPACE_SCALE[8],
    pad: TRACE_SPACE_SCALE[3],
    leading: "1.75",
    leadingTight: "1.55",
    tracking: "0.005em",
    trackingMono: "0.02em",
  },
};

export type TraceSpacingTokens = {
  /** Worked title → first row. Alias of `gap3`. */
  titleGap: string;
  /** Between sibling groups, whatever the group type. Alias of `gap2`. */
  groupGap: string;
  /** Between items inside one group, and between paragraphs in a body. Alias of `gap1`. */
  withinGap: string;
  /** Group header → its body. */
  headerGap: string;
  /** Block padding inside a reasoning / tool body. Alias of `pad`. */
  bodyPad: string;
  /** Inline indent of a reasoning body (the hairline rail). */
  bodyIndent: string;
  /** The chain block against the answer that follows it. Alias of `gap4`. */
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

/**
 * The semantic chain tokens, derived from `DENSITY_TOKENS` so a mode cannot
 * disagree with itself. `headerGap` and `bodyIndent` are the two that are not
 * a plain alias: a compact header sits flush, and the rail indent steps with
 * the mode.
 */
function traceSpacingFor(
  tokens: DensityTokens,
  headerGap: string,
  bodyIndent: string,
): TraceSpacingTokens {
  return {
    titleGap: tokens.gap3,
    groupGap: tokens.gap2,
    withinGap: tokens.gap1,
    headerGap,
    bodyPad: tokens.pad,
    bodyIndent,
    chainGap: tokens.gap4,
  };
}

export const TRACE_SPACING: Record<TraceDensity, TraceSpacingTokens> = {
  compact: traceSpacingFor(DENSITY_TOKENS.compact, "0rem", TRACE_SPACE_SCALE[5]),
  default: traceSpacingFor(
    DENSITY_TOKENS.default,
    DENSITY_TOKENS.default.gap1,
    TRACE_SPACE_SCALE[6],
  ),
  airy: traceSpacingFor(DENSITY_TOKENS.airy, DENSITY_TOKENS.airy.gap2, TRACE_SPACE_SCALE[7]),
};

export function isTraceDensity(value: string): value is TraceDensity {
  return (TRACE_DENSITIES as readonly string[]).includes(value);
}

export function normalizeTraceDensity(value: string | null | undefined): TraceDensity | null {
  if (!value) return null;
  const id = value.trim().toLowerCase();
  return isTraceDensity(id) ? id : null;
}

/** A phone-width viewport has no room for the desktop rhythm either way. */
export const MOBILE_DENSITY_QUERY = "(max-width: 640px)";

/** What a phone gets when nobody has chosen a rhythm. */
export const MOBILE_DEFAULT_DENSITY: TraceDensity = "airy";

/**
 * Resolution order, highest first:
 *
 *   1. a stored user choice (`dt-density`)   — always wins, desktop or phone
 *   2. the mobile default (airy)             — viewports <= 640px
 *   3. an explicit deployment density
 *   4. the builtin `default` rhythm
 *
 * The mobile default deliberately outranks a deployment default: a deployment
 * picks a density for a desktop panel, and a phone still needs air. Passing no
 * context (the old two-argument call) keeps the pre-mobile behaviour.
 */
export function resolveTraceDensity(
  stored: string | null | undefined,
  deployed: string | null | undefined,
  context: { mobile?: boolean } = {},
): TraceDensity {
  const chosen = normalizeTraceDensity(stored);
  if (chosen) return chosen;
  if (context.mobile) return MOBILE_DEFAULT_DENSITY;
  return normalizeTraceDensity(deployed) ?? DEFAULT_TRACE_DENSITY;
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

type DensityViewport = {
  matchMedia?(query: string): { matches: boolean };
};

/**
 * True when the viewport is phone-width. Never throws: a host without
 * `matchMedia` (bare jsdom, a server render) simply is not mobile.
 */
export function matchesMobileDensityViewport(viewport?: DensityViewport | null): boolean {
  const target =
    viewport === null ? null : (viewport ?? (typeof window === "undefined" ? null : window));
  if (!target || typeof target.matchMedia !== "function") return false;
  try {
    return target.matchMedia(MOBILE_DENSITY_QUERY).matches === true;
  } catch {
    return false;
  }
}
