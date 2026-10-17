"use client";

import { pageByPath } from "../../../../clients/digiquant-tui/src/catalog";
import { DeskBody, DeskCatalogLive, mountedDeskKind } from "@/components/desk/desk-page";
import { isInviteSurface } from "@/components/desk/public-surface";

export type ScreenKind = "brief" | "portfolio" | "pipeline" | "strategies" | "catalog" | "undrawn";

/** Which real desk screen a terminal path draws. Invite-only and web-only slots stay undrawn. */
export function screenKind(path: string): ScreenKind {
  if (isInviteSurface(path)) return "undrawn";
  const mounted = mountedDeskKind(path);
  if (mounted) return mounted;
  if (pageByPath(path)) return "catalog";
  return "undrawn";
}

/** The same page the web desk mounts for this path, inside the terminal frame. */
export function TerminalScreen({ path }: { path: string }) {
  const kind = screenKind(path);
  switch (kind) {
    case "brief":
    case "portfolio":
    case "pipeline":
    case "strategies":
      return <DeskBody path={path} />;
    case "catalog":
      return <DeskCatalogLive path={path} />;
    case "undrawn":
      return (
        <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">
          This page is not drawn on the terminal.
        </p>
      );
    default: {
      const never: never = kind;
      return never;
    }
  }
}
