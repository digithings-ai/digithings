"use client"

import * as React from "react"
import { cn } from "../lib/utils"

export type CardDress = "default" | "chat";

// The chat dress scopes its part rules under `.ctl-card-chat .ctl-card-*`
// (styles/controls-core.css), so the parts must know the root's dress. The
// digichat wrapper pins `dress="chat"` on the root and the parts inherit it.
const CardDressContext = React.createContext<CardDress>("default")

function useCardDress() {
  return React.useContext(CardDressContext)
}

function Card({
  className,
  size = "default",
  dress = "default",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm"; dress?: CardDress }) {
  return (
    <CardDressContext.Provider value={dress}>
      <div
        data-slot="card"
        data-size={size}
        className={cn(
          dress === "chat"
            ? "ctl-card-chat"
            : "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-none bg-card py-(--card-spacing) text-xs/relaxed text-card-foreground ring-1 ring-foreground/10 [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-none *:[img:last-child]:rounded-none",
          className
        )}
        {...props}
      />
    </CardDressContext.Provider>
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-header"
      className={cn(
        dress === "chat"
          ? "ctl-card-header"
          : "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-none px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-title"
      className={cn(
        dress === "chat"
          ? "ctl-card-title"
          : "text-sm font-medium group-data-[size=sm]/card:text-sm",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-description"
      className={cn(
        dress === "chat"
          ? "ctl-card-description"
          : "text-xs/relaxed text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-action"
      className={cn(
        dress === "chat"
          ? "ctl-card-action"
          : "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-content"
      className={cn(dress === "chat" ? "ctl-card-content" : "px-(--card-spacing)", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  const dress = useCardDress()
  return (
    <div
      data-slot="card-footer"
      className={cn(
        dress === "chat"
          ? "ctl-card-footer"
          : "flex items-center rounded-none border-t p-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
