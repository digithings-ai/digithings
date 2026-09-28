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
