/**
 * Shared skin/chrome value types for the package thread + skins.
 *
 * These are structural twins of the app's deploy-config literals
 * (`ChromeModeSchema`, `PageContextModeSchema`, `UserAlignSchema` in
 * `apps/digichat/src/lib/deploy-config/schema.ts`, `ChainDisclosureMode` in
 * `apps/digichat/src/lib/view-modes.ts`). The app schema stays the single
 * source of truth for config validation; this module keeps the presentation
 * layer free of app imports (WS4).
 */

export type ChromeMode = "app" | "embed" | "modal" | "sidebar";

export type PageContextMode = "off" | "silent" | "visible";

export type UserAlign = "right" | "left";

export type ChainDisclosureMode =
  | "off"
  | "collapsed"
  | "balanced"
  | "expanded";

/**
 * How much of the agent's work (reasoning + tool calls) a client wants its
 * users to see. Structural twin of the app's `workVisibility` literal in
 * `apps/digichat/src/lib/deploy-config/schema.ts`.
 *
 * - `quiet` — one summary line ("Working — digisearch", "Used 3 tools"); the
 *   chain itself is never expanded.
 * - `balanced` — the chain is expanded while it runs, so the arguments and
 *   the reasoning are visible, and collapses when it finishes.
 * - `verbose` — the chain stays expanded; everything is readable.
 */
export type WorkVisibility = "hidden" | "quiet" | "balanced" | "verbose";

/** What the disclosure policy resolves to for the thread components. */
export type WorkDisclosure = {
  /**
   * A single summary line replaces the chain: the trace is folded away and
   * nothing of it is on screen.
   */
  summaryOnly: boolean;
  /** The chain stays open, so the row titles are visible. */
  chainOpen: boolean;
  /** The rows expand while their work streams. */
  openWhileRunning: boolean;
  /** The rows stay open once the work has finished. */
  openAtRest: boolean;
  /** Per-tool detail (arguments, results) is rendered. */
  showDetails: boolean;
};

/**
 * The client-facing view level becomes the work visibility the thread uses.
 * `hidden` is handled upstream (nothing is rendered at all), so it maps to
 * the balanced policy here.
 */
export function workVisibilityForView(
  view: ViewMode | undefined,
): WorkVisibility {
  switch (view) {
    case "hidden":
      return "hidden";
    case "quiet":
      return "quiet";
    case "verbose":
      return "verbose";
    default:
      return "balanced";
  }
}

/** The one place the visibility level becomes behaviour. */
export function resolveWorkDisclosure(
  visibility: WorkVisibility | undefined,
): WorkDisclosure {
  switch (visibility) {
    // Folded away: one line, nothing of the trace on screen.
    case "hidden":
      return {
        summaryOnly: true,
        chainOpen: false,
        openWhileRunning: false,
        openAtRest: false,
        showDetails: false,
      };
    // The titles only: the chain and its rows are there, folded.
    case "quiet":
      return {
        summaryOnly: false,
        chainOpen: true,
        openWhileRunning: false,
        openAtRest: false,
        showDetails: false,
      };
    // Open while the work streams, folded when the turn ends.
    case "balanced":
      return {
        summaryOnly: false,
        chainOpen: true,
        openWhileRunning: true,
        openAtRest: false,
        showDetails: true,
      };
    // Nothing ever folds: everything stays open and can be closed by hand.
    case "verbose":
      return {
        summaryOnly: false,
        chainOpen: true,
        openWhileRunning: true,
        openAtRest: true,
        showDetails: true,
      };
    default:
      return {
        summaryOnly: false,
        chainOpen: true,
        openWhileRunning: true,
        openAtRest: false,
        showDetails: true,
      };
  }
}

/**
 * Prefs value literals (WS4). Structural twins of `ViewMode` /
 * `ThinkingMode` (`VIEW_MODES`, `THINKING_MODES` in
 * `apps/digichat/src/lib/view-modes.ts`, defaults `"balanced"` / `"auto"`).
 */
export type ViewMode = "hidden" | "quiet" | "balanced" | "verbose";

/**
 * Retired view ids still found in saved prefs. `compact` was the
 * closed-summary level (now `quiet`); `detailed` was the fully-open one (now
 * `verbose`). The app's `view-modes.ts` holds the twin of this map.
 */
export const LEGACY_VIEW_MODE_ALIASES = {
  compact: "quiet",
  detailed: "verbose",
} as const;

/** A current view id, a retired one folded forward, or the default. */
export function normalizeViewPref(value: unknown): ViewMode {
  if (
    value === "hidden" ||
    value === "quiet" ||
    value === "balanced" ||
    value === "verbose"
  ) {
    return value;
  }
  if (value === "compact") return "quiet";
  if (value === "detailed") return "verbose";
  return "balanced";
}

export type ThinkingMode = "auto" | "collapsed" | "open";

/**
 * Session MCP server config (WS4). Structural twin of `SessionMcpConfig` in
 * `apps/digichat/src/components/stock/embed-mcp-flow.ts` (`auth` /
 * `source` literals mirror `McpAuthKind` / `McpSource`). The app type stays
 * the source of truth for BFF validation; identical shape keeps host values
 * assignable across the boundary.
 */
export type SkinMcpServerConfig = {
  id: string;
  label: string;
  url: string;
  auth: "none" | "bearer" | "oauth";
  token: string;
  extra: Record<string, string>;
  source: "operator" | "session";
};

/**
 * Composer menu pane ids (WS4). Structural twin of `ComposerMenuKind` in
 * `apps/digichat/src/components/stock/embed-composer-menu.tsx`.
 */
export type StockComposerMenuKind =
  | "settings"
  | "models"
  | "mcp"
  | "tools"
  | "language"
  | "effort"
  | "search-engine"
  | "view"
  | "thinking"
  | "provider"
  | "help";
