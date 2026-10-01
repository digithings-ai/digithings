/** Whether `href` targets a hash on the current document (same origin + path). */
export function isSamePageHashHref(href: string, locationHref = window.location.href): boolean {
  if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) return false;

  let url: URL;
  try {
    url = new URL(href, locationHref);
  } catch {
    return false;
  }

  const current = new URL(locationHref);
  if (url.origin !== current.origin || !url.hash) return false;

  const normalize = (pathname: string) => {
    if (pathname === "/index.html") return "/";
    return pathname;
  };

  return normalize(url.pathname) === normalize(current.pathname);
}

export function hashIdFromHref(href: string, locationHref = window.location.href): string | null {
  if (!isSamePageHashHref(href, locationHref)) return null;
  const hash = new URL(href, locationHref).hash;
  return hash.length > 1 ? hash.slice(1) : null;
}

/** Jump directly to a section — no smooth scroll through intermediate scroll-driven UI. */
export function instantScrollToId(id: string): boolean {
  const el = document.getElementById(id);
  if (!el) return false;
  el.scrollIntoView({ behavior: "instant", block: "start" });
  return true;
}

export function instantScrollToHash(hash: string): boolean {
  const id = hash.replace(/^#/, "");
  return id ? instantScrollToId(id) : false;
}

/**
 * Where the reader is, as content rather than pixels: the innermost
 * `main section[id]` under the line just below the fixed bar, and how far
 * through it that line sits. Viewport-sized bands (pinned tours, scrolly
 * grids) change height with the viewport, so a raw scrollY lands somewhere
 * else after a zoom; the same fraction of the same section does not.
 */
export interface ScrollAnchor {
  id: string | null;
  frac: number;
  y: number;
}

function anchorLine(): number {
  const pad = Number.parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop);
  return (Number.isFinite(pad) ? pad : 0) + 1;
}

export function readScrollAnchor(): ScrollAnchor {
  const line = anchorLine();
  let anchor: ScrollAnchor = { id: null, frac: 0, y: window.scrollY };
  if (window.scrollY < 1) return anchor;
  for (const el of document.querySelectorAll<HTMLElement>("main section[id]")) {
    const box = el.getBoundingClientRect();
    if (box.height > 0 && box.top <= line && box.bottom > line) {
      anchor = { id: el.id, frac: (line - box.top) / box.height, y: window.scrollY };
    }
  }
  return anchor;
}

export function scrollTopForAnchor(anchor: ScrollAnchor): number {
  const el = anchor.id ? document.getElementById(anchor.id) : null;
  if (!el) return anchor.y;
  const box = el.getBoundingClientRect();
  return window.scrollY + box.top + anchor.frac * box.height - anchorLine();
}
