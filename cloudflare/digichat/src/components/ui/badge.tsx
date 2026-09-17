// Thin adapter over the canonical kit Badge (@digithings/web/ui), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (variant enum verbatim, useRender `render` prop and
// { slot, variant } state preserved). The chat tone lives in
// @digithings/web/styles/controls-core.css (.ctl-badge-chat*). The old local
// cva `badgeVariants` export is gone — no call site imported it (see CONTROLS.md).

import { Badge as KitBadge } from "@digithings/web/ui"
import type { ComponentProps } from "react"

type BadgeProps = Omit<ComponentProps<typeof KitBadge>, "dress">

function Badge(props: BadgeProps) {
  return <KitBadge dress="chat" {...props} />
}

export { Badge }
