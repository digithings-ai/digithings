// Thin re-export of the shared @digithings/web Input (#1419), pinned to
// dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (same @base-ui/react Input primitive underneath).

import { Input as ControlInput } from "@digithings/web"
import type { InputProps as ControlInputProps } from "@digithings/web"

function Input(props: Omit<ControlInputProps, "dress">) {
  return <ControlInput dress="chat" {...props} />
}

export { Input }
