"use client"

import * as React from "react"
import { cn } from "../lib/utils"

export type LabelDress = "default" | "chat";

function Label({
  className,
  dress = "default",
  ...props
}: React.ComponentProps<"label"> & { dress?: LabelDress }) {
  // dress="chat" emits the digichat chat-dress class (styles/controls-core.css)
  // instead of the kit utilities, keeping digichat's rendered look exact.
  const classes =
    dress === "chat"
      ? cn("ctl-label-chat", className)
      : cn(
          "flex items-center gap-2 text-xs leading-none select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
          className
        );

  return (
    <label
      data-slot="label"
      className={classes}
      {...props}
    />
  )
}

export { Label }
