/**
 * DIGIVOICE block wordmark. Same module and half-block language as the
 * digichat wordmark (packages/ui/src/components/chat/digichat-wordmark), the
 * ASCII Magic direction: 7×10 glyph cells drawn with ▀ ▄ █. The scramble plays
 * once, then settles; `DIGIVOICE_WORDMARK_MS` freezes it for screenshots and
 * for anyone who asked for reduced motion.
 *
 * Nine glyphs need 63 columns, so a narrow terminal (a phone at 390×844 is
 * about 46 columns) gets a compact two-row braille lockup instead — the same
 * weight digiquant uses in its desk header.
 */
import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";
import {
  SETTLED_MS,
  heroWordmarkLines,
  truecolorEnabled,
  wordmarkLines,
  wordmarkPixels,
  type CellColor,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";

const TICK_MS = 40;
const WORD = "DIGIVOICE";
const HERO_ROWS = 5;
const HERO_COLS = WORD.length * 7;
/** Source rows kept in the compact lockup. Four samples per braille row. */
const SAMPLE_Y = [0, 1, 3, 4, 5, 6, 8, 9] as const;
/** Braille dots, two source columns by four sampled rows. Blank stays a space. */
const BRAILLE_DOTS = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
] as const;
const ACCENT_RGBA = RGBA.fromInts(0x3d, 0xd6, 0xc4);

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

/** Compact braille lockup, centred in `cols`. Two rows, ~32 columns wide. */
function compactRows(cols: number): { ch: string; fg: RGBA }[][] {
  const { pixels, width } = wordmarkPixels(SETTLED_MS, { word: WORD, gap: 0 });
  const on = new Set(pixels.map((p) => `${p.x},${p.y}`));
  const markCols = Math.ceil(width / 2);
  const pad = Math.max(0, Math.floor((cols - markCols) / 2));
  const rows: { ch: string; fg: RGBA }[][] = [];
  for (let r = 0; r < SAMPLE_Y.length / 4; r += 1) {
    const row: { ch: string; fg: RGBA }[] = [];
    for (let i = 0; i < pad; i += 1) row.push({ ch: " ", fg: ACCENT_RGBA });
    for (let c = 0; c < markCols; c += 1) {
      let bits = 0;
      for (let dy = 0; dy < 4; dy += 1) {
        const y = SAMPLE_Y[r * 4 + dy];
        for (let dx = 0; dx < 2; dx += 1) {
          if (on.has(`${c * 2 + dx},${y}`)) bits |= BRAILLE_DOTS[dy][dx];
        }
      }
      row.push({ ch: bits ? String.fromCodePoint(0x2800 + bits) : " ", fg: ACCENT_RGBA });
    }
    rows.push(row);
  }
  return rows;
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

  if (cols < HERO_COLS + 2) {
    const rows = compactRows(cols);
    return (
      <box width="100%" height={rows.length} flexDirection="column">
        {rows.map((row, y) => (
          <text key={y}>
            {row.map((cell, x) => (
              <span key={x} fg={cell.fg}>
                {cell.ch}
              </span>
            ))}
          </text>
        ))}
      </box>
    );
  }

  const truecolor = truecolorEnabled(process.env.COLORTERM);
  const drawn =
    hold != null
      ? wordmarkLines(WORD, { cols, tMs: hold, truecolor })
      : heroWordmarkLines(WORD, { cols, elapsed, full: true, truecolor });

  return (
    <box width="100%" height={HERO_ROWS} flexDirection="column">
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

export const WORDMARK_ROWS = HERO_ROWS;
