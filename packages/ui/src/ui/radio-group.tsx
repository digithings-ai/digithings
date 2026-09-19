"use client"

/**
 * RadioGroup / Radio — the shared selection control (#1548), promoted from the
 * controls layer into the kit (#4306, batch K1). Behavior comes from
 * `@base-ui/react`'s Radio / RadioGroup primitives (roving focus, keyboard
 * toggle, `data-checked` / `data-disabled` state); this file skins them to the
 * form-fields grammar — a 16px circle, hairline, accent dot, accent focus ring
 * — re-expressed in kit token utilities so `.ctl-radio*` can retire.
 *
 * Pair with a plain `<label>` (wrapping or `htmlFor`) — the control owns no
 * label of its own, same as the native inputs it replaces. `Checkbox` and
 * `Switch` remain on the controls layer for now; the kit already owns both, so
 * they have no live main-barrel consumer to repoint.
 */

import { Radio as RadioPrimitive } from "@base-ui/react/radio"
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group"

import { cn } from "../lib/utils"

export type RadioGroupProps = RadioGroupPrimitive.Props
export type RadioProps = RadioPrimitive.Root.Props

export function RadioGroup({ className, ...props }: RadioGroupProps) {
  return (
    <RadioGroupPrimitive
      data-slot="radio-group"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

export function Radio({ className, ...props }: RadioProps) {
  return (
    <RadioPrimitive.Root
      data-slot="radio"
      className={cn(
        "relative inline-flex size-4 shrink-0 cursor-pointer appearance-none items-center justify-center rounded-full border border-hair bg-surface p-0 transition-colors outline-none after:absolute after:-inset-3 focus-visible:ring-[3px] focus-visible:ring-ring/30 data-checked:border-accent data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <RadioPrimitive.Indicator
        data-slot="radio-indicator"
        className="absolute inset-[3px] rounded-full bg-accent"
      />
    </RadioPrimitive.Root>
  )
}
