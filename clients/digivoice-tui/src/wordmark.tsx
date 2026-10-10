/**
 * DIGIVOICE block wordmark. Same module and half-block language as the
 * digichat wordmark (packages/ui/src/components/chat/digichat-wordmark), the
 * ASCII Magic direction: 7×10 glyph cells drawn with ▀ ▄ █. The scramble plays
 * once, then settles; `DIGIVOICE_WORDMARK_MS` freezes it for screenshots and
 * for anyone who asked for reduced motion.
 */
import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";
import {
  heroWordmarkLines,
  truecolorEnabled,
  wordmarkLines,
  type CellColor,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";

const TICK_MS = 40;
const WORD = "DIGIVOICE";
let originMs: number | null = null;

function paint(color: CellColor): RGBA {
  if ("rgb" in color) return RGBA.fromInts(color.rgb, color.rgb, color.rgb);
  return RGBA.fromIndex(color.cube);
}

function frozenMs(): number | null {
  const raw = process.env.DIGIVOICE_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function DigivoiceWordmark({ cols }: { cols: number }) {
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
    const timer = setInterval(() => setElapsed(Date.now() - origin), TICK_MS);
    setElapsed(Date.now() - origin);
    return () => clearInterval(timer);
  }, [hold]);

  const truecolor = truecolorEnabled(process.env.COLORTERM);
  const drawn =
    hold != null
      ? wordmarkLines(WORD, { cols, tMs: hold, truecolor })
      : heroWordmarkLines(WORD, { cols, elapsed, full: true, truecolor });

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
