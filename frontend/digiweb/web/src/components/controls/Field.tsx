/**
 * Field — the label + control + hint/error wrapper. One component meshes
 * the accessible wiring callers otherwise hand-roll: a mono micro-cap
 * label, an optional hint, an optional error (which replaces the hint),
 * and `aria-describedby` / `aria-invalid` injected into the child control
 * via clone — so the control keeps its own props and ref. The child must
 * accept `id`, `aria-describedby`, and `aria-invalid` (native inputs and
 * every shared input do).
 *
 * Error is `--danger`, never `--down` (tokens.css house rule: money colors
 * are P&L-only). All dress lives in styles/controls-core.css (`.ctl-field*`,
 * import once app-wide); this file carries no Tailwind utilities, so no
 * `@source` line is needed for it.
 */
import { cloneElement, isValidElement, useId } from "react";
import type { ReactElement, ReactNode } from "react";

import { cx } from "./cx";
import { Label } from "./Label";

type ControlProps = {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean | string;
};

export function Field({
  label,
  hint,
  error,
  htmlFor,
  required = false,
  className,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const autoId = useId();
  const controlId = htmlFor ?? `${autoId}-control`;
  const hintId = `${autoId}-hint`;
  const errorId = `${autoId}-error`;
  const describedBy = [error ? errorId : null, hint && !error ? hintId : null]
    .filter(Boolean)
    .join(" ");

  const control = isValidElement<ControlProps>(children)
    ? cloneElement(children as ReactElement<ControlProps>, {
        id: (children as ReactElement<ControlProps>).props.id ?? controlId,
        ...(describedBy ? { "aria-describedby": describedBy } : null),
        ...(error ? { "aria-invalid": true } : null),
      })
    : children;

  return (
    <div data-slot="field" data-invalid={error ? true : undefined} className={cx("ctl-field", className)}>
      <Label htmlFor={controlId}>
        {label}
        {required ? (
          <span aria-hidden="true" className="ctl-field-required">
            {" *"}
          </span>
        ) : null}
      </Label>
      {control}
      {error ? (
        <p id={errorId} className="ctl-field-error">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="ctl-field-hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
