"use client"

// Thin re-export of the shared @digithings/web Collapsible (#1419) — an
// unstyled 1:1 passthrough of @base-ui/react's Collapsible, exactly like
// the previous local wrapper (call sites keep dressing trigger/panel).

export {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@digithings/web"
