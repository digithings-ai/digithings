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
 * - `quiet` — the chain is there, folded, and its header reads as a status
 *   line ("Working — digisearch", "Used 3 tools"); the rows stay closed.
 * - `balanced` — the chain is expanded while it runs, so the arguments and
 *   the reasoning are visible, and collapses when it finishes.
 * - `verbose` — the chain stays expanded; everything is readable.
 *
 * There is no `hidden` level any more: a client that wants the least reads
 * the live status line and nothing else, which is `quiet`. Old values fold
 * forward — see `LEGACY_VIEW_MODE_ALIASES` and `workVisibilityForView`.
 */
export type WorkVisibility = "quiet" | "balanced" | "verbose";

/** What the disclosure policy resolves to for the thread components. */
export type WorkDisclosure = {
  /**
   * A single summary line replaces the chain. The hidden level is gone, so
   * this is always false now; it stays on the type while the thread renderer
   * still holds the branch that reads it.
   *
   * @deprecated the chain folds to its titles instead (`quiet`).
   */
  summaryOnly: boolean;
  /** The rows expand while their work streams. */
  openWhileRunning: boolean;
  /** The rows stay open once the work has finished. */
  openAtRest: boolean;
  /** Per-tool detail (arguments, results) is rendered. */
  showDetails: boolean;
  /**
   * The chain folds as soon as the answer starts streaming, rather than
   * waiting for the turn to end. The quiet level: the titles are there while
   * the agent works, then they get out of the way of the answer.
   */
  foldOnAnswer: boolean;
};

/**
 * The client-facing view level becomes the work visibility the thread uses.
 * The retired `hidden` level means "the titles only, folded" now, so a host
 * bundle still carrying it folds forward to `quiet`.
 */
export function workVisibilityForView(
  view: ViewMode | undefined,
): WorkVisibility {
  switch (view) {
    case "quiet":
      return "quiet";
    case "verbose":
      return "verbose";
    // Includes `balanced` and a host bundle that has not been rebuilt yet.
    default:
      return (view as string | undefined) === "hidden" ? "quiet" : "balanced";
  }
}

/** The one place the visibility level becomes behaviour. */
export function resolveWorkDisclosure(
  visibility: WorkVisibility | undefined,
): WorkDisclosure {
  switch (visibility) {
    // The titles only: the chain and its rows are there, folded. The folded
    // header is the status line, so this is also the level that used to be
    // called `hidden`.
    case "quiet":
      return {
        summaryOnly: false,
        openWhileRunning: false,
        openAtRest: false,
        showDetails: false,
        foldOnAnswer: true,
      };
    // Open while the work streams, folded when the turn ends.
    case "balanced":
      return {
        summaryOnly: false,
        openWhileRunning: true,
        openAtRest: false,
        showDetails: true,
        foldOnAnswer: false,
      };
    // Nothing ever folds: everything stays open and can be closed by hand.
    case "verbose":
      return {
        summaryOnly: false,
        openWhileRunning: true,
        openAtRest: true,
        showDetails: true,
        foldOnAnswer: false,
      };
    default:
      return {
        summaryOnly: false,
        openWhileRunning: true,
        openAtRest: false,
        showDetails: true,
        foldOnAnswer: false,
      };
  }
}

/**
 * Prefs value literals (WS4). Structural twins of `ViewMode` /
 * `ThinkingMode` (`VIEW_MODES`, `THINKING_MODES` in
 * `apps/digichat/src/lib/view-modes.ts`, defaults `"balanced"` / `"auto"`).
 */
export type ViewMode = "quiet" | "balanced" | "verbose";

/**
 * Retired view ids still found in saved prefs. `hidden` was the level that
 * folded the trace to a single line — the chain folds to its titles and shows
 * the same status line now, so it means `quiet`. `compact` was the
 * closed-summary level (also now `quiet`); `detailed` was the fully-open one
 * (now `verbose`). The app's `view-modes.ts` holds the twin of this map.
 */
export const LEGACY_VIEW_MODE_ALIASES = {
  hidden: "quiet",
  compact: "quiet",
  detailed: "verbose",
} as const;

/** A current view id, a retired one folded forward, or the default. */
export function normalizeViewPref(value: unknown): ViewMode {
  if (value === "quiet" || value === "balanced" || value === "verbose") {
    return value;
  }
  if (value === "hidden" || value === "compact") return "quiet";
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
