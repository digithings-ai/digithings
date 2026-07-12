/**
 * Card — the shared surface-card family promoted for #1419, in digichat's
 * ui/card.tsx shape: Card + CardHeader / CardTitle / CardDescription /
 * CardAction / CardContent / CardFooter (all plain divs, server-safe,
 * className passthrough). The root takes the dress; the parts inherit it
 * via descendant CSS, exactly like digichat's group/card scoping:
 *
 * - dress="reference" (default): the hairline frame grammar — 1px hair
 *   border, 12px radius, surface fill, hairline-ruled head and foot rows
 *   (the ChatWidgetFrame card paddings), mono title.
 * - dress="chat": digichat's current dress translated exactly (ring-1
 *   foreground/10 shadow, 14px radius, block padding + gap, muted-washed
 *   footer, `size` "default" | "sm") so digichat's wrapper can pin
 *   dress="chat" and re-export with no rendered-look change.
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
import type { ComponentProps } from "react";

export type CardDress = "reference" | "chat";
export type CardSize = "default" | "sm";

export type CardProps = ComponentProps<"div"> & {
  dress?: CardDress;
  /** digichat's density switch — only the chat dress reads it. */
  size?: CardSize;
};

function cx(base: string, className?: string) {
  return className ? `${base} ${className}` : base;
}

export function Card({ dress = "reference", size = "default", className, ...props }: CardProps) {
  const base = dress === "chat" ? "ctl-card-chat" : "ctl-card-ref";
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cx(base, className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-header" className={cx("ctl-card-header", className)} {...props} />;
}

export function CardTitle({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-title" className={cx("ctl-card-title", className)} {...props} />;
}

export function CardDescription({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cx("ctl-card-description", className)}
      {...props}
    />
  );
}

export function CardAction({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-action" className={cx("ctl-card-action", className)} {...props} />;
}

export function CardContent({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-content" className={cx("ctl-card-content", className)} {...props} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="card-footer" className={cx("ctl-card-footer", className)} {...props} />;
}
