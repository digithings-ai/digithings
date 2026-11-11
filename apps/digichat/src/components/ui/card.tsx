// Thin adapter over the canonical kit Card family (@digithings-ai/ui/ui). The
// root pins dress="chat" so the rendered look stays exactly digichat's current
// shadcn-derived dress (size "default" | "sm", data-slot/data-size hooks
// preserved); the parts inherit the dress through the kit's Card context. The
// chat tone lives in @digithings-ai/ui/styles/controls-core.css (.ctl-card-chat*).

import {
  Card as KitCard,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@digithings-ai/ui/ui"
import type { ComponentProps } from "react"

type CardProps = Omit<ComponentProps<typeof KitCard>, "dress">

function Card(props: CardProps) {
  return <KitCard dress="chat" {...props} />
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
