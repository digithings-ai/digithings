"use client"

import * as React from "react"

import { cn } from "../lib/utils"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select"

/**
 * PipelineSelect — labelled kit `Select` for choosing among pipelines. Composes
 * Select (no new primitive). With a single option it stays a real select but is
 * disabled and shows that option, so the control's place in the layout is stable
 * when only the baseline exists. Controlled: `value` / `onValueChange`.
 */
type PipelineOption = {
  id: string
  label: string
  /** e.g. "baseline" | "user" | "fork" — shown as a mute tag. */
  kind?: string
}

type PipelineSelectProps = {
  options: readonly PipelineOption[] | null | undefined
  value: string | null | undefined
  onValueChange?: (id: string) => void
  /** Visible label. */
  label?: string
  id?: string
  className?: string
  disabled?: boolean
}

function PipelineSelect({
  options,
  value,
  onValueChange,
  label = "Pipeline",
  id,
  className,
  disabled,
}: PipelineSelectProps) {
  const autoId = React.useId()
  const triggerId = id ?? `pipeline-select-${autoId}`
  const list = options ?? []
  const items = list.map((o) => ({ value: o.id, label: o.label }))
  const single = list.length <= 1
  const shown = value ?? (single ? (list[0]?.id ?? null) : null)

  return (
    <div data-slot="pipeline-select" className={cn("flex flex-col gap-1 font-mono", className)}>
      <label htmlFor={triggerId} className="text-[0.65rem] uppercase tracking-wider text-ink-mute">
        {label}
      </label>
      <Select
        items={items}
        value={shown}
        onValueChange={(v) => {
          if (typeof v === "string") onValueChange?.(v)
        }}
        disabled={disabled || single}
      >
        <SelectTrigger id={triggerId} className="w-full min-w-40 text-ink">
          <SelectValue placeholder={list.length === 0 ? "No pipelines" : "Select pipeline"} />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {list.map((o) => (
            <SelectItem key={o.id} value={o.id}>
              <span>{o.label}</span>
              {o.kind ? <span className="text-ink-mute">{o.kind}</span> : null}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export { PipelineSelect }
export type { PipelineOption, PipelineSelectProps }
