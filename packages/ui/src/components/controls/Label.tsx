/**
 * Label — the shared field label promoted for #1419. A plain <label>
 * (server-safe, className passthrough), props mirroring digichat's
 * ui/label.tsx (React.ComponentProps<"label">) plus the dress switch:
 *
 * - dress="reference" (default): the form-fields mono micro-caps grammar —
 *   0.6rem uppercase, 0.1em tracking, ink-mute.
 * - dress="chat": digichat's current dress translated exactly (flex row,
 *   text-sm medium, leading-none, select-none, with the .group
 *   data-disabled and .peer:disabled dimming combinators) so digichat's
 *   wrapper can pin dress="chat" and re-export with no rendered-look
 *   change.
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
import type { ComponentProps } from "react";

export type LabelDress = "reference" | "chat";

export type LabelProps = ComponentProps<"label"> & {
  dress?: LabelDress;
};

export function Label({ dress = "reference", className, ...props }: LabelProps) {
  const base = dress === "chat" ? "ctl-label-chat" : "ctl-label-ref";
  return (
    <label
      data-slot="label"
      className={className ? `${base} ${className}` : base}
      {...props}
    />
  );
}
