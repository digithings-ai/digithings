import * as React from "react"
import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-none border border-input bg-transparent px-2.5 py-2 text-base transition-colors outline-none placeholder:text-ink-mute focus-visible:border-accent focus-visible:ring-3 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:bg-surface-2/50 disabled:opacity-50 aria-invalid:border-danger aria-invalid:ring-3 aria-invalid:ring-danger/20 md:text-sm dark:bg-surface-2/30 dark:disabled:bg-surface-2/80 dark:aria-invalid:border-danger/50 dark:aria-invalid:ring-danger/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
