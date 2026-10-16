"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChatDesk } from "./chat-desk";
import { DeskFrame } from "./desk-frame";
import { deskHref, deskPathFromPathname, readDeskGo } from "./paths";
import { publicCatalogPages } from "./public-surface";

const PAGES = new Set(publicCatalogPages().map((page) => page.path));

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
        <div key={path} className="desk-page-settle flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {children}
        </div>
      </DeskFrame>
    </ChatDesk>
  );
}
