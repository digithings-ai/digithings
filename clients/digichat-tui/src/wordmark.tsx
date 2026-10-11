import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";

import {
  SETTLED_MS,
  heroWordmarkLines,
  truecolorEnabled,
  wordmarkLines,
  type CellColor,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";
import { FRAME, reducedMotion } from "./motion";

/** Process start. A remount in the same process keeps this clock. */
let originMs: number | null = null;

function paint(color: CellColor): RGBA {
  if ("rgb" in color) return RGBA.fromInts(color.rgb, color.rgb, color.rgb);
  return RGBA.fromIndex(color.cube);
}

/** Test freeze, or the settled frame under reduced motion. */
function frozenMs(): number | null {
  if (reducedMotion()) return SETTLED_MS;
  const raw = process.env.DIGICHAT_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function DigichatWordmark({ cols }: { cols: number }) {
  const hold = frozenMs();
  const [elapsed, setElapsed] = useState(() => {
    if (hold != null) return 0;
    if (originMs === null) originMs = Date.now();
    return Date.now() - originMs;
  });

  useEffect(() => {
    if (hold != null) return;
    if (originMs === null) originMs = Date.now();
    const origin = originMs;
    const timer = setInterval(() => setElapsed(Date.now() - origin), FRAME.tick);
    setElapsed(Date.now() - origin);
    return () => clearInterval(timer);
  }, [hold]);

  const truecolor = truecolorEnabled(process.env.COLORTERM);
  const drawn =
    hold != null
      ? wordmarkLines("DIGICHAT", { cols, tMs: hold, truecolor })
      : heroWordmarkLines("DIGICHAT", { cols, elapsed, full: true, truecolor });

  return (
    <box width="100%" height={5} flexDirection="column">
      {drawn.lines.map((row, y) => (
        <text key={y}>
          {row.map((cell, x) =>
            cell.color ? (
              <span key={x} fg={paint(cell.color)}>
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

export const WORDMARK_ROWS = 5;
