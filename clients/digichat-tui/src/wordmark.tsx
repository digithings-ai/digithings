import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";

import {
  CYCLE_MS,
  truecolorEnabled,
  wordmarkLines,
  type CellColor,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";

const TICK_MS = 40;

function paint(color: CellColor): RGBA {
  if ("rgb" in color) return RGBA.fromInts(color.rgb, color.rgb, color.rgb);
  return RGBA.fromIndex(color.cube);
}

function frozenMs(): number | null {
  const raw = process.env.DIGICHAT_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function DigichatWordmark({ cols }: { cols: number }) {
  const [tMs, setTMs] = useState(() => frozenMs() ?? 0);
  const hold = frozenMs();

  useEffect(() => {
    if (hold != null) return;
    const start = Date.now();
    const timer = setInterval(() => {
      setTMs((Date.now() - start) % CYCLE_MS);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [hold]);

  const truecolor = truecolorEnabled(process.env.COLORTERM);
  const drawn = wordmarkLines("DIGICHAT", { cols, tMs: hold ?? tMs, truecolor });

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
