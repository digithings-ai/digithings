"use client";

import { useCallback, useLayoutEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

/**
 * TabStrip — the sliding-indicator tab strip promoted from the design
 * reference (chrome/tabs). A proper tablist: role="tablist"/"tab",
 * aria-selected, roving tabindex, ArrowLeft/Right + Home/End keyboard nav.
 * The active indicator is a single absolutely-positioned element whose
 * transform/width are measured from the active tab and written straight to a
 * ref, so the slide is a CSS transition — no `layoutId` (the apps' LazyMotion
 * runs `domAnimation`, which omits layout animations) and no per-frame React
 * state. Survives resize; honours reduced motion (indicator jumps, no slide).
 *
 * Two dresses: `underline` for content regions, `pill` for a compact mode
 * switch. The strip is controlled (`active` + `onChange`); panels are
 * consumer-owned — wire them with the exported `tabId`/`tabPanelId` helpers:
 *
 *   <TabStrip tabs={TABS} active={i} onChange={setI} label="Account view" />
 *   <div role="tabpanel" id={tabPanelId("Account view", tab.id)}
 *        aria-labelledby={tabId("Account view", tab.id)}>…</div>
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type TabItem = { id: string; label: string };

export type TabStripProps = {
  tabs: TabItem[];
  /** Index of the active tab. */
  active: number;
  onChange: (index: number) => void;
  /** Accessible tablist name; also seeds the tab/panel id pairing. */
  label: string;
  variant?: "underline" | "pill";
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
      ink.style.transition = animate ? "" : "none";
      ink.style.transform = `translateX(${el.offsetLeft}px)`;
      ink.style.width = `${el.offsetWidth}px`;
      if (!animate) {
        // flush the jump before restoring the transition so it never animates
        void ink.offsetWidth;
        ink.style.transition = "";
      }
    },
    [active],
  );

  useLayoutEffect(() => {
    position(mounted.current && !reduced);
    mounted.current = true;
  }, [position, reduced]);

  useLayoutEffect(() => {
    const onResize = () => position(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [position]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    let next = active;
    if (e.key === "ArrowRight") next = (active + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (active - 1 + tabs.length) % tabs.length;
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
        <button
          key={t.id}
          type="button"
          role="tab"
          id={tabId(label, t.id)}
          aria-selected={i === active}
          aria-controls={tabPanelId(label, t.id)}
          tabIndex={i === active ? 0 : -1}
          className="tab-btn"
          onClick={() => onChange(i)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
