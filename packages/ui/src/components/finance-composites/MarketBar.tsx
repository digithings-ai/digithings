"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Marquee } from "../marquee/Marquee";
import { toneClass } from "../finance-tearsheet/format";
import { cn } from "../../lib/utils";

/**
 * MarketBar — the terminal status line: a green square, then
 * `BTC 63,410 ▲0.40% …`, then `[pause]`. Props-driven and honest: it renders
 * exactly the cells it is given and never a price of its own. The consumer
 * owns the feed, the clock and the status.
 *
 * Built on `Marquee` (seamless -50% loop, edge fade, pause-on-hover). Each
 * cell carries its own horizontal padding and the group gap is zero, so the
 * join where the list repeats is the same gap as every other pair. Honesty
 * and a11y contract:
 *  - `status="live"` is a green square (it may pulse). The word is not shown.
 *    `connecting` / `stale` / `offline` show a muted bracketed word;
 *  - no cells -> the text `connecting…` (or `offline`), never invented prices;
 *  - a cell with `value: null` shows an em dash for the price;
 *  - a missing percent is an em dash, never a fabricated number;
 *  - `asOf` (e.g. "as of 09-29") and `source` label recorded cells — `asOf`
 *    shows inline, `source` in the tooltip and the screen-reader summary;
 *  - the scrolling strip is `aria-hidden` and the region is `aria-live="off"`;
 *    a plain-text `sr-only` summary carries the same facts once, statically;
 *  - a pause control (the marquee auto-runs well past 5s; hover also pauses);
 *    it is hidden under reduced motion, where nothing moves;
 *  - when a percent actually changes, only that number pulses. The first
 *    observation does not. The symbol, the price, and the row stay still;
 *  - `--up` / `--down` colour ONLY the signed change (`toneClass`, the
 *    finance-tearsheet `is-pos` / `is-neg`), never the symbol or value.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/marquee.css";
 *                 @import "@digithings/ui/styles/finance-tearsheet.css";
 *                 @source "<path-to>/packages/ui/src/components/finance-composites";
 * CSS-only motion: no MotionProvider needed. Client component (pause state).
 */
export type MarketBarStatus = "connecting" | "live" | "stale" | "offline";

export type MarketBarCell = {
  /** Instrument symbol — "BTC", "SPY" … */
  symbol: string;
  /** Preformatted price, or null while unknown (renders "—"). */
  value: string | null;
  /** Signed percent change (0.4 = +0.40%). Null or missing renders an em dash. */
  changePct?: number | null;
  /** Freshness stamp shown inline for recorded cells — "as of 09-29". */
  asOf?: string;
  /** Origin of the number — tooltip and screen-reader text only. */
  source?: string;
  /** Retained for callers. The tape pulses from `changePct`, not this key. */
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
  live: "The price feed is ticking.",
  stale: "Prices are stale; the feed has stopped ticking.",
  offline: "The price feed is offline.",
};

/**
 * Pulse generation for a percent. The first observation never pulses. A null
 * or non-finite percent never pulses. An unchanged number never pulses.
 */
export function percentPulseGeneration(
  previous: number | null | undefined,
  next: number | null,
  generation: number,
): { previous: number | null; generation: number } {
  const pct = next !== null && Number.isFinite(next) ? next : null;
  if (previous === undefined) return { previous: pct, generation };
  if (pct !== null && pct !== previous) return { previous: pct, generation: generation + 1 };
  return { previous: pct, generation };
}

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
  } else {
    parts.push("percent unavailable");
  }
  if (c.asOf) parts.push(c.asOf);
  if (c.source) parts.push(`source ${c.source}`);
  return parts.join(" ");
}

function PercentNumber({ pct }: { pct: number | null }) {
  const [generation, setGeneration] = useState(0);
  const previous = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    const next = percentPulseGeneration(previous.current, pct, generation);
    previous.current = next.previous;
    if (next.generation !== generation) setGeneration(next.generation);
  }, [pct, generation]);
  const pulsing = generation > 0 && pct !== null && Number.isFinite(pct);
  return (
    <span key={generation} data-mb="pct" className={pulsing ? "mb-pct-pulse" : undefined}>
      {pct === null || !Number.isFinite(pct) ? "—" : fmtChange(pct)}
    </span>
  );
}

function Cell({ cell }: { cell: MarketBarCell }) {
  const pct = hasChange(cell) ? cell.changePct : null;
  return (
    <span
      title={cell.source ? `${cell.symbol} · source ${cell.source}` : undefined}
      className="mb-cell inline-flex items-baseline gap-2 whitespace-nowrap px-[1.15rem] font-mono text-[0.72rem] [font-variant-numeric:tabular-nums]"
    >
      <span className="tracking-[0.02em] text-ink">{cell.symbol}</span>
      <span className="mb-price text-ink-soft">{cell.value ?? "—"}</span>
      <span
        className={cn(
          "mb-pct inline-flex items-center justify-end gap-1",
          pct === null ? "text-ink-mute" : toneClass(pct) || "text-ink-mute",
        )}
      >
        {pct === null ? null : (
          <span aria-hidden="true">{pct > 0 ? "▲" : pct < 0 ? "▼" : "·"}</span>
        )}
        <PercentNumber pct={pct} />
      </span>
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
        <span className="mb-live-mark" aria-hidden="true" />
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
            <Marquee className="mb-tape" speed={speed} paused={paused}>
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
