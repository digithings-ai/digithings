/**
 * Slice C Brief panes.
 *
 * Slice A mounts `BRIEF_PANES` and `BriefPaneContent` inside `DeskShell`.
 * Slice B replaces `@/lib/desk/digiquant`, `@/lib/desk/movers`, and
 * `components/desk/atoms/*`. Fonts stay with the shell (`app/fonts.ts` loads
 * them; no face is loaded here).
 */
export { BRIEF_PANES, type DeskPaneModel, type PaneState } from './catalog';
export { BriefDesk, BriefDeskView, BriefPaneFrame } from './BriefDesk';
export { BriefPaneContent } from './bodies';
export { buildBriefPanes, loadingBriefPanes, focusSymbol } from './model';
export { deskShellEnabled } from './flag';
export type { BriefPaneView, BriefSnapshot } from './model';
