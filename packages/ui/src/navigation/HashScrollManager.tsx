"use client";

import { useEffect } from "react";
import {
  hashIdFromHref,
  instantScrollToHash,
  instantScrollToId,
  isSamePageHashHref,
} from "./hashScroll";

/**
 * Same-page hash links jump instantly to their target section instead of
 * smooth-scrolling through tall scroll-driven blocks (pipeline, card stack, etc.).
 */
export function HashScrollManager() {
  useEffect(() => {
    const scrollInitialHash = () => {
      if (!window.location.hash) return;
      requestAnimationFrame(() => {
        instantScrollToHash(window.location.hash);
      });
    };

    scrollInitialHash();

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const anchor = (event.target as Element | null)?.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;

      const href = anchor.getAttribute("href");
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

    document.addEventListener("click", onClick);
    window.addEventListener("hashchange", onHashChange);

    return () => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("hashchange", onHashChange);
    };
  }, []);

  return null;
}
