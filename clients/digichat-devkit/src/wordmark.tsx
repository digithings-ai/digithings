import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";

import { DIGICHAT } from "../../../packages/hero-banner/src/definitions";
import { nextTickMs, resolveLive, resolveMotion } from "../../../packages/hero-banner/src/engine";
import { colorModeFrom, compactLines, type TermColor } from "../../../packages/hero-banner/src/tui";

/**
 * The devkit header mark: the universal digichat hero banner, packed into
 * compact cells. Same definition, same PIXEL_7X10 font, same scramble LOADING
 * and LIVE animation the digichat TUI draws — only the cell encoding differs,
 * so the mark is small enough to sit in the top-left corner without becoming a
 * second wordmark to keep in step with the hero.
 *
 * DIGICHAT_DEVKIT_MARK_MS freezes it at one moment (snapshots, tests).
 * HERO_BANNER_MOTION and HERO_BANNER_LIVE are honoured, like every surface.
 */

function paint(color: TermColor): RGBA {
  return "hex" in color ? RGBA.fromHex(color.hex) : RGBA.fromIndex(color.cube);
}

function frozenMs(): number | null {
  const raw = process.env.DIGICHAT_DEVKIT_MARK_MS;
  if (raw == null || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

/** Cells across and rows down, read off the definition so the layout maths in
 *  the app cannot drift from what is actually drawn. */
const settled = compactLines(DIGICHAT, { t: 0, motion: "reduced", mode: "256" });
export const MARK_COLS = settled.width;
export const MARK_ROWS = settled.lines.length;

/** LOADING plays once per process: a remount keeps the clock. */
const origins = new Map<string, number>();

export function DigichatMark() {
  const motion = resolveMotion({ env: process.env });
  const live = resolveLive(DIGICHAT, { env: process.env });
  const mode = colorModeFrom(process.env);
  const [now, setNow] = useState(() => Date.now());
  if (!origins.has(DIGICHAT.id)) origins.set(DIGICHAT.id, now);
  const origin = origins.get(DIGICHAT.id)!;
  const hold = frozenMs();
  const drawn = compactLines(DIGICHAT, { t: hold ?? now - origin, live, motion, mode });
  const wait = hold != null ? null : nextTickMs(DIGICHAT, drawn.phase);

  useEffect(() => {
    if (wait == null) return;
    const timer = setTimeout(() => setNow(Date.now()), wait);
    return () => clearTimeout(timer);
  }, [wait, now]);

  return (
    <box width={MARK_COLS} height={MARK_ROWS} flexDirection="column">
      {drawn.lines.map((row, y) => (
        <text key={y}>
          {row.map((cell, x) => (cell.fg ? <span key={x} fg={paint(cell.fg)}>{cell.ch}</span> : <span key={x}>{cell.ch}</span>))}
        </text>
      ))}
    </box>
  );
}