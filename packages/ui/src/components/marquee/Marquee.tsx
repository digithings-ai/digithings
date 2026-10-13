"use client";

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";
import { ICONS } from "../logos";

/**
 * Marquee — the infinite "built on" strip promoted from the design reference
 * (data/marquee-ticker), in our terminal register: a mono row drifting behind
 * an edge-fade mask, looping seamlessly. Hover pins the computed transform so
 * the strip freezes where it is. Reduced motion stops the drift and the strip
 * reads statically.
 *
 * Seamless loop mechanics: the content renders twice as two `.mq-group` spans
 * and the track translates exactly -50% per cycle. Each group carries the
 * inter-item gap as its own padding-right (and the track itself has NO gap),
 * so half the track width equals exactly one period and the wrap is invisible.
 *
 * Items may be plain strings (legacy dress: mono chip with a leading accent
 * dot) or `{ name, icon }` objects — `icon` is a slug in the shared Simple
 * Icons registry (components/logos.ts) and renders as a small glyph before the
 * name; an object without a resolvable icon renders text-only. Arbitrary
 * `children` are also duplicated into the two groups. The overflow + edge-fade
 * mask, the loop keyframes, the pause control and the reduced-motion stop live in
 * styles/marquee.css. Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/marquee.css";
 *                 @source "<path-to>/packages/ui/src/components/marquee";
 */
export type MarqueeItem = {
  /** Display name (mono lozenge). */
  name: string;
  /** Simple Icons slug in the shared registry (components/logos.ts). */
  icon?: string;
};

export type MarqueeProps = {
  /** Row contents — strings (accent-dot chips) or `{ name, icon }` lozenges. */
  items?: (string | MarqueeItem)[];
  /** Arbitrary content instead of `items` (duplicated for the seamless loop). */
  children?: ReactNode;
  /** Drift direction. */
  direction?: "left" | "right";
  /** Loop duration in seconds (one full -50% translate). */
  speed?: number;
  /** Item text tone — reference dress is "soft"; "mute" for quieter strips. */
  tone?: "soft" | "mute";
  /** Hold the drift still (a consumer's pause control). Hover pauses regardless. */
  paused?: boolean;
  /** Accessible label for the strip. */
  "aria-label"?: string;
  /** Extra classes on the masked row wrapper. */
  className?: string;
};

// Literal class strings (not a `text-ink-${tone}` template) so Tailwind's
// @source scan generates both variants.
const TONE: Record<"soft" | "mute", string> = {
  soft: "text-ink-soft",
  mute: "text-ink-mute",
};

/** Horizontal translation from a computed `matrix(...)` or our own `translateX(Npx)`. */
export function matrixTranslateX(transform: string): number | null {
  const value = transform.trim();
  if (value === "" || value === "none") return 0;
  const translate = value.match(/^translateX\(([-\d.]+)px\)$/);
  if (translate) {
    const n = Number(translate[1]);
    return Number.isFinite(n) ? n : null;
  }
  const matrix = value.match(/^matrix\(([^)]+)\)$/);
  if (!matrix) return null;
  const parts = matrix[1].split(",").map((part) => Number(part.trim()));
  if (parts.length !== 6 || parts.some((n) => !Number.isFinite(n))) return null;
  return parts[4];
}

/**
 * Progress through one loop, 0 inclusive to 1 exclusive.
 * Left drift runs from 0 to `-period`. Right drift runs from `-period` to 0.
 */
export function loopProgress(
  translateX: number,
  periodPx: number,
  direction: "left" | "right",
): number {
  if (!(periodPx > 0) || !Number.isFinite(translateX)) return 0;
  const along = direction === "left" ? -translateX / periodPx : (translateX + periodPx) / periodPx;
  let wrapped = along % 1;
  if (wrapped < 0) wrapped += 1;
  return wrapped || 0;
}

/** Negative delay that restarts a linear loop at `progress`. */
export function resumeDelaySeconds(progress: number, durationSeconds: number): string {
  const p = Number.isFinite(progress) ? Math.min(1, Math.max(0, progress)) : 0;
  const d = Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : 0;
  return `-${p * d}s`;
}

function Chip({ item, tone }: { item: string | MarqueeItem; tone: "soft" | "mute" }) {
  const isPlain = typeof item === "string";
  const name = isPlain ? item : item.name;
  const icon = !isPlain && item.icon ? (ICONS[item.icon] ?? null) : null;
  return (
    <span
      className={`inline-flex items-center gap-[0.55rem] font-mono text-[0.82rem] whitespace-nowrap ${TONE[tone]}`}
    >
      {isPlain ? <span className="h-1 w-1 rounded-full bg-accent" aria-hidden="true" /> : null}
      {icon ? (
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <path d={icon.path} fill="currentColor" />
        </svg>
      ) : null}
      {name}
    </span>
  );
}

export function Marquee({
  items,
  children,
  direction = "left",
  speed = 34,
  tone = "soft",
  paused,
  "aria-label": ariaLabel,
  className,
}: MarqueeProps) {
  const dirClass = direction === "right" ? "mq-track--right" : "mq-track--left";
  const trackRef = useRef<HTMLDivElement>(null);
  const hovering = useRef(false);
  const [frozen, setFrozen] = useState<string | null>(null);
  const [resumeDelay, setResumeDelay] = useState("0s");

  const pin = () => {
    const track = trackRef.current;
    if (!track || frozen) return;
    const tx = matrixTranslateX(getComputedStyle(track).transform);
    if (tx === null) return;
    setFrozen(`translateX(${tx}px)`);
  };

  const release = () => {
    if (!frozen) return;
    const track = trackRef.current;
    const tx = matrixTranslateX(frozen) ?? 0;
    const period = track ? track.scrollWidth / 2 : 0;
    const progress = loopProgress(tx, period, direction);
    setResumeDelay(resumeDelaySeconds(progress, speed));
    setFrozen(null);
  };

  useEffect(() => {
    if (paused || hovering.current || frozen === null) return;
    const track = trackRef.current;
    const tx = matrixTranslateX(frozen) ?? 0;
    const period = track ? track.scrollWidth / 2 : 0;
    setResumeDelay(resumeDelaySeconds(loopProgress(tx, period, direction), speed));
    setFrozen(null);
  }, [paused, frozen, direction, speed]);

  const onPointerEnter = (event: PointerEvent<HTMLDivElement>) => {
    hovering.current = true;
    if (event.pointerType === "touch") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    pin();
  };

  const onPointerLeave = () => {
    hovering.current = false;
    if (!paused) release();
  };

  const style = {
    "--mq-speed": `${speed}s`,
    animationDelay: frozen ? undefined : resumeDelay,
    animation: frozen ? "none" : undefined,
    transform: frozen ?? undefined,
  } as CSSProperties;
  const group = (hidden: boolean) => (
    <span className="mq-group" aria-hidden={hidden || undefined}>
      {items
        ? items.map((item, i) => (
            <Chip key={`${typeof item === "string" ? item : item.name}-${i}`} item={item} tone={tone} />
          ))
        : children}
    </span>
  );

  return (
    <div
      className={`mq-row${className ? ` ${className}` : ""}`}
      aria-label={ariaLabel}
      data-paused={paused ? "true" : undefined}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <div ref={trackRef} className={`mq-track ${dirClass}`} style={style}>
        {group(false)}
        {group(true)}
      </div>
    </div>
  );
}
