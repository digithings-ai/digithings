"use client"

// Thin adapter over the canonical kit Button (@digithings/web/ui), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress. The chat tone lives in
// @digithings/web/styles/controls-core.css (.ctl-btn-chat*) and the kit emits
// it when dress="chat". Variant/size enums are digichat's verbatim — the kit's
// enums are identical. The old local cva `buttonVariants` export is gone — no
// call site imported it (see CONTROLS.md).

import { Button as KitButton } from "@digithings/web/ui"
import type { ComponentProps } from "react"

type ButtonProps = Omit<ComponentProps<typeof KitButton>, "dress">

function Button(props: ButtonProps) {
  return <KitButton dress="chat" {...props} />
}

export { Button }
