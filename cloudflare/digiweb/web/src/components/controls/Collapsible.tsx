"use client";
/**
 * Collapsible — the shared disclosure control (#1419). A pure passthrough of
 * @base-ui/react's Collapsible (trigger aria-expanded/aria-controls wiring,
 * hidden-state management), matching digichat's
 * src/components/ui/collapsible.tsx 1:1 so a thin re-export can replace that
 * file. Deliberately unstyled, exactly like digichat's wrapper: every
 * digichat call site dresses the trigger/panel itself, and the reference
 * accordion grammar (acc-*) stays a page-level concern until a product
 * ruling converges them. No CSS in controls-overlay.css is needed.
 */
import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible";

export function Collapsible({ ...props }: CollapsiblePrimitive.Root.Props) {
  return <CollapsiblePrimitive.Root data-slot="collapsible" {...props} />;
}

export function CollapsibleTrigger({ ...props }: CollapsiblePrimitive.Trigger.Props) {
  return <CollapsiblePrimitive.Trigger data-slot="collapsible-trigger" {...props} />;
}

export function CollapsibleContent({ ...props }: CollapsiblePrimitive.Panel.Props) {
  return <CollapsiblePrimitive.Panel data-slot="collapsible-content" {...props} />;
}
