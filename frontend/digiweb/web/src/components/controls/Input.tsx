/**
 * Input — the shared text input promoted for #1419. Behavior comes from
 * @base-ui/react's Input primitive (the same primitive digichat's
 * ui/input.tsx wraps — Field integration, onValueChange, ref forwarding).
 * Props mirror digichat's wrapper: React.ComponentProps<"input"> plus the
 * dress switch. Two dresses:
 *
 * - dress="reference" (default): the form-fields .ff-input grammar — mono
 *   0.82rem on a surface fill, 8px radius, accent focus ring; the error
 *   dress keys off the input's own aria-invalid (the specimen's
 *   .ff-field.is-error wrapper combinator, re-hung on the control) and
 *   disabled dims to the specimen's 0.55 wash.
 * - dress="chat": digichat's current dress translated exactly (h-8,
 *   10px radius, transparent fill, text-base → md:text-sm, ring focus,
 *   input-washed disabled, destructive aria-invalid, dark input/30 fill)
 *   so digichat's wrapper can pin dress="chat" and re-export with no
 *   rendered-look change.
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
import { Input as InputPrimitive } from "@base-ui/react/input";
import type { ComponentProps } from "react";

export type InputDress = "reference" | "chat";

export type InputProps = ComponentProps<"input"> & {
  dress?: InputDress;
};

export function Input({ dress = "reference", className, type, ...props }: InputProps) {
  const base = dress === "chat" ? "ctl-input-chat" : "ctl-input-ref";
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={className ? `${base} ${className}` : base}
      {...props}
    />
  );
}
