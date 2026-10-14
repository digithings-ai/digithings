"use client";

import { useEffect } from "react";
import {
  hashIdFromHref,
  instantScrollToHash,
  instantScrollToId,
  isSamePageHashHref,
  readScrollAnchor,
  scrollTopForAnchor,
  type ScrollAnchor,
} from "./hashScroll";

const STORE = "dg-scroll:";
/** Late layout (fonts, measured grids) can still move content this long after load. */
const RESTORE_MS = 1500;
const RESIZE_SETTLE_MS = 300;

const storeKey = () => `${STORE}${window.location.pathname}${window.location.search}`;

function readSaved(): ScrollAnchor | null {
  try {
    const raw = window.sessionStorage.getItem(storeKey());
    const saved = raw ? (JSON.parse(raw) as ScrollAnchor) : null;
    return saved && typeof saved.y === "number" && typeof saved.frac === "number" ? saved : null;
  } catch {
    return null;
  }
}

function save(anchor: ScrollAnchor) {
  try {
    window.sessionStorage.setItem(storeKey(), JSON.stringify(anchor));
  } catch {
    /* storage full or blocked: position keeping is best-effort */
  }
}

/**
 * Owns page scroll position:
 * - same-page hash links jump instantly to their target section instead of
 *   smooth-scrolling through tall scroll-driven blocks (pipeline, card stack, etc.);
 * - a reload or back/forward lands where the reader was, not on the URL hash;
 * - a width change (browser zoom, rotation, window resize) keeps the reader on
 *   the same point of the same section. Height-only changes on touch devices
 *   are ignored — that is the mobile URL bar, and it moves under a live thumb.
 */
export function HashScrollManager() {
  useEffect(() => {
    const nav = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    const returning = nav?.type === "reload" || nav?.type === "back_forward";
    const saved = returning ? readSaved() : null;

    let anchor: ScrollAnchor = saved ?? readScrollAnchor();
    let holdUntil = 0;
    let frame = 0;
    let saveTimer = 0;
    const timers: number[] = [];
    let width = window.innerWidth;
    let height = window.innerHeight;
    const coarse = window.matchMedia("(pointer: coarse)").matches;

    const place = () => {
      if (performance.now() > holdUntil) return;
      window.scrollTo({ top: Math.max(0, scrollTopForAnchor(anchor)), behavior: "instant" });
    };
    const hold = (ms: number) => {
      holdUntil = Math.max(holdUntil, performance.now() + ms);
    };
    const release = () => {
      holdUntil = 0;
      if (window.history.scrollRestoration === "manual") window.history.scrollRestoration = "auto";
    };

    if (saved) {
      window.history.scrollRestoration = "manual";
      hold(RESTORE_MS);
      requestAnimationFrame(place);
      for (const ms of [250, 700, RESTORE_MS - 100]) timers.push(window.setTimeout(place, ms));
      timers.push(window.setTimeout(release, RESTORE_MS));
      void document.fonts?.ready.then(place);
    } else if (window.location.hash) {
      requestAnimationFrame(() => instantScrollToHash(window.location.hash));
    }

    const onScroll = () => {
      if (performance.now() < holdUntil) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        anchor = readScrollAnchor();
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(() => save(anchor), 150);
      });
    };

    const onResize = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const moved = w !== width || (h !== height && !coarse);
      width = w;
      height = h;
      if (!moved) return;
      hold(RESIZE_SETTLE_MS + 50);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
      timers.push(window.setTimeout(place, RESIZE_SETTLE_MS));
    };

    /* The reader takes over: stop steering. */
    const onInput = () => {
      if (holdUntil) release();
    };

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const link = (event.target as Element | null)?.closest("a[href]");
      if (!(link instanceof HTMLAnchorElement)) return;

      const href = link.getAttribute("href");
      if (!href || !isSamePageHashHref(href)) return;

      const id = hashIdFromHref(href);
      if (!id) return;

      event.preventDefault();
      const url = new URL(href, window.location.href);
      window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
      instantScrollToId(id);
    };

    const onHashChange = () => {
      if (!window.location.hash) return;
      instantScrollToHash(window.location.hash);
    };

    const onHide = () => save(readScrollAnchor());

    const inputs = ["wheel", "touchstart", "keydown", "pointerdown"] as const;
    for (const type of inputs) window.addEventListener(type, onInput, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    window.addEventListener("pagehide", onHide);
    document.addEventListener("click", onClick);
    window.addEventListener("hashchange", onHashChange);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(saveTimer);
      for (const id of timers) window.clearTimeout(id);
      for (const type of inputs) window.removeEventListener(type, onInput);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("click", onClick);
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  return null;
}
