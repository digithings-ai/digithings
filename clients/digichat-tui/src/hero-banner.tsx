import { RGBA } from "@opentui/core";
import { useEffect, useState } from "react";

import { nextTickMs, resolveLive, resolveMotion } from "../../../packages/hero-banner/src/engine";
import { bannerLines, colorModeFrom, type TermColor } from "../../../packages/hero-banner/src/tui";
import type { BannerDefinition } from "../../../packages/hero-banner/src/types";
import { reducedMotion } from "./motion";

/**
 * OpenTUI renderer for @digithings/hero-banner. Any banner definition, drawn
 * in half-blocks. LOADING plays once per process: a remount keeps the clock.
 * NO_MOTION / HERO_BANNER_MOTION=reduce / DIGI_REDUCED_MOTION draw the
 * settled mark with no timer;
 * HERO_BANNER_LIVE=0 (or `live={false}`) settles after LOADING.
 * `holdMs` freezes the banner at one moment (snapshots, tests).
 */

const origins = new Map<string, number>();

function paint(color: TermColor): RGBA {
  return "hex" in color ? RGBA.fromHex(color.hex) : RGBA.fromIndex(color.cube);
}

export function HeroBanner({
  def,
  cols,
  rows,
  live,
  scale,
  holdMs,
  align = "center",
  env = process.env,
}: {
  def: BannerDefinition;
  cols: number;
  rows?: number;
  live?: boolean;
  scale?: number;
  holdMs?: number | null;
  align?: "center" | "left";
  env?: Record<string, string | undefined>;
}) {
  const motion = resolveMotion({ env, prefersReduced: reducedMotion(env) });
  const liveOn = resolveLive(def, { env, config: live });
  const mode = colorModeFrom(env);
  const [now, setNow] = useState(() => Date.now());
  if (!origins.has(def.id)) origins.set(def.id, now);
  const origin = origins.get(def.id)!;
  const t = holdMs ?? now - origin;
  const drawn = bannerLines(def, { cols, rows, t, live: liveOn, motion, mode, scale });
  const wait = holdMs != null ? null : nextTickMs(def, drawn.phase);

  useEffect(() => {
    if (wait == null) return;
    const timer = setTimeout(() => setNow(Date.now()), wait);
    return () => clearTimeout(timer);
  }, [wait, now]);

  return (
    <box width="100%" height={drawn.lines.length} flexDirection="column" alignItems={align === "center" ? "center" : "flex-start"}>
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
