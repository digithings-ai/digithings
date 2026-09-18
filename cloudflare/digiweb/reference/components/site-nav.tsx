"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ThemeToggle } from "@digithings/web";
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
} from "@digithings/web/ui";
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

const PAGES = [
  { href: "/", label: "Foundations" },
  { href: "/iterate", label: "Iterate" },
  { href: "/controls", label: "Controls" },
  { href: "/ui", label: "UI kit" },
  { href: "/layout-patterns", label: "Layout" },
  { href: "/typography", label: "Typography" },
  { href: "/data", label: "Data" },
  { href: "/finance", label: "Finance" },
  { href: "/tearsheet", label: "Tearsheet" },
  { href: "/effects", label: "Effects" },
  { href: "/chrome", label: "Chrome" },
  { href: "/terminal", label: "Terminal" },
  { href: "/chatbot", label: "Chatbot" },
  { href: "/symbols", label: "Symbols" },
  { href: "/brand", label: "Brand" },
  { href: "/account", label: "Account" },
] as const;

/** Shared top bar for the design-reference app. Each page holds one family
 *  of design elements; the bar is the only chrome shared across them.
 *  Below the fit threshold the links — and the livery/type-suite pickers —
 *  collapse behind a hamburger that opens the kit Sheet (`@digithings/web/ui`,
 *  Base UI dialog: focus trap, document scroll lock, Escape/backdrop close,
 *  focus returned to the trigger). The always-visible row never has more than
 *  the brand mark, theme toggle, and hamburger to fit, so the hamburger itself
 *  is never a collapse/clip candidate.
 *
 *  Wave 1 (T6): the hand-built `.site-nav-sheet*`/`.site-nav-scrim*` overlays
 *  and the four native `<select>` pickers are gone. Wave 4: the pickers moved
 *  onto the stock kit `Select` (`@digithings/web/ui`) now that it carries the
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

  // Collapse to the hamburger whenever the inline links (plus the livery/type
  // pickers — both collapse together, see .site-nav.is-collapsed in
  // globals.css) stop fitting — at any width, not a hardcoded breakpoint (the
  // item count grows as pages are added). We compare the bar's content width
  // (scrollWidth, which exceeds clientWidth once the nowrap row overflows)
  // against the space available, and freeze the "required" width while
  // collapsed so re-expanding uses the real requirement (+8px hysteresis)
  // instead of the shrunken collapsed row.
  const navRef = useRef<HTMLElement | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const collapsedRef = useRef(false);
  const requiredRef = useRef(0);

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const ro = new ResizeObserver(() => {
      if (!collapsedRef.current) requiredRef.current = nav.scrollWidth;
      const threshold = collapsedRef.current ? requiredRef.current + 8 : requiredRef.current;
      const next = nav.clientWidth < threshold;
      if (next !== collapsedRef.current) {
        collapsedRef.current = next;
        setCollapsed(next);
      }
    });
    ro.observe(nav);
    return () => ro.disconnect();
  }, []);

  // Close the sheet the moment the row stops being collapsed (e.g. a device
  // rotation or window resize widens the bar past the fit threshold while
  // the sheet is open) — same adjust-state-during-render pattern as the
  // pathname handling above. Without this, the sheet's own livery/type-suite
  // pickers stay mounted and one live setting would have two controls.
  const [lastCollapsed, setLastCollapsed] = useState(collapsed);
  if (lastCollapsed !== collapsed) {
    setLastCollapsed(collapsed);
    if (!collapsed && open) setOpen(false);
  }

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
    <nav
      ref={navRef}
      className={`site-nav${collapsed ? " is-collapsed" : ""}`}
      aria-label="Design reference sections"
    >
      <Link href="/" className="site-nav-mark">
        design<em>ref</em>
      </Link>

      <ul className="site-nav-links">
        {PAGES.map((page) => (
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
          {/* pt-12 clears the stock close button (absolute top-3 right-3);
              the links stay right-aligned like the rest of the bar's chrome. */}
          <nav aria-label="Design reference sections" className="flex flex-col px-5 pb-6 pt-12">
            <ul className="m-0 list-none p-0">
              {PAGES.map((page) => (
                <li key={page.href}>
                  <Link
                    href={page.href}
                    aria-current={isActive(page.href) ? "page" : undefined}
                    onClick={() => setOpen(false)}
                    className="block w-full border-b border-hair py-[0.85rem] text-right font-display text-[1.35rem] text-ink-soft no-underline transition-colors hover:text-ink aria-[current=page]:border-accent/55 aria-[current=page]:text-ink"
                  >
                    {page.label}
                  </Link>
                </li>
              ))}
            </ul>

            {/* Livery + type suite pickers collapse in here alongside the
                links (see .site-nav.is-collapsed in globals.css) — they
                are hidden from the always-visible row below the same
                breakpoint, so the row only ever needs to fit the brand
                mark, theme toggle, and the hamburger. */}
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
