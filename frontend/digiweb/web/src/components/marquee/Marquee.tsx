import type { CSSProperties, ReactNode } from "react";

/**
 * Marquee — the infinite "built on" strip promoted from the design reference
 * (data/marquee-ticker), in our terminal register: a mono row drifting behind
 * an edge-fade mask, looping seamlessly (content duplicated, track translated
 * exactly -50%), pausing on hover. Pure CSS, so a plain server component;
 * reduced motion stops the drift and the strip reads statically.
 *
 * Pass `items` (each rendered as a mono chip with a leading accent dot) or
 * arbitrary `children` (duplicated into two groups for the seamless loop). The
 * overflow + edge-fade mask, the loop keyframes, pause-on-hover and the
 * reduced-motion stop live in styles/marquee.css. Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/marquee.css";
 *                 @source "<path-to>/digiweb/web/src/components/marquee";
 */
export type MarqueeProps = {
  /** Row contents as strings — each a mono chip with a leading accent dot. */
  items?: string[];
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

  return (
    <div className={`mq-row${className ? ` ${className}` : ""}`} aria-label={ariaLabel}>
      <div className={`mq-track ${dirClass}`} style={style}>
        {items ? (
          [...items, ...items].map((item, i) => (
            <span
              className={`inline-flex items-center gap-[0.7rem] font-mono text-[0.82rem] whitespace-nowrap ${TONE[tone]}`}
              key={`${item}-${i}`}
              aria-hidden={i >= items.length || undefined}
            >
              <span className="h-1 w-1 rounded-full bg-accent" aria-hidden="true" />
              {item}
            </span>
          ))
        ) : (
          <>
            <span className="inline-flex items-center gap-[2.2rem] whitespace-nowrap">
              {children}
            </span>
            <span
              className="inline-flex items-center gap-[2.2rem] whitespace-nowrap"
              aria-hidden="true"
            >
              {children}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
