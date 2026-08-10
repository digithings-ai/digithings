/**
 * Button — the shared control promoted for #1419. Behavior comes from
 * @base-ui/react's Button primitive (the same primitive digichat's
 * ui/button.tsx wraps, so `render` composition, `nativeButton`,
 * `focusableWhenDisabled` and ref forwarding all carry over). Two dresses:
 *
 * - dress="reference" (default): the design-reference button vocabulary —
 *   variant "primary" | "ghost" | "quiet" | "danger" (globals.css .btn-*)
 *   plus "icon" (the nav-shell borderless glyph button). `loading` renders
 *   the .btn-spinner grammar before the children (callers set `disabled`
 *   themselves, as the specimen does).
 * - dress="chat": digichat's current shadcn-derived dress, matching
 *   digichat ui/button.tsx variant/size enums exactly so that wrapper can
 *   pin dress="chat" and re-export without any rendered-look change
 *   (E3 ruling: API compatibility beats aesthetic purity — the
 *   reference-vs-chat delta awaits a product ruling).
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import type { ReactNode } from "react";

export type ButtonDress = "reference" | "chat";
export type ButtonReferenceVariant = "primary" | "ghost" | "quiet" | "danger" | "icon";
export type ButtonChatVariant =
  | "default"
  | "outline"
  | "secondary"
  | "ghost"
  | "destructive"
  | "link";
export type ButtonChatSize =
  | "default"
  | "xs"
  | "sm"
  | "lg"
  | "icon"
  | "icon-xs"
  | "icon-sm"
  | "icon-lg";

type ButtonReferenceOwnProps = {
  dress?: "reference";
  variant?: ButtonReferenceVariant;
  size?: never;
  /** Reference primary loading state — prepends the spinner glyph. */
  loading?: boolean;
};

type ButtonChatOwnProps = {
  dress: "chat";
  variant?: ButtonChatVariant;
  size?: ButtonChatSize;
  loading?: never;
};

export type ButtonProps = Omit<ButtonPrimitive.Props, "className"> & {
  className?: string;
} & (ButtonReferenceOwnProps | ButtonChatOwnProps);

const REFERENCE_VARIANTS: Record<ButtonReferenceVariant, string> = {
  primary: "ctl-btn-ref ctl-btn-ref--primary",
  ghost: "ctl-btn-ref ctl-btn-ref--ghost",
  quiet: "ctl-btn-ref ctl-btn-ref--quiet",
  danger: "ctl-btn-ref ctl-btn-ref--danger",
  icon: "ctl-btn-ref--icon",
};

const CHAT_VARIANTS: Record<ButtonChatVariant, string> = {
  default: "ctl-btn-chat--default",
  outline: "ctl-btn-chat--outline",
  secondary: "ctl-btn-chat--secondary",
  ghost: "ctl-btn-chat--ghost",
  destructive: "ctl-btn-chat--destructive",
  link: "ctl-btn-chat--link",
};

const CHAT_SIZES: Record<ButtonChatSize, string> = {
  default: "ctl-btn-chat--size-default",
  xs: "ctl-btn-chat--size-xs",
  sm: "ctl-btn-chat--size-sm",
  lg: "ctl-btn-chat--size-lg",
  icon: "ctl-btn-chat--size-icon",
  "icon-xs": "ctl-btn-chat--size-icon-xs",
  "icon-sm": "ctl-btn-chat--size-icon-sm",
  "icon-lg": "ctl-btn-chat--size-icon-lg",
};

export function Button({
  dress = "reference",
  variant,
  size,
  loading,
  className,
  children,
  ...props
}: ButtonProps) {
  // The destructured union loses the dress↔variant correlation, so narrow
  // each branch explicitly.
  const classes =
    dress === "chat"
      ? `ctl-btn-chat ${CHAT_VARIANTS[(variant as ButtonChatVariant | undefined) ?? "default"]} ${
          CHAT_SIZES[(size as ButtonChatSize | undefined) ?? "default"]
        }`
      : `${REFERENCE_VARIANTS[(variant as ButtonReferenceVariant | undefined) ?? "primary"]}${
          loading ? " ctl-btn-ref--loading" : ""
        }`;

  return (
    <ButtonPrimitive
      data-slot="button"
      className={className ? `${classes} ${className}` : classes}
      {...props}
    >
      {loading ? <span className="ctl-btn-spinner" aria-hidden="true" /> : null}
      {children as ReactNode}
    </ButtonPrimitive>
  );
}
