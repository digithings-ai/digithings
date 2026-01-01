"use client"

/**
 * Field — the label + control + hint/error wrapper (#1548), promoted from the
 * controls layer into the kit (#4306, batch K1). One component meshes the
 * accessible wiring callers otherwise hand-roll: a mono micro-cap label, an
 * optional hint, an optional error (which replaces the hint), and
 * `aria-describedby` / `aria-invalid` injected into the child control via
 * clone — so the control keeps its own props and ref. The child must accept
 * `id`, `aria-describedby`, and `aria-invalid` (native inputs and every shared
 * input do).
 *
 * Error is `--danger`, never `--down` (tokens.css house rule: money colors are
 * P&L-only). The `.ctl-field*` dress is translated into token utilities here,
 * so the controls CSS can retire.
 */

import { cloneElement, isValidElement, useId } from "react"
import type { ReactElement, ReactNode } from "react"

import { cn } from "../lib/utils"

type ControlProps = {
  id?: string
  "aria-describedby"?: string
  "aria-invalid"?: boolean | string
}

export type FieldProps = {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  htmlFor?: string
  required?: boolean
  className?: string
  children: ReactNode
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  required = false,
  className,
  children,
}: FieldProps) {
  const autoId = useId()
  // Resolve the control id FIRST: a child with its own id wins, and the
  // label follows it — never the synthetic id.
  const childId = isValidElement<ControlProps>(children) ? children.props.id : undefined
  const controlId = htmlFor ?? childId ?? `${autoId}-control`
  const hintId = `${autoId}-hint`
  const errorId = `${autoId}-error`
  const describedBy = [
    isValidElement<ControlProps>(children) ? children.props["aria-describedby"] : null,
    error ? errorId : null,
    hint && !error ? hintId : null,
  ]
    .filter(Boolean)
    .join(" ")

  const control = isValidElement<ControlProps>(children)
    ? cloneElement(children as ReactElement<ControlProps>, {
        id: childId ?? controlId,
        ...(describedBy ? { "aria-describedby": describedBy } : null),
        ...(error ? { "aria-invalid": true } : null),
        ...(required ? { "aria-required": true } : null),
      })
    : children

  return (
    <div
      data-slot="field"
      data-invalid={error ? true : undefined}
      className={cn("grid min-w-0 gap-[0.35rem]", className)}
    >
      <label
        htmlFor={controlId}
        className="cursor-pointer font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
      >
        {label}
        {required ? (
          <>
            <span aria-hidden="true" className="text-ink-soft">
              {" *"}
            </span>
            <span className="sr-only"> (required)</span>
          </>
        ) : null}
      </label>
      {control}
      {error ? (
        <p id={errorId} className="m-0 font-mono text-[0.62rem] leading-[1.5] text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="m-0 font-mono text-[0.62rem] leading-[1.5] text-ink-mute">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
