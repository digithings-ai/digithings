"use client";

import { useRef, useState, type ReactNode } from "react";
import { Marquee } from "../marquee/Marquee";
import { LiveBadge } from "../finance-tearsheet/LiveBadge";
import { toneClass } from "../finance-tearsheet/format";
import { cn } from "../../lib/utils";

/**
 * MarketBar — the terminal status line: `[● live] BTC 63,410 ▲0.40% … [pause]`.
 * Props-driven and honest: it renders exactly the cells it is given and never a
 * price of its own. The consumer owns the feed, the clock and the status.
 *
 * Built on `Marquee` (seamless -50% loop, edge fade, pause-on-hover). Honesty
 * and a11y contract:
 *  - the badge reads "live" ONLY for `status="live"`; `connecting` / `stale` /
 *    `offline` show a muted bracketed word instead (LiveBadge is not used);
 *  - no cells -> the text `connecting…` (or `offline`), never invented prices;
 *  - a cell with `value: null` shows an em dash and no change;
 *  - `asOf` (e.g. "as of 09-29") and `source` label recorded cells — `asOf`
 *    shows inline, `source` in the tooltip and the screen-reader summary;
 *  - the scrolling strip is `aria-hidden` and the region is `aria-live="off"`;
 *    a plain-text `sr-only` summary carries the same facts once, statically;
 *  - a pause control (the marquee auto-runs well past 5s; hover also pauses);
 *    it is hidden under reduced motion, where nothing moves;
 *  - tick flash is an opacity-only overlay re-keyed by a cell's `flashKey`
 *    (the initial `flashKey` never flashes; only a change does);
 *  - `--up` / `--down` colour ONLY the signed change (`toneClass`, the
 *    finance-tearsheet `is-pos` / `is-neg`), never the symbol or value.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/marquee.css";            (loop, pause, flash keyframes)
 *                 @import "@digithings/ui/styles/finance-tearsheet.css";  (LiveBadge dot, is-pos / is-neg)
 *                 @source "<path-to>/packages/ui/src/components/finance-composites";
 * CSS-only motion: no MotionProvider needed. Client component (pause state).
 */
export type MarketBarStatus = "connecting" | "live" | "stale" | "offline";

export type MarketBarCell = {
  /** Instrument symbol — "BTC", "SPY" … */
  symbol: string;
  /** Preformatted price, or null while unknown (renders "—"). */
  value: string | null;
  /** Signed percent change (0.4 = +0.40%); null / undefined hides the change. */
  changePct?: number | null;
  /** Freshness stamp shown inline for recorded cells — "as of 09-29". */
  asOf?: string;
  /** Origin of the number — tooltip and screen-reader text only. */
  source?: string;
  /** Change this to flash the cell (opacity wash). The first value never flashes. */
  flashKey?: string | number;
};

export type MarketBarProps = {
  /** The tape. Empty renders the `connecting…` empty state. */
  cells: MarketBarCell[];
  /** Feed state. Only "live" earns the live badge. */
  status: MarketBarStatus;
  /** Right-aligned slot — a clock like "00:00Z". Consumer-rendered (hydration is theirs). */
  trailing?: ReactNode;
  /** Marquee loop duration in seconds. Default 60. */
  speed?: number;
  /** Start paused. */
  defaultPaused?: boolean;
  /** Accessible name for the region. */
  ariaLabel?: string;
  className?: string;
};

const STATUS_WORD: Record<Exclude<MarketBarStatus, "live">, string> = {
  connecting: "connecting",
  stale: "stale",
  offline: "offline",
};

const STATUS_SR: Record<MarketBarStatus, string> = {
  connecting: "Connecting to the price feed.",
  live: "Prices are live.",
  stale: "Prices are stale; the feed has stopped ticking.",
  offline: "The price feed is offline.",
};

/** Change magnitude — the sign is carried by the arrow and the tone. */
function fmtChange(pct: number): string {
  return `${Math.abs(pct).toFixed(2)}%`;
}

function hasChange(c: MarketBarCell): c is MarketBarCell & { changePct: number } {
  return c.value !== null && c.changePct !== null && c.changePct !== undefined;
}

function srCell(c: MarketBarCell): string {
  const parts = [c.symbol, c.value ?? "no value"];
  if (hasChange(c)) {
    parts.push(c.changePct === 0 ? "unchanged" : `${c.changePct > 0 ? "up" : "down"} ${fmtChange(c.changePct)}`);
  }
  if (c.asOf) parts.push(c.asOf);
  if (c.source) parts.push(`source ${c.source}`);
  return parts.join(" ");
}

function Cell({ cell }: { cell: MarketBarCell }) {
  const initialFlash = useRef(cell.flashKey);
  const flashing = cell.flashKey !== undefined && cell.flashKey !== initialFlash.current;
  return (
    <span
      title={cell.source ? `${cell.symbol} · source ${cell.source}` : undefined}
      className="relative inline-flex items-baseline gap-2 whitespace-nowrap px-1 font-mono text-[0.72rem] [font-variant-numeric:tabular-nums]"
    >
      {flashing ? (
        <span
          key={String(cell.flashKey)}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-accent opacity-0 [animation:mb-flash_0.7s_ease-out] motion-reduce:hidden"
        />
      ) : null}
      <span className="tracking-[0.02em] text-ink">{cell.symbol}</span>
      <span className="text-ink-soft">{cell.value ?? "—"}</span>
      {hasChange(cell) ? (
        <span className={cn("inline-flex items-center gap-1", toneClass(cell.changePct) || "text-ink-mute")}>
          <span aria-hidden="true">{cell.changePct > 0 ? "▲" : cell.changePct < 0 ? "▼" : "·"}</span>
          {fmtChange(cell.changePct)}
        </span>
      ) : null}
      {cell.asOf ? <span className="text-ink-mute">{cell.asOf}</span> : null}
    </span>
  );
}

export function MarketBar({
  cells,
  status,
  trailing,
  speed = 60,
  defaultPaused = false,
  ariaLabel = "Market prices",
  className,
}: MarketBarProps) {
  const [paused, setPaused] = useState(defaultPaused);
  const empty = cells.length === 0;

  return (
    <div
      role="region"
      aria-label={ariaLabel}
      aria-live="off"
      className={cn(
        "flex h-8 min-w-0 items-center gap-3 font-mono text-[0.68rem] text-ink-mute",
        className,
      )}
    >
      {status === "live" ? (
        <LiveBadge label="live" ariaLabel="Prices are live" />
      ) : (
        <span className="shrink-0 tracking-[0.04em]">{`[${STATUS_WORD[status]}]`}</span>
      )}

      {empty ? (
        <span className="min-w-0 flex-1 truncate text-ink-soft">
          {status === "offline" ? "offline" : "connecting…"}
        </span>
      ) : (
        <>
          <div aria-hidden="true" className="min-w-0 flex-1">
            <Marquee speed={speed} paused={paused}>
              {cells.map((c) => (
                <Cell key={c.symbol} cell={c} />
              ))}
            </Marquee>
          </div>
          <p className="sr-only">{`${STATUS_SR[status]} ${cells.map(srCell).join("; ")}.`}</p>
        </>
      )}

      {trailing ? <span className="hidden shrink-0 sm:inline">{trailing}</span> : null}

      {empty ? null : (
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
          aria-label="Pause price ticker"
          className="shrink-0 cursor-pointer bg-transparent p-0 font-[inherit] text-ink-mute transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent motion-reduce:hidden"
        >
          {paused ? "[play]" : "[pause]"}
        </button>
      )}
    </div>
  );
}
