import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";

import { DIGICHAT } from "../../../packages/hero-banner/src/definitions";
import { nextTickMs, resolveLive, resolveMotion } from "../../../packages/hero-banner/src/engine";
import { bannerLines, colorModeFrom, type TermColor } from "../../../packages/hero-banner/src/tui";

/**
 * The DIGICHAT header mark, five rows, left-aligned. Same definition and
 * engine as the digichat-tui wordmark, drawn with this app's React: importing
 * the digichat-tui component pulls in a second React (or none) and its hooks
 * throw. DIGICHAT_WORDMARK_MS freezes it at one moment.
 */

export const WORDMARK_ROWS = 5;

const origin = Date.now();

function paint(color: TermColor): RGBA {
  return "hex" in color ? RGBA.fromHex(color.hex) : RGBA.fromIndex(color.cube);
}

function frozenMs(): number | null {
  const raw = process.env.DIGICHAT_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function DigichatWordmark({ cols }: { cols: number }) {
  const env = process.env;
  const holdMs = frozenMs();
  const [now, setNow] = useState(() => Date.now());
  const drawn = bannerLines(DIGICHAT, {
    cols,
    t: holdMs ?? now - origin,
    live: resolveLive(DIGICHAT, { env }),
    motion: resolveMotion({ env }),
    mode: colorModeFrom(env),
    scale: 1,
  });
  const wait = holdMs != null ? null : nextTickMs(DIGICHAT, drawn.phase);

  useEffect(() => {
    if (wait == null) return;
    const timer = setTimeout(() => setNow(Date.now()), wait);
    return () => clearTimeout(timer);
  }, [wait, now]);

  return (
    <box width="100%" height={drawn.lines.length} flexDirection="column" alignItems="flex-start">
      {drawn.lines.map((row, y) => (
        <text key={y}>
          {row.map((cell, x) =>
            cell.fg ? (
              <span key={x} fg={paint(cell.fg)} bg={cell.bg ? paint(cell.bg) : undefined}>
                {cell.ch}
              </span>
            ) : (
              <span key={x}>{cell.ch}</span>
            ),
          )}
        </text>
      ))}
    </box>
  );
}
