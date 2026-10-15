"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChatDesk } from "./chat-desk";
import { DeskFrame } from "./desk-frame";
import { deskHref, deskPathFromPathname, readDeskGo } from "./paths";
import { publicCatalogPages } from "./public-surface";
import { WEB_SLOTS } from "./web-slots";

const PAGES = new Set(publicCatalogPages().map((page) => page.path));

/** The route name a screen reader hears. One h1 per route, visually hidden. */
export function deskRouteLabel(path: string): string {
  const slot = WEB_SLOTS.find((entry) => entry.path === path);
  if (slot) return slot.label;
  const page = publicCatalogPages().find((entry) => entry.path === path);
  if (page) return page.label;
  return "Brief";
}

/** Desk chrome stays mounted. A page change swaps the body. */
export function DeskShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/app";
  const path = deskPathFromPathname(pathname);
  const router = useRouter();

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const next = readDeskGo(event.data);
      if (!next || !PAGES.has(next)) return;
      if (deskPathFromPathname(window.location.pathname) === next) return;
      router.push(deskHref(next), { scroll: false });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [router]);

  return (
    <ChatDesk active={path === "/tools/chat"}>
      <DeskFrame current={path}>
        <a href="#desk-main" className="desk-skip">
          Skip to desk content
        </a>
        <h1 className="desk-sr">{deskRouteLabel(path)}</h1>
        <div
          key={path}
          id="desk-main"
          tabIndex={-1}
          className="desk-page-settle flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
        >
          {children}
        </div>
      </DeskFrame>
    </ChatDesk>
  );
}
