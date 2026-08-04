/**
 * Terminal brand marks — the `digi` prompt lockup and the hairline wordmark.
 *
 * Canonical implementation lives in @digithings/web
 * (components/symbols/terminal-marks.tsx); this specimen re-exports it for the
 * symbols page, exactly as marks.tsx does for the olympus signature.
 *
 * - TerminalMark: outlined `digi` + block cursor in currentColor, Geist Mono 400
 *   (the weight terminal text renders at). `variant="compact"` is the `d`
 *   reduction — use it below ~64px, where the full lockup's five character
 *   cells close up. This artwork is also the favicon source.
 * - TerminalWordmark: the default wordmark, plain mono text at tracking 0.
 * - HairlineWordmark: the display cut replicating the footer colophon
 *   (`.colo-word`) — 0.538%-of-em stroke, ink 30%. FULL-BLEED ONLY: the floor is
 *   on the em (~173px), which for `digithings` is a ~1036px rendered width
 *   before the stroke reaches one device pixel. Narrower than that, use
 *   TerminalWordmark.
 *
 * Kept in a separate file from marks.tsx on purpose: build-manifest.mjs names an
 * entry from the FIRST PascalCase export it finds, so aliasing these into
 * marks.tsx would silently rename that entry away from OlympusMark.
 */
import {
  HairlineWordmark as SharedHairlineWordmark,
  TerminalMark as SharedTerminalMark,
  TerminalWordmark as SharedTerminalWordmark,
} from "@digithings/web";

// Const aliases (not a bare `export … from`) so build-manifest.mjs's
// export-name scan keeps indexing this specimen on the symbols page.
export const TerminalMark = SharedTerminalMark;
export const TerminalWordmark = SharedTerminalWordmark;
export const HairlineWordmark = SharedHairlineWordmark;
