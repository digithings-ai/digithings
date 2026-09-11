// Thin re-export of the shared @digithings/web Card family (#1419). The
// root pins dress="chat" so the rendered look stays exactly digichat's
// current shadcn-derived dress (size "default" | "sm", data-slot/data-size
// hooks preserved); the part components carry no dress of their own.

import {
  Card as ControlCard,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@digithings/web"
import type { CardProps as ControlCardProps } from "@digithings/web"

function Card(props: Omit<ControlCardProps, "dress">) {
  return <ControlCard dress="chat" {...props} />
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
