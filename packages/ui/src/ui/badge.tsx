import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-none border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline:
          "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost:
          "hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "text-primary underline-offset-4 hover:underline",
        // Reference-dress tones (controls-layer Badge parity): hairline chip,
        // token text/border only — no fill, no hardcoded colour.
        neutral: "border-hair text-ink-mute",
        accent: "border-accent-weak text-accent",
        warn: "border-warn/40 text-warn",
        up: "border-up/40 text-up",
        down: "border-down/40 text-down",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export type BadgeDress = "default" | "chat";

function Badge({
  className,
  variant = "default",
  dress = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { dress?: BadgeDress }) {
  // dress="chat" emits the digichat chat-dress classes (styles/controls-core.css)
  // instead of the kit utilities; the variant enum is identical.
  const classes =
    dress === "chat"
      ? cn(`ctl-badge-chat ctl-badge-chat--${variant}`, className)
      : cn(badgeVariants({ variant }), className);

  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      { className: classes },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
