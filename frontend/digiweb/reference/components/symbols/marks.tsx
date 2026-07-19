/**
 * Product brand marks — promoted to @digithings/web (#1548,
 * components/symbols/marks.tsx), which is now the canonical copy of the
 * four-stroke olympus signature (previously quadruplicated across the olympus
 * dashboard, digiquant-web, and here). This specimen simply re-exports the
 * shared primitives for the symbols page and the phone demo.
 *
 * - OlympusMark: four strokes in currentColor; strokes keep their
 *   `olympus-stroke-N` classes by default so the dashboard's stroke-draw
 *   loader animation could be replayed via CSS if ever wanted here
 *   (`strokeClassPrefix` retargets them, e.g. to `atlas-loader-stroke-N`).
 * - Wordmark: the text lockup grammar shared with the footer colophon —
 *   `digi` in ink, the suffix wearing var(--accent) so a livery scope
 *   (e.g. `.accent-digiquant`) dresses it automatically. Mono, weight 500.
 *
 * digichat has no separate brand mark — its module emblem (the `>▮` terminal
 * prompt in emblems.tsx) is its symbol.
 */
import { OlympusMark as SharedOlympusMark, Wordmark as SharedWordmark } from "@digithings/web";

// Const aliases (not a bare `export … from`) so build-manifest.mjs's
// export-name scan keeps indexing this specimen on the symbols page.
export const OlympusMark = SharedOlympusMark;
export const Wordmark = SharedWordmark;
