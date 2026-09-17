// Thin adapter over the canonical kit Input (@digithings/web/ui), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (same @base-ui/react Input primitive underneath). The
// chat tone lives in @digithings/web/styles/controls-core.css (.ctl-input-chat).

import { Input as KitInput } from "@digithings/web/ui"
import type { ComponentProps } from "react"

type InputProps = Omit<ComponentProps<typeof KitInput>, "dress">

function Input(props: InputProps) {
  return <KitInput dress="chat" {...props} />
}

export { Input }
