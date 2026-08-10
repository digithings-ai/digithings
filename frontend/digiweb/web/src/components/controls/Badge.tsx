/**
 * Badge — the shared status pill promoted for #1419. Rendering behavior
 * comes from @base-ui/react's useRender (the same hook digichat's
 * ui/badge.tsx uses, so the `render` composition prop carries over). Two
 * dresses:
 *
 * - dress="reference" (default): the mono micro-caps hairline pill — the
 *   .dg-tier grammar (web-theme.css). Variants are tones: "neutral"
 *   (ink-mute, default), "accent" (t-core), "warn" (t-roadmap), and the
 *   money colors "up" / "down" by the same 40%-mix border formula.
 * - dress="chat": digichat's current shadcn-derived dress, matching
 *   digichat ui/badge.tsx variant enums exactly ("default" | "secondary" |
 *   "destructive" | "outline" | "ghost" | "link") so that wrapper can pin
 *   dress="chat" and re-export with no rendered-look change.
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
"use client";

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";

export type BadgeDress = "reference" | "chat";
export type BadgeReferenceVariant = "neutral" | "accent" | "warn" | "up" | "down";
export type BadgeChatVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "ghost"
  | "link";

type BadgeReferenceOwnProps = {
  dress?: "reference";
  variant?: BadgeReferenceVariant;
};

type BadgeChatOwnProps = {
  dress: "chat";
  variant?: BadgeChatVariant;
};

export type BadgeProps = useRender.ComponentProps<"span"> &
  (BadgeReferenceOwnProps | BadgeChatOwnProps);

const REFERENCE_VARIANTS: Record<BadgeReferenceVariant, string> = {
  neutral: "ctl-badge-ref",
  accent: "ctl-badge-ref ctl-badge-ref--accent",
  warn: "ctl-badge-ref ctl-badge-ref--warn",
  up: "ctl-badge-ref ctl-badge-ref--up",
  down: "ctl-badge-ref ctl-badge-ref--down",
};

const CHAT_VARIANTS: Record<BadgeChatVariant, string> = {
  default: "ctl-badge-chat ctl-badge-chat--default",
  secondary: "ctl-badge-chat ctl-badge-chat--secondary",
  destructive: "ctl-badge-chat ctl-badge-chat--destructive",
  outline: "ctl-badge-chat ctl-badge-chat--outline",
  ghost: "ctl-badge-chat ctl-badge-chat--ghost",
  link: "ctl-badge-chat ctl-badge-chat--link",
};

export function Badge({ dress = "reference", variant, className, render, ...props }: BadgeProps) {
  // The destructured union loses the dress↔variant correlation, so narrow
  // each branch explicitly.
  const classes =
    dress === "chat"
      ? CHAT_VARIANTS[(variant as BadgeChatVariant | undefined) ?? "default"]
      : REFERENCE_VARIANTS[(variant as BadgeReferenceVariant | undefined) ?? "neutral"];

  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      { className: className ? `${classes} ${className}` : classes },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant: variant ?? (dress === "chat" ? "default" : "neutral"),
    },
  });
}
