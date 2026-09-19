/**
 * Chain-of-thought "view mode" contract, shared by the config schema,
 * embed-tenant bridge, chat prefs and the thread renderer.
 *
 * Kept dependency-free (no zod / no React) so server config code and client
 * UI can both fold a view mode into the per-group disclosure modes the
 * gallery thread understands:
 *
 *   hidden   — tool calls and reasoning are not rendered, answer only
 *   compact  — groups render as closed dropdowns
 *   balanced — groups open while in progress, collapse when completed
 *   detailed — groups stay fully open
 *
 * `thinking` is the reasoning-only override on top of the view mode:
 * `auto` follows the view mode, `collapsed` pins reasoning closed and
 * `open` pins it expanded.
 */

export const VIEW_MODES = ["hidden", "compact", "balanced", "detailed"] as const;
export type ViewMode = (typeof VIEW_MODES)[number];

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
  if (view === "detailed") return "expanded";
  if (view === "balanced") return "balanced";
  return "collapsed";
}

export function effectiveToolCallsMode(view: ViewMode): ChainDisclosureMode {
  if (view === "hidden") return "off";
  if (view === "detailed") return "expanded";
  if (view === "balanced") return "balanced";
  return "collapsed";
}
