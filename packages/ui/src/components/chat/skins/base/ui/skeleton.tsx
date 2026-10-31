/**
 * Base skin skeleton: the assistant-ui / shadcn default, drawn only from the theme
 * tokens (background, foreground, popover, muted, primary, border, ring), so a
 * tenant or brand theme restyles it. The stock (digichat) twin keeps its own
 * square look; nothing in the base skin path may import it
 * (base-skin-theme-surfaces.source.test.ts).
 */
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
