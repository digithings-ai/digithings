"use client"

// Thin re-export of the shared @digithings/web Label (#1419), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (incl. the .group data-disabled / .peer:disabled
// dimming combinators).

import { Label as ControlLabel } from "@digithings/web"
import type { LabelProps as ControlLabelProps } from "@digithings/web"

function Label(props: Omit<ControlLabelProps, "dress">) {
  return <ControlLabel dress="chat" {...props} />
}

export { Label }
