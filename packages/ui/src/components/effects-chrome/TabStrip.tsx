"use client";

import { useCallback, useLayoutEffect, useRef, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { Button } from "../../ui";

/**
 * TabStrip — the sliding-indicator tab strip promoted from the design
 * reference (chrome/tabs). A proper tablist: role="tablist"/"tab",
 * aria-selected, roving tabindex, ArrowLeft/Right + Home/End keyboard nav.
 * The active indicator is a single absolutely-positioned element whose
 * transform/width (and, for the box dresses, height) are measured from the
 * active tab and written straight to a ref, so the slide is a CSS transition
 * — no `layoutId` (the apps' LazyMotion runs `domAnimation`, which omits
 * layout animations) and no per-frame React state. Survives resize and
 * re-measures on a `dir` flip (ResizeObserver on the strip and its tabs;
 * MutationObserver on <html>'s `dir`/`class`/`data-theme`/`style`), so the
 * ink is correct the instant the document mirrors — not only after the next
 * tab click. Honours reduced motion (indicator jumps, no slide). The ink
 * anchors on
 * `inset-inline-start` and measures the active tab from that same inline-start
 * edge, so it lands under the active tab in both LTR and RTL; arrow-key nav
 * swaps ArrowLeft/ArrowRight under RTL to match the visual order.
 *
 * Three dresses: `underline` for content regions, `pill` for a compact
 * filled-rect mode switch (API name kept; shape is radius 0), `chip` for a
 * wrapping row of bordered chips (dashboard sub-nav — mono face,
 * accent-tinted active chip). `pill` and `chip` position the ink with
 * translate(x, y) + measured height, so `chip` rows may flex-wrap. The strip is controlled (`active` + `onChange`);
 * panels are consumer-owned — wire them with the exported `tabId`/
 * `tabPanelId` helpers:
 *
 *   <TabStrip tabs={TABS} active={i} onChange={setI} label="Account view" />
 *   <div role="tabpanel" id={tabPanelId("Account view", tab.id)}
 *        aria-labelledby={tabId("Account view", tab.id)}>…</div>
 *
 * That per-tab-id default is only correct when the consumer genuinely mounts
 * ONE role="tabpanel" per tab. Content-swapping consumers — one physical
 * panel whose content changes with `active`, which is the common case —
 * must pass `sharedPanel` instead: every tab's aria-controls then points at
 * the CURRENTLY ACTIVE tab's panel id (matching the one real panel, which
 * the consumer keys the same way: id={tabPanelId(label, tabs[active].id)}),
 * rather than each tab dangling a reference to an id that only exists while
 * IT is the active one. Found live in two shipped consumers (#2272) and,
 * closer to home, in this file's own reference showcase before this fix —
 * the tell is a single tabpanel below the strip whose `key` changes with
 * `active` rather than one tabpanel per tab.
 *
 * When the consumer's panels carry no DOM ids at all (e.g. a wrapper
 * adapting legacy children, or no panel semantics apply), pass
 * `linkPanels={false}` to omit `aria-controls` entirely — the attribute is
 * optional in the APG tabs pattern, and a dangling reference is worse than
 * none.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/effects-chrome.css";
 *                 @source "<path-to>/packages/ui/src/components/effects-chrome";
 */
export type TabItem = { id: string; label: ReactNode };

export type TabStripProps = {
  tabs: TabItem[];
  /** Index of the active tab. */
  active: number;
  onChange: (index: number) => void;
  /** Accessible tablist name; also seeds the tab/panel id pairing. */
  label: string;
  variant?: "underline" | "pill" | "chip";
  /** Emit aria-controls → tabPanelId(label, id) (default). False = omit. */
  linkPanels?: boolean;
  /**
   * True when the consumer mounts ONE physical role="tabpanel" whose content
   * swaps with `active`, rather than one tabpanel per tab (see the module
   * doc comment above). Every tab's aria-controls then points at the
   * currently active tab's panel id instead of its own — the one id that
   * actually exists in the DOM — so inactive tabs never dangle a reference.
   * No-op when `linkPanels` is false.
   */
  sharedPanel?: boolean;
  className?: string;
};

/** Id base derived from the tablist label (spaces collapsed to dashes). */
export function tabBaseId(label: string): string {
  return label.replace(/\s+/g, "-");
}

/** DOM id of the tab button for `tabId(label, tab.id)` — pair with aria-labelledby. */
export function tabId(label: string, id: string): string {
  return `${tabBaseId(label)}-tab-${id}`;
}

/** DOM id the consumer's role="tabpanel" must carry (aria-controls points here). */
export function tabPanelId(label: string, id: string): string {
  return `${tabBaseId(label)}-panel-${id}`;
}

export function TabStrip({
  tabs,
  active,
  onChange,
  label,
  variant = "underline",
  linkPanels = true,
  sharedPanel = false,
  className,
}: TabStripProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const inkRef = useRef<HTMLSpanElement>(null);
  const mounted = useRef(false);
  const reduced = useReducedMotion();

  const position = useCallback(
    (animate: boolean) => {
      const list = listRef.current;
      const ink = inkRef.current;
      if (!list || !ink) return;
      const el = list.querySelectorAll<HTMLButtonElement>('[role="tab"]')[active];
      if (!el) return;
      const listRect = list.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      // The ink is anchored with inset-inline-start: 0, so its origin mirrors
      // with the strip. Measure the active tab from that same inline-start
      // edge (physical left in LTR, physical right in RTL) and translate by
      // the physical delta — `transform` has no logical form, so RTL negates.
      const rtl = getComputedStyle(list).direction === "rtl";
      const x = rtl ? listRect.right - elRect.right : elRect.left - listRect.left;
      const y = elRect.top - listRect.top;
      ink.style.transition = animate ? "" : "none";
      // translate(x, y): measured against the strip's padding box — the same
      // origin as the ink's absolute inset-inline-start/top — so the box
      // dresses (pill/chip) track the tab even across wrapped rows.
      ink.style.transform = `translate(${rtl ? -x : x}px, ${y}px)`;
      ink.style.width = `${elRect.width}px`;
      // The underline ink keeps its CSS height (2px, strip-bottom anchored);
      // the box dresses take the tab's own height.
      if (variant !== "underline") ink.style.height = `${elRect.height}px`;
      if (!animate) {
        // flush the jump before restoring the transition so it never animates
        void ink.offsetWidth;
        ink.style.transition = "";
      }
    },
    [active, variant],
  );

  useLayoutEffect(() => {
    position(mounted.current && !reduced);
    mounted.current = true;
  }, [position, reduced]);

  // Re-measure whenever the geometry the ink is derived from can change: the
  // strip's own box (font/zoom/layout), any tab's box (label reflow, wrap),
  // and the document's writing direction. A `dir` flip is the case the
  // reference audit caught (/rtl): the ink kept its LTR offset ~372px from the
  // active tab until the next click, because nothing re-ran `position()` — a
  // window `resize` never fires for it. ResizeObserver covers the box changes;
  // MutationObserver on <html>'s `dir` (plus `class`/`data-theme`/`style`,
  // which can restyle the strip through a theme/livery swap) covers the
  // direction flip and any out-of-React dir change, not just the one the kit's
  // own DirectionProvider makes.
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const remeasure = () => position(false);
    const ro = new ResizeObserver(remeasure);
    ro.observe(list);
    for (const tab of list.querySelectorAll<HTMLElement>('[role="tab"]')) ro.observe(tab);
    const mo = new MutationObserver(remeasure);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["dir", "class", "data-theme", "style"],
    });
    window.addEventListener("resize", remeasure);
    return () => {
      ro.disconnect();
      mo.disconnect();
      window.removeEventListener("resize", remeasure);
    };
  }, [position]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    // In an RTL strip the tabs run right-to-left, so "next" is visually to the
    // left: ArrowLeft/ArrowRight swap their DOM-order meaning.
    const rtl = listRef.current
      ? getComputedStyle(listRef.current).direction === "rtl"
      : false;
    const nextInDom = (active + 1) % tabs.length;
    const prevInDom = (active - 1 + tabs.length) % tabs.length;
    let next = active;
    if (e.key === "ArrowRight") next = rtl ? prevInDom : nextInDom;
    else if (e.key === "ArrowLeft") next = rtl ? nextInDom : prevInDom;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    onChange(next);
    listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  };

  return (
    <div
      ref={listRef}
      className={`tab-strip ${variant}${className ? ` ${className}` : ""}`}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
    >
      <span ref={inkRef} className={`tab-ink ${variant}`} aria-hidden="true" />
      {tabs.map((t, i) => (
        <Button
          key={t.id}
          type="button"
          role="tab"
          variant="ghost"
          id={tabId(label, t.id)}
          aria-selected={i === active}
          aria-controls={
            linkPanels
              ? tabPanelId(label, sharedPanel ? tabs[active].id : t.id)
              : undefined
          }
          tabIndex={i === active ? 0 : -1}
          className="tab-btn h-auto inline-block border-0 bg-transparent text-[0.76rem] font-normal hover:bg-transparent"
          onClick={() => onChange(i)}
        >
          {t.label}
        </Button>
      ))}
    </div>
  );
}
