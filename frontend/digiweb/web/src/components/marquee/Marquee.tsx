import type { CSSProperties, ReactNode } from "react";
import { ICONS } from "../logos";

/**
 * Marquee — the infinite "built on" strip promoted from the design reference
 * (data/marquee-ticker), in our terminal register: a mono row drifting behind
 * an edge-fade mask, looping seamlessly, pausing on hover. Pure CSS, so a
 * plain server component; reduced motion stops the drift and the strip reads
 * statically.
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
 * mask, the loop keyframes, pause-on-hover and the reduced-motion stop live in
 * styles/marquee.css. Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/marquee.css";
 *                 @source "<path-to>/digiweb/web/src/components/marquee";
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
  "aria-label": ariaLabel,
  className,
}: MarqueeProps) {
  const dirClass = direction === "right" ? "mq-track--right" : "mq-track--left";
  const style = { "--mq-speed": `${speed}s` } as CSSProperties;
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
    <div className={`mq-row${className ? ` ${className}` : ""}`} aria-label={ariaLabel}>
      <div className={`mq-track ${dirClass}`} style={style}>
        {group(false)}
        {group(true)}
      </div>
    </div>
  );
}
