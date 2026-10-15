/**
 * DIGIVOICE block wordmark. Same module and half-block language as the
 * digichat wordmark (packages/ui/src/components/chat/digichat-wordmark), the
 * ASCII Magic direction: 7×10 glyph cells drawn with ▀ ▄ █. The scramble plays
 * once, then settles; `DIGIVOICE_WORDMARK_MS` freezes it for screenshots and
 * for anyone who asked for reduced motion.
 *
 * Nine glyphs need 63 columns, so a narrow terminal (a phone at 390×844 is
 * about 46 columns) gets a compact lockup instead: the same grid packed two
 * source columns by two source rows into one quadrant block (▘▝▖▗▚▞▛▜▙▟▀▄▌▐█),
 * half the width, still one Geist Mono cell and the same half-block language.
 */
import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";
import {
  SETTLED_MS,
  SHADES,
  heroWordmarkLines,
  truecolorEnabled,
  wordmarkLines,
  wordmarkPixels,
  type CellColor,
  type ShadeName,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";

const TICK_MS = 40;
const WORD = "DIGIVOICE";
const HERO_ROWS = 5;
const HERO_COLS = WORD.length * 7;
/** 2×2 source block (bits TL,TR,BL,BR) -> one quadrant block glyph. */
const QUADRANT = [
  " ",
  "▘",
  "▝",
  "▀",
  "▖",
  "▌",
  "▞",
  "▛",
  "▗",
  "▚",
  "▐",
  "▜",
  "▄",
  "▙",
  "▟",
  "█",
] as const;

function shadeRgba(name: ShadeName): RGBA {
  const value = SHADES[name].rgb;
  return RGBA.fromInts(value, value, value);
}

let originMs: number | null = null;

function paint(color: CellColor): RGBA {
  if ("rgb" in color) return RGBA.fromInts(color.rgb, color.rgb, color.rgb);
  return RGBA.fromIndex(color.cube);
}

function frozenMs(): number | null {
  const raw = process.env.DIGIVOICE_WORDMARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  // A freeze below the settle time would show a mid-scramble frame. Anyone who
  // asked for reduced motion, and every screenshot, wants the settled mark.
  return Math.max(value, SETTLED_MS);
}

/** Compact quadrant lockup, centred in `cols`. Five rows, ~32 columns wide. */
function compactRows(cols: number): { ch: string; fg: RGBA }[][] {
  const { pixels, width, height } = wordmarkPixels(SETTLED_MS, { word: WORD, gap: 0 });
  const shade = new Map<string, ShadeName>();
  for (const p of pixels) shade.set(`${p.x},${p.y}`, p.shade);
  const markCols = Math.ceil(width / 2);
  const pad = Math.max(0, Math.floor((cols - markCols) / 2));
  const rows: { ch: string; fg: RGBA }[][] = [];
  for (let cy = 0; cy < Math.ceil(height / 2); cy += 1) {
    const row: { ch: string; fg: RGBA }[] = [];
    for (let i = 0; i < pad; i += 1) row.push({ ch: " ", fg: shadeRgba("rest") });
    for (let cx = 0; cx < markCols; cx += 1) {
      const x = cx * 2;
      const y = cy * 2;
      const tl = shade.get(`${x},${y}`);
      const tr = shade.get(`${x + 1},${y}`);
      const bl = shade.get(`${x},${y + 1}`);
      const br = shade.get(`${x + 1},${y + 1}`);
      const bits = (tl ? 1 : 0) | (tr ? 2 : 0) | (bl ? 4 : 0) | (br ? 8 : 0);
      const tone = tl ?? tr ?? bl ?? br ?? "rest";
      row.push({ ch: QUADRANT[bits], fg: shadeRgba(tone) });
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
  const heroWidth = drawn.lines.reduce((max, row) => Math.max(max, row.length), 0);
  const pad = Math.max(0, Math.floor((cols - heroWidth) / 2));

  return (
    <box width="100%" height={HERO_ROWS} flexDirection="column">
      {drawn.lines.map((row, y) => (
        <text key={y}>
          {pad > 0 ? <span>{" ".repeat(pad)}</span> : null}
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
