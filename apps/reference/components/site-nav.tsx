"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { ThemeToggle } from "@digithings/ui";
import {
  Button,
  Select,
  SelectItem,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@digithings/ui/ui";
import {
  applyLivery,
  getLiverySnapshot,
  getLiveryServerSnapshot,
  LIVERY_OPTIONS,
  subscribeLivery,
} from "@/components/livery-store";
import {
  applyType,
  getTypeServerSnapshot,
  getTypeSnapshot,
  subscribeType,
  TYPE_SUITES,
} from "@/components/type-store";
// Primary families and the reference-only (lab) group are declared once in
// `@/lib/nav`; the top bar and the home-page contents map both read them.
import { LAB_NAV, PRIMARY_NAV } from "@/lib/nav";

/** Shared top bar for the design-reference app. Each page holds one family
 *  of design elements; the bar is the only chrome shared across them.
 *
 *  The row's composition is breakpoint-driven (see `.site-nav` in globals.css:
 *  1080px and 1600px), not JS fit-measured — the old ResizeObserver collapsed
 *  the moment the row stopped fitting, which hid the family map on ordinary
 *  desktop widths (1440/1280) until ~1600px. At ≥1080px the primary family
 *  map rides inline; the reference-only lab group and both choosers stay in
 *  the kit Sheet behind the hamburger. At ≥1600px the lab group and pickers
 *  join the row and the hamburger retires. Below 1080px the hamburger is the
 *  only way in, opening the full menu in the kit Sheet (`@digithings/ui/ui`,
 *  Base UI dialog: focus trap, document scroll lock, Escape/backdrop close,
 *  focus returned to the trigger).
 *
 *  Wave 1 (T6): the hand-built `.site-nav-sheet*`/`.site-nav-scrim*` overlays
 *  and the four native `<select>` pickers are gone. Wave 4: the pickers moved
 *  onto the stock kit `Select` (`@digithings/ui/ui`) now that it carries the
 *  non-portal `SelectPopup` the controls layer used; the sheet and the
 *  hamburger trigger are the stock kit too (`Sheet`, `Button`). */
export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [lastPathname, setLastPathname] = useState(pathname);

  // Close the sheet on route change (covers back/forward navigation) via the
  // adjust-state-during-render pattern — no setState-in-effect cascade.
  if (lastPathname !== pathname) {
    setLastPathname(pathname);
    if (open) setOpen(false);
  }

  const livery = useSyncExternalStore(subscribeLivery, getLiverySnapshot, getLiveryServerSnapshot);
  const typeTheme = useSyncExternalStore(subscribeType, getTypeSnapshot, getTypeServerSnapshot);

  // Boundary-checked, not a bare startsWith: /data would otherwise also read
  // "current" on a hypothetical /data-v2 route (or any other sibling sharing
  // the prefix) — match only the exact path or a path continuing after "/".
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const liveryPicker = (label: string) => (
    <Select
      value={livery}
      onValueChange={(value) => value != null && applyLivery(String(value))}
    >
      <SelectTrigger aria-label={label}>
        <SelectValue>
          {(value) => LIVERY_OPTIONS.find((o) => o.id === value)?.label ?? ""}
        </SelectValue>
      </SelectTrigger>
      <SelectPopup>
        {LIVERY_OPTIONS.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.label}
          </SelectItem>
        ))}
      </SelectPopup>
    </Select>
  );

  const typePicker = (label: string) => (
    <Select
      value={typeTheme}
      onValueChange={(value) => value != null && applyType(String(value))}
    >
      <SelectTrigger aria-label={label}>
        <SelectValue>
          {(value) => TYPE_SUITES.find((o) => o.id === value)?.label ?? ""}
        </SelectValue>
      </SelectTrigger>
      <SelectPopup>
        {TYPE_SUITES.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.label}
          </SelectItem>
        ))}
      </SelectPopup>
    </Select>
  );

  return (
    <nav className="site-nav" aria-label="Design reference sections">
      <Link href="/" className="site-nav-mark">
        design<em>ref</em>
      </Link>

      <ul className="site-nav-links">
        {PRIMARY_NAV.map((page) => (
          <li key={page.href}>
            <Link href={page.href} aria-current={isActive(page.href) ? "page" : undefined}>
              {page.label}
            </Link>
          </li>
        ))}
      </ul>

      {/* Reference-only surfaces stay off the primary row: a de-emphasised
          secondary list after the same divider, never peers of the families. */}
      <ul className="site-nav-links site-nav-links--lab" aria-label="Reference-only surfaces">
        <li aria-hidden="true" className="site-nav-lab-sep">
          lab
        </li>
        {LAB_NAV.map((page) => (
          <li key={page.href}>
            <Link href={page.href} aria-current={isActive(page.href) ? "page" : undefined}>
              {page.label}
            </Link>
          </li>
        ))}
      </ul>

      <div className="site-nav-livery">{liveryPicker("Page livery")}</div>

      <div className="site-nav-suite">{typePicker("Type suite")}</div>

      <ThemeToggle className="site-nav-theme" />

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          render={
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="site-nav-burger size-auto"
              aria-label={open ? "Close navigation" : "Open navigation"}
            />
          }
        >
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </SheetTrigger>

        <SheetContent side="right" aria-label="Navigation" className="overflow-y-auto">
          {/* pt-12 clears the stock close button (absolute top-3 end-3);
              the links stay right-aligned like the rest of the bar's chrome. */}
          <nav aria-label="Design reference sections" className="flex flex-col px-5 pb-6 pt-12">
            <ul className="m-0 list-none p-0">
              {PRIMARY_NAV.map((page) => (
                <li key={page.href}>
                  <Link
                    href={page.href}
                    aria-current={isActive(page.href) ? "page" : undefined}
                    onClick={() => setOpen(false)}
                    className="block w-full border-b border-hair py-[0.85rem] text-end font-display text-[1.35rem] text-ink-soft no-underline transition-colors hover:text-ink aria-[current=page]:border-accent/55 aria-[current=page]:text-ink"
                  >
                    {page.label}
                  </Link>
                </li>
              ))}
            </ul>

            <p className="mb-0 mt-[1.2rem] font-mono text-[0.58rem] uppercase tracking-[0.14em] text-ink-mute">
              reference-only
            </p>
            <ul className="m-0 list-none p-0">
              {LAB_NAV.map((page) => (
                <li key={page.href}>
                  <Link
                    href={page.href}
                    aria-current={isActive(page.href) ? "page" : undefined}
                    onClick={() => setOpen(false)}
                    className="block w-full border-b border-hair py-[0.6rem] text-end font-display text-[1.05rem] text-ink-mute no-underline transition-colors hover:text-ink aria-[current=page]:text-ink"
                  >
                    {page.label}
                  </Link>
                </li>
              ))}
            </ul>

            {/* Livery + type suite pickers live in here alongside the links
                everywhere below 1600px (see `.site-nav-livery`/`-suite` in
                globals.css) — below the 1600px row they would crowd the
                family map, so the hamburger is their only door. */}
            <div className="mt-[1.4rem] flex items-center gap-[0.75rem] border-t border-hair pt-[1.1rem]">
              {liveryPicker("Page livery")}
              {typePicker("Type suite")}
            </div>
          </nav>
        </SheetContent>
      </Sheet>
    </nav>
  );
}
