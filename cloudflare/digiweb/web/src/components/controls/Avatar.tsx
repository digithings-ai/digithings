/**
 * Avatar — the shared avatar family promoted for #1419. Behavior comes
 * from @base-ui/react's Avatar primitives (the same Root / Image /
 * Fallback digichat's ui/avatar.tsx wraps — image load-state drives the
 * fallback swap). The full digichat shape carries over: Avatar (size
 * "default" | "sm" | "lg"), AvatarImage, AvatarFallback, AvatarBadge,
 * AvatarGroup, AvatarGroupCount.
 *
 * Single dress: digichat's current look, translated exactly (circular,
 * blend-mode hairline ring via ::after, muted fallback, primary badge with
 * background ring, -0.5rem group overlap). The reference family has no
 * avatar specimen, so there is no reference dress yet — that awaits a
 * product ruling (see the controls-core.css header).
 *
 * All dress lives in styles/controls-core.css (import once app-wide).
 */
import { Avatar as AvatarPrimitive } from "@base-ui/react/avatar";
import type { ComponentProps } from "react";

export type AvatarSize = "default" | "sm" | "lg";

export type AvatarProps = Omit<AvatarPrimitive.Root.Props, "className"> & {
  className?: string;
  size?: AvatarSize;
};

function cx(base: string, className?: string) {
  return className ? `${base} ${className}` : base;
}

export function Avatar({ className, size = "default", ...props }: AvatarProps) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      data-size={size}
      className={cx("ctl-avatar", className)}
      {...props}
    />
  );
}

export type AvatarImageProps = Omit<AvatarPrimitive.Image.Props, "className"> & {
  className?: string;
};

export function AvatarImage({ className, ...props }: AvatarImageProps) {
  return (
    <AvatarPrimitive.Image
      data-slot="avatar-image"
      className={cx("ctl-avatar-image", className)}
      {...props}
    />
  );
}

export type AvatarFallbackProps = Omit<AvatarPrimitive.Fallback.Props, "className"> & {
  className?: string;
};

export function AvatarFallback({ className, ...props }: AvatarFallbackProps) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cx("ctl-avatar-fallback", className)}
      {...props}
    />
  );
}

export function AvatarBadge({ className, ...props }: ComponentProps<"span">) {
  return (
    <span data-slot="avatar-badge" className={cx("ctl-avatar-badge", className)} {...props} />
  );
}

export function AvatarGroup({ className, ...props }: ComponentProps<"div">) {
  return (
    <div data-slot="avatar-group" className={cx("ctl-avatar-group", className)} {...props} />
  );
}

export function AvatarGroupCount({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="avatar-group-count"
      className={cx("ctl-avatar-group-count", className)}
      {...props}
    />
  );
}
