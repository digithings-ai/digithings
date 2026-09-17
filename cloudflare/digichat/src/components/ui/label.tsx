"use client"

// Thin adapter over the canonical kit Label (@digithings/web/ui), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (incl. the .group data-disabled / .peer:disabled
// dimming combinators). The chat tone lives in
// @digithings/web/styles/controls-core.css (.ctl-label-chat).

import { Label as KitLabel } from "@digithings/web/ui"
import type { ComponentProps } from "react"

type LabelProps = Omit<ComponentProps<typeof KitLabel>, "dress">

function Label(props: LabelProps) {
  return <KitLabel dress="chat" {...props} />
}

export { Label }
