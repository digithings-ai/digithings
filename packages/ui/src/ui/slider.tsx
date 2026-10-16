"use client"

/**
 * Slider — the stock shadcn (base-lyra) Base UI slider (#4306, batch K1),
 * vendored into the kit and token-bridged to the digiweb palette. Single-thumb
 * (`value={n}`) and range/multi-thumb (`value={[a, b]}`) both work: the thumb
 * count follows the resolved value array.
 *
 * Bridging deltas from the stock registry file (recorded, not silent):
 * - The stock `[min, max]` fallback would render two thumbs for a scalar
 *   `value`/`defaultValue`; the kit resolves a scalar to one thumb instead, so
 *   every repointed single-value consumer (TradesTab, the canon) keeps its
 *   single-thumb look.
 * - `bg-muted`/`bg-primary`/`bg-white` become the in-house accent mechanic —
 *   a 4px ink-tinted track, an accent fill, and a square accent thumb with the
 *   surface/hair ring — so the part reproduces the legacy controls `Slider`
 *   (`.ctl-slider-input`) the consumers were repointed from. `--color-primary`
 *   is ink/paper in the bridge, never the accent, so it cannot be used here.
 * - pointer cursors on the interactive parts + the kit's not-allowed disabled
 *   convention (#4306, phase 0.3).
 * - no physical `left/right`: Base UI positions thumbs with `inset-inline-start`
 *   (logical), so a `dir="rtl"` flip mirrors the whole track with no extra CSS.
 */

import { Slider as SliderPrimitive } from "@base-ui/react/slider"

import { cn } from "../lib/utils"

function Slider({
  className,
  defaultValue,
  value,
  min = 0,
  max = 100,
  ...props
}: SliderPrimitive.Root.Props) {
  const _values = Array.isArray(value)
    ? value
    : Array.isArray(defaultValue)
      ? defaultValue
      : [value ?? defaultValue ?? min]

  return (
    <SliderPrimitive.Root
      className={cn("data-horizontal:w-full data-vertical:h-full", className)}
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      thumbAlignment="edge"
      {...props}
    >
      <SliderPrimitive.Control className="relative flex w-full touch-none items-center select-none data-disabled:cursor-not-allowed data-disabled:opacity-50 data-vertical:h-full data-vertical:min-h-40 data-vertical:w-auto data-vertical:flex-col">
        <SliderPrimitive.Track
          data-slot="slider-track"
          className="relative h-1 w-full grow cursor-pointer overflow-hidden rounded-none bg-[color-mix(in_srgb,var(--ink)_14%,transparent)] select-none data-disabled:cursor-not-allowed data-vertical:h-full data-vertical:w-1"
        >
          <SliderPrimitive.Indicator
            data-slot="slider-range"
            className="bg-accent select-none data-horizontal:h-full data-vertical:w-full"
          />
        </SliderPrimitive.Track>
        {Array.from({ length: _values.length }, (_, index) => (
          <SliderPrimitive.Thumb
            data-slot="slider-thumb"
            key={index}
            className="relative block size-3.5 shrink-0 cursor-pointer rounded-none border-2 border-surface bg-accent shadow-[0_0_0_1px_var(--hair)] transition-[box-shadow] select-none after:absolute after:-inset-2 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 data-disabled:cursor-not-allowed data-disabled:opacity-50"
          />
        ))}
      </SliderPrimitive.Control>
    </SliderPrimitive.Root>
  )
}

export { Slider }
