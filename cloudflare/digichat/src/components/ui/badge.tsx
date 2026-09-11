// Thin re-export of the shared @digithings/web Badge (#1419), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (variant enum verbatim, useRender `render` prop and
// { slot, variant } state preserved). The old local cva `badgeVariants`
// export is gone — no call site imported it (see CONTROLS.md).

import { Badge as ControlBadge } from "@digithings/web"
import type { BadgeProps as ControlBadgeProps } from "@digithings/web"

type BadgeProps = Omit<Extract<ControlBadgeProps, { dress: "chat" }>, "dress">

function Badge(props: BadgeProps) {
  return <ControlBadge dress="chat" {...props} />
}

export { Badge }
