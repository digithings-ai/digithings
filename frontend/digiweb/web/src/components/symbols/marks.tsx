import type { ReactNode } from "react";

/**
 * Brand marks — promoted from the design reference (symbols/marks) as pure,
 * props-driven components. The four-stroke olympus signature was previously
 * copied verbatim in four places (olympus atlas-mark.tsx + AtlasLoader.tsx,
 * digiquant-web's OlympusMark, the reference specimen) — this file is the
 * canonical copy. Everything draws in currentColor so a mark inherits the
 * ink/accent of its livery scope. No CSS ships with this family: the marks
 * are pure SVG/text; stroke-draw loader animations stay in the consuming
 * app's CSS, targeted through `strokeClassPrefix`.
 */

export type OlympusMarkProps = {
  size?: number;
  className?: string;
  /** Accessible name (renders a <title> + role="img"); omitted → decorative. */
  title?: string;
  /**
   * Per-path class hook for stroke-draw animations: each stroke gets
   * `${prefix} ${prefix}-N` (N = 1..4, outer arc last). The olympus
   * dashboard's loader keys its draw keyframes off "atlas-loader-stroke";
   * the reference / digiquant hover replay uses the default
   * "olympus-stroke".
   */
  strokeClassPrefix?: string;
};

export function OlympusMark({
  size = 22,
  className,
  title,
  strokeClassPrefix = "olympus-stroke",
}: OlympusMarkProps) {
  const strokeClass = (n: number) => `${strokeClassPrefix} ${strokeClassPrefix}-${n}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : "true"}
      focusable="false"
      className={["olympus-mark", className].filter(Boolean).join(" ")}
    >
      {title ? <title>{title}</title> : null}
      <path
        className={strokeClass(1)}
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4.2774,32.5293a11.6485,11.6485,0,0,1,23.2219,1.32h0c0,3.2166.0022,11.6479.0022,11.6479"
      />
      <path
        className={strokeClass(2)}
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.3047,29.8574q-.0277-.4816-.0279-.97a16.61,16.61,0,1,1,33.2209,0v0c0,4.5869.0031,16.6095.0031,16.6095"
      />
      <circle
        className={strokeClass(3)}
        stroke="currentColor"
        strokeWidth="2"
        cx="16.5007"
        cy="33.4992"
        r="5.0328"
      />
      <path
        className={strokeClass(4)}
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M45.5,24A21.5,21.5,0,1,0,24,45.5H45.5Z"
      />
    </svg>
  );
}

export type WordmarkProps = {
  /**
   * Suffix after the prefix — "things", "quant". Wears var(--accent), so a
   * livery scope (e.g. `.accent-digiquant`) dresses it automatically.
   */
  suffix: ReactNode;
  /** Lockup prefix, in ink (default "digi"). */
  prefix?: ReactNode;
  className?: string;
};

/**
 * Wordmark — the text lockup grammar shared with the footer colophon:
 * `digi` in ink, the suffix wearing var(--accent). Mono, weight 500.
 * Carries token-backed utilities — consumers need an
 * `@source "<path-to>/digiweb/web/src/components/symbols"` line.
 */
export function Wordmark({ suffix, prefix = "digi", className }: WordmarkProps) {
  return (
    <span
      className={[
        "font-mono text-[1.25rem] font-medium tracking-[-0.01em] text-ink",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {prefix}
      <em className="not-italic text-accent">{suffix}</em>
    </span>
  );
}
