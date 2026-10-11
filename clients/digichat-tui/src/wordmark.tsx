import { DIGICHAT } from "../../../packages/hero-banner/src/definitions";
import { HeroBanner } from "./hero-banner";

function frozenMs(): number | null {
  const raw = process.env.DIGICHAT_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

/** The header mark: the DIGICHAT hero banner, five rows, left-aligned.
 *  DIGICHAT_WORDMARK_MS freezes it at one moment. */
export function DigichatWordmark({ cols }: { cols: number }) {
  return <HeroBanner def={DIGICHAT} cols={cols} scale={1} align="left" holdMs={frozenMs()} />;
}

export const WORDMARK_ROWS = 5;
