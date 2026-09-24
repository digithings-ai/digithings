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
