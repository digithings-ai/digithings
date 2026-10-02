import type { ReactNode } from "react";
import Link from "next/link";
import { QuantWordmark } from "@/app/_chrome/QuantWordmark";
import { DeskAccess } from "./desk-access";
import { DeskCommand } from "./desk-command";
import { DeskRail } from "./desk-nav";
import { DeskPicker } from "./desk-picker";
import { deskHref } from "./paths";

/** Shared desk chrome. Internal routes use `Link` so the app router owns them. */
export function DeskFrame({ current, children }: { current: string; children: ReactNode }) {
  return (
    <DeskAccess>
      <div className="flex h-full min-h-0 flex-col bg-black font-mono text-ink">
        <header className="flex h-8 shrink-0 items-center gap-3 border-b border-hair px-3 text-[0.7rem]">
          <Link href="/" className="inline-flex shrink-0 items-center text-ink">
            <QuantWordmark className="block h-[14px] w-auto fill-current text-ink" />
          </Link>
          <DeskPicker />
          <DeskCommand pathname={deskHref(current)} />
        </header>
        <div className="flex min-h-0 flex-1">
          <DeskRail current={current} />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
        </div>
      </div>
    </DeskAccess>
  );
}
