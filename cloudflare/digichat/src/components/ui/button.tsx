"use client"

// Thin re-export of the shared @digithings/web Button (#1419), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress. Variant/size enums are digichat's verbatim
// (ButtonChatVariant / ButtonChatSize). The old local cva `buttonVariants`
// export is gone — no call site imported it (see CONTROLS.md).

import { Button as ControlButton } from "@digithings/web"
import type { ButtonProps as ControlButtonProps } from "@digithings/web"

type ButtonProps = Omit<Extract<ControlButtonProps, { dress: "chat" }>, "dress">

function Button(props: ButtonProps) {
  return <ControlButton dress="chat" {...props} />
}

export { Button }
