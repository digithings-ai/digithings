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
 * Prefs value literals (WS4). Structural twins of `ViewMode` /
 * `ThinkingMode` (`VIEW_MODES`, `THINKING_MODES` in
 * `apps/digichat/src/lib/view-modes.ts`, defaults `"balanced"` / `"auto"`).
 */
export type ViewMode = "hidden" | "compact" | "balanced" | "detailed";

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
  | "view"
  | "thinking"
  | "provider";
