/**
 * Skeleton — the sk-* shimmer grammar (#1548), promoted from the controls
 * layer into the kit (#4306, batch K1). Content-shaped placeholder bars/blocks
 * that hold the layout until data lands, then swap 1:1 to the real thing with
 * no reflow. Variants: line (text bar, `size="sm"` for the label-height cut),
 * block (value bar), circle (avatar), button (button stand-in). Width/height
 * come from props or call-site utilities — the shape defaults are utilities, so
 * a call-site `h-20`/`w-2/5` still wins. The shimmer is a translating ink-tint
 * gradient (`@keyframes sk-shimmer`, declared on the kit's web-theme bridge);
 * prefers-reduced-motion drops the sweep and leaves the static tint.
 *
 * Shapes are decorative (aria-hidden); the loading semantic belongs on the
 * container — SkeletonGroup renders it (aria-busy).
 */

import type { CSSProperties, HTMLAttributes } from "react"

import { cn } from "../lib/utils"

export type SkeletonVariant = "line" | "block" | "circle" | "button"

export type SkeletonProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: SkeletonVariant
  /** Compact label-height line — the sk-line--sm grammar (variant="line" only). */
  size?: "sm"
  width?: CSSProperties["width"]
  height?: CSSProperties["height"]
}

const VARIANTS: Record<SkeletonVariant, string> = {
  line: "h-[0.72rem]",
  block: "h-6 w-3/5",
  circle: "size-10 shrink-0 rounded-full",
  button: "h-8 w-[6.6rem] shrink-0",
}

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
    width !== undefined || height !== undefined ? { width, height, ...style } : style
  return (
    <span
      data-slot="skeleton"
      aria-hidden="true"
      className={cn(
        "relative overflow-hidden rounded-none",
        variant === "line" && size === "sm" ? "h-[0.5rem]" : VARIANTS[variant],
        "bg-[color-mix(in_srgb,var(--ink)_9%,transparent)]",
        className,
      )}
      style={sized}
      {...props}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -translate-x-full bg-[linear-gradient(90deg,transparent,color-mix(in_srgb,var(--ink)_13%,transparent),transparent)] motion-reduce:animate-none motion-reduce:bg-none animate-[sk-shimmer_1.5s_var(--ease)_infinite]"
      />
    </span>
  )
}

export type SkeletonGroupProps = HTMLAttributes<HTMLDivElement> & {
  /** Mirrors the container's aria-busy — flip to false once content lands. */
  busy?: boolean
}

export function SkeletonGroup({ busy = true, ...props }: SkeletonGroupProps) {
  return <div data-slot="skeleton-group" aria-busy={busy} {...props} />
}
