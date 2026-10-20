/**
 * Chain-of-thought "view mode" contract, shared by the config schema,
 * embed-tenant bridge, chat prefs and the thread renderer.
 *
 * Kept dependency-free (no zod / no React) so server config code and client
 * UI can both fold a view mode into the per-group disclosure modes the
 * gallery thread understands:
 *
 *   hidden   — tool calls and reasoning are not rendered, answer only
 *   quiet    — the chain collapses to one summary line and never expands
 *   balanced — groups open while in progress, collapse when completed
 *   verbose  — groups stay fully open
 *
 * `thinking` is the reasoning-only override on top of the view mode:
 * `auto` follows the view mode, `collapsed` pins reasoning closed and
 * `open` pins it expanded.
 *
 * `quiet` / `verbose` are the product ids for the two levels previously
 * called `compact` / `detailed`; the old ids fold forward on read.
 */

export const VIEW_MODES = ["hidden", "quiet", "balanced", "verbose"] as const;
export type ViewMode = (typeof VIEW_MODES)[number];

/**
 * Retired view ids still found in saved configs, tenant entries, slash
 * invocations and browser state. `compact` was the closed-summary level
 * (`quiet`); `detailed` was the fully-open one (`verbose`).
 */
export const LEGACY_VIEW_MODE_ALIASES = {
  compact: "quiet",
  detailed: "verbose",
} as const;
export type LegacyViewMode = keyof typeof LEGACY_VIEW_MODE_ALIASES;

export const THINKING_MODES = ["auto", "collapsed", "open"] as const;
export type ThinkingMode = (typeof THINKING_MODES)[number];

/**
 * Effective disclosure mode for a single group (reasoning or tool calls)
 * after folding the view mode with the thinking override. "locked_open" is
 * intentionally not reachable here — it only exists on the raw thread props
 * for other consumers.
 */
export type ChainDisclosureMode = "off" | "collapsed" | "balanced" | "expanded";

export const DEFAULT_VIEW_MODE: ViewMode = "balanced";
export const DEFAULT_THINKING_MODE: ThinkingMode = "auto";

export function isViewMode(value: unknown): value is ViewMode {
  return typeof value === "string" && (VIEW_MODES as readonly string[]).includes(value);
}

/** True for the retired ids (`compact` / `detailed`) this module folds forward. */
export function isLegacyViewMode(value: unknown): value is LegacyViewMode {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(LEGACY_VIEW_MODE_ALIASES, value)
  );
}

/**
 * Current id, or a retired id folded forward, or `DEFAULT_VIEW_MODE` for
 * anything else. Read-path normaliser: config, tenant entries and prefs all
 * pass their value through here so `compact` / `detailed` keep working.
 */
export function normalizeViewMode(value: unknown): ViewMode {
  if (isViewMode(value)) return value;
  if (isLegacyViewMode(value)) return LEGACY_VIEW_MODE_ALIASES[value];
  return DEFAULT_VIEW_MODE;
}

export function isThinkingMode(value: unknown): value is ThinkingMode {
  return typeof value === "string" && (THINKING_MODES as readonly string[]).includes(value);
}

export function viewIsVisible(view: ViewMode): boolean {
  return view !== "hidden";
}

export function effectiveReasoningMode(
  view: ViewMode,
  thinking: ThinkingMode,
): ChainDisclosureMode {
  if (view === "hidden") return "off";
  if (thinking === "open") return "expanded";
  if (thinking === "collapsed") return "collapsed";
  if (view === "verbose") return "expanded";
  if (view === "balanced") return "balanced";
  // quiet — one summary line, never expanded
  return "collapsed";
}

export function effectiveToolCallsMode(view: ViewMode): ChainDisclosureMode {
  if (view === "hidden") return "off";
  if (view === "verbose") return "expanded";
  if (view === "balanced") return "balanced";
  // quiet — one summary line, never expanded
  return "collapsed";
}
