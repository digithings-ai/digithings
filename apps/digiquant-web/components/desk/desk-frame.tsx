"use client";

import { useEffect, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { Button } from "@digithings/ui/ui";
import { QuantWordmark } from "@/app/_chrome/QuantWordmark";
import { DeskAccess } from "./desk-access";
import { DeskCommand } from "./desk-command";
import { DeskRail } from "./desk-nav";
import { DeskPicker } from "./desk-picker";
import { deskHref } from "./paths";
import { RAIL_WIDTH_DEFAULT, RAIL_WIDTHS, stepRailWidth } from "./rail-width";

const NARROW = "(max-width: 759px)";
const STORAGE = "dq.desk.rail";

function useNarrowDesk() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia(NARROW);
    const apply = () => setNarrow(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);
  return narrow;
}

/* The server snapshot is the default width, so the hydrated rail matches.
   The client snapshot reads the saved width after mount. */
const railListeners = new Set<() => void>();

function subscribeRailWidth(onStoreChange: () => void): () => void {
  railListeners.add(onStoreChange);
  return () => {
    railListeners.delete(onStoreChange);
  };
}

function readRailWidth(): number {
  const saved = Number(window.localStorage.getItem(STORAGE));
  const widths: readonly number[] = RAIL_WIDTHS;
  return widths.includes(saved) ? saved : RAIL_WIDTH_DEFAULT;
}

function railWidthServerSnapshot(): number {
  return RAIL_WIDTH_DEFAULT;
}

function writeRailWidth(next: number): void {
  window.localStorage.setItem(STORAGE, String(next));
  for (const listener of railListeners) listener();
}

/** Shared desk chrome. One page rail: resizable on a wide layout, a drawer on a phone. */
export function DeskFrame({ current, children }: { current: string; children: ReactNode }) {
  const narrow = useNarrowDesk();
  const width = useSyncExternalStore(subscribeRailWidth, readRailWidth, railWidthServerSnapshot);
  const [open, setOpen] = useState(false);
  const [prevNarrow, setPrevNarrow] = useState(narrow);
  if (narrow !== prevNarrow) {
    setPrevNarrow(narrow);
    if (!narrow) setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const drawer = narrow && open;
  const style = { "--rail-w": `${width}px` } as CSSProperties;

  return (
    <DeskAccess>
      <div className="desk-shell flex h-full min-h-0 flex-col bg-black font-mono text-ink" data-drawer={drawer ? "open" : "closed"} style={style}>
        <header className="relative z-50 flex h-8 min-w-0 shrink-0 items-center gap-2 border-b border-hair px-2 text-[0.7rem] sm:gap-3 sm:px-3">
          <Link href="/" className="desk-mark inline-flex shrink-0 items-center text-ink">
            <QuantWordmark className="block h-[14px] w-auto fill-current text-ink" />
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="desk-pages"
            aria-expanded={drawer}
            aria-controls="desk-rail"
            onClick={() => setOpen((value) => !value)}
          >
            pages
          </Button>
          <DeskPicker />
          <DeskCommand pathname={deskHref(current)} />
        </header>
        <div className="desk-body relative flex min-h-0 min-w-0 flex-1">
          {drawer ? (
            <Button type="button" variant="ghost" className="desk-scrim" aria-label="Close pages" onClick={() => setOpen(false)} />
          ) : null}
          <DeskRail
            current={current}
            onNavigate={() => setOpen(false)}
            collapsed={narrow && !open}
            onNarrower={() => writeRailWidth(stepRailWidth(width, -1))}
            onWider={() => writeRailWidth(stepRailWidth(width, 1))}
            narrowDisabled={width === RAIL_WIDTHS[0]}
            wideDisabled={width === RAIL_WIDTHS[RAIL_WIDTHS.length - 1]}
          />
          <div className="desk-main flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
        </div>
      </div>
    </DeskAccess>
  );
}
