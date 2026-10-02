import type { ReactNode } from "react";
import Link from "next/link";
import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import { deskHref } from "./paths";
import { WEB_SLOTS } from "./web-slots";

/** Shared desk chrome. Internal routes use `Link` so the app router owns them. */
export function DeskFrame({ current, children }: { current: string; children: ReactNode }) {
  const page = PAGES.find((item) => item.path === current);
  const slot = WEB_SLOTS.find((item) => item.path === current);
  const crumb = page ? `${page.label} ${page.path}` : slot ? `${slot.label} ${slot.path}` : current;
  return (
    <div className="flex h-full min-h-0 flex-col bg-black font-mono text-ink">
      <header className="flex h-8 shrink-0 items-center gap-3 border-b border-hair px-3 text-[0.7rem]">
        <Link href="/" className="text-ink no-underline">
          digiquant
        </Link>
        <span className="text-ink-mute">{crumb}</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Pages" className="w-44 shrink-0 overflow-auto border-r border-hair py-2 text-[0.75rem]">
          {PAGES.map((item) => {
            const active = item.path === current;
            const child = item.path.split("/").filter(Boolean).length > 1;
            return (
              <Link
                key={item.path}
                href={deskHref(item.path)}
                aria-current={active ? "page" : undefined}
                className={`block py-0.5 no-underline ${child ? "pl-6" : "pl-3"} ${active ? "text-ink" : "text-ink-mute"}`}
              >
                {item.label}
              </Link>
            );
          })}
          <p className="m-0 px-3 pt-3 pb-0.5 text-[0.65rem] text-ink-mute">browser</p>
          {WEB_SLOTS.map((item) => {
            const active = item.path === current;
            return (
              <Link
                key={item.path}
                href={deskHref(item.path)}
                aria-current={active ? "page" : undefined}
                className={`block py-0.5 pl-3 no-underline ${active ? "text-ink" : "text-ink-mute"}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
