/**
 * Skeleton — the sk-* shimmer grammar promoted for #1548. Content-shaped
 * placeholder bars/blocks that hold the layout until data lands, then swap
 * 1:1 to the real thing with no reflow. Variants: line (text bar, `size="sm"`
 * for the label-height cut), block (value bar), circle (avatar), button
 * (pill stand-in). Width/height come from props or call-site utilities —
 * the shape defaults sit in `@layer components` in styles/controls-core.css
 * so utilities win. The shimmer is a translating ink-tint gradient (works in
 * any theme, no accent); prefers-reduced-motion drops the sweep and leaves
 * the static tint.
 *
 * Shapes are decorative (aria-hidden); the loading semantic belongs on the
 * container — SkeletonGroup renders it (aria-busy).
 *
 * Shaped against the olympus adoption targets: SnapshotSkeleton
 * (components/overview/daily-snapshot-panel.tsx), PipelineNodeDetail's
 * loading state, and the AtlasLoader Suspense fallbacks (the full-screen
 * brand loader itself stays app-local — it is a logo animation, not a
 * content-shaped placeholder).
 *
 * Loading-grammar ruling (#1548): the sk shimmer sweep is the ONE loading
 * grammar, app-wide. Olympus's legacy `animate-pulse` opacity bars adopt the
 * shimmer as a deliberate upgrade rather than this primitive growing a
 * `pulse` dress — two loading animations on one screen read as two apps.
 */
import type { CSSProperties, HTMLAttributes } from "react";

import { cx } from "./cx";

export type SkeletonVariant = "line" | "block" | "circle" | "button";

export type SkeletonProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: SkeletonVariant;
  /** Compact label-height line — the sk-line--sm grammar (variant="line" only). */
  size?: "sm";
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
};

const VARIANTS: Record<SkeletonVariant, string> = {
  line: "sk-line",
  block: "sk-block",
  circle: "sk-circle",
  button: "sk-btn",
};

export function Skeleton({
  variant = "line",
  size,
  width,
  height,
  className,
  style,
  ...props
}: SkeletonProps) {
  const sized =
    width !== undefined || height !== undefined ? { width, height, ...style } : style;
  return (
    <span
      data-slot="skeleton"
      aria-hidden="true"
      className={cx(
        "sk",
        VARIANTS[variant],
        variant === "line" && size === "sm" && "sk-line--sm",
        className,
      )}
      style={sized}
      {...props}
    />
  );
}

export type SkeletonGroupProps = HTMLAttributes<HTMLDivElement> & {
  /** Mirrors the container's aria-busy — flip to false once content lands. */
  busy?: boolean;
};

export function SkeletonGroup({ busy = true, ...props }: SkeletonGroupProps) {
  return <div data-slot="skeleton-group" aria-busy={busy} {...props} />;
}
