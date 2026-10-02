/** Walkthrough policy for the embedded digiquant terminal.
 *  Clicks are real sidebar anchors. A trusted pointer, wheel, or key yields. */

export const DESK_EMBED_SRC = "/app";

export const WALK_STOPS = ["Brief", "Portfolio", "Pipeline"] as const;

export type WalkStop = (typeof WALK_STOPS)[number];

export type DeskPhase = "opening" | "walking" | "yours" | "live" | "empty";

export const OPEN_BUDGET_MS = 20_000;

export const WALK_DWELL_MS = 3_200;

export const CLICK_FALLBACK_MS = 900;

export const DESK_YIELD_LABEL = "Take control";

export const DESK_EMPTY_COPY =
  "The terminal did not load. This frame stays empty. No figures are filled in.";

const YIELD_TYPES = new Set(["pointerdown", "wheel", "keydown"]);

export function deskStatus(phase: DeskPhase): string {
  switch (phase) {
    case "opening":
      return "Opening the terminal.";
    case "walking":
      return "Walking Brief, Portfolio, and Pipeline.";
    case "yours":
      return "You have the terminal.";
    case "live":
      return "The terminal is in this frame. The walkthrough stays off because this frame is not same-origin.";
    case "empty":
      return "The terminal did not load.";
    default: {
      const never: never = phase;
      return never;
    }
  }
}

export function anchorLabel(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

export function shouldYieldToUser(event: { isTrusted: boolean; type: string }): boolean {
  return event.isTrusted && YIELD_TYPES.has(event.type);
}

export function bindYieldListeners(target: EventTarget, onYield: () => void): () => void {
  const handler = (event: Event) => {
    if (shouldYieldToUser(event)) onYield();
  };
  for (const type of YIELD_TYPES) target.addEventListener(type, handler, true);
  return () => {
    for (const type of YIELD_TYPES) target.removeEventListener(type, handler, true);
  };
}

function routePath(href: string): string {
  return href.replace(/[?#].*$/, "").replace(/\/+$/, "") || "/";
}

/** True when this href is that terminal stop. /app alone is Brief, after the root redirect. */
export function pathMatchesStop(href: string, stop: WalkStop): boolean {
  const path = routePath(href);
  if (stop === "Pipeline") return path === "/app/pipeline" || path.startsWith("/app/pipeline/");
  if (stop === "Portfolio") return path === "/app/portfolio" || path.startsWith("/app/portfolio/");
  return path === "/app" || path === "/app/brief" || path.startsWith("/app/brief/");
}

/** Sidebar anchor for one stop. Href must be the terminal route, so the landing nav's Pipeline link does not match. */
export function navAnchor(doc: Document, stop: WalkStop): HTMLAnchorElement | null {
  const nav = doc.querySelector('nav[aria-label="Pages"]');
  if (!nav) return null;
  for (const node of nav.querySelectorAll("a")) {
    const href = node.getAttribute("href") ?? "";
    if (pathMatchesStop(href, stop)) return node as HTMLAnchorElement;
  }
  return null;
}

export function dashboardReady(doc: Document): boolean {
  return WALK_STOPS.every((stop) => navAnchor(doc, stop) != null);
}

export function stopFromPath(pathname: string): WalkStop | null {
  if (pathMatchesStop(pathname, "Pipeline")) return "Pipeline";
  if (pathMatchesStop(pathname, "Portfolio")) return "Portfolio";
  if (pathMatchesStop(pathname, "Brief")) return "Brief";
  return null;
}

export function activeStop(doc: Document): WalkStop | null {
  try {
    const fromPath = stopFromPath(doc.location.pathname);
    if (fromPath) return fromPath;
  } catch {
    /* The frame is opaque. Fall through to the sidebar's current page. */
  }
  for (const stop of WALK_STOPS) {
    const link = navAnchor(doc, stop);
    if (link?.getAttribute("aria-current") === "page") return stop;
  }
  return null;
}

/** Next sidebar anchor from the frame's current route. */
export function nextWalkAnchor(doc: Document): HTMLAnchorElement | null {
  return navAnchor(doc, nextWalkStop(activeStop(doc)));
}

/** The frame opens on Brief. Null means that home route. */
export function nextWalkStop(current: WalkStop | null): WalkStop {
  if (current == null) return "Portfolio";
  const index = WALK_STOPS.indexOf(current);
  if (index < 0) return "Portfolio";
  return WALK_STOPS[(index + 1) % WALK_STOPS.length];
}

export type EmbedProbe =
  | { kind: "scriptable"; href: string }
  | { kind: "cross-origin" }
  | { kind: "closed" };

export function probeEmbed(frame: { contentDocument: Document | null }): EmbedProbe {
  let doc: Document | null;
  try {
    doc = frame.contentDocument;
  } catch {
    return { kind: "cross-origin" };
  }
  if (!doc) return { kind: "cross-origin" };
  let href = "";
  try {
    href = doc.location?.href ?? "";
  } catch {
    return { kind: "cross-origin" };
  }
  if (href === "" || href === "about:blank") return { kind: "closed" };
  return { kind: "scriptable", href };
}

/** Same-origin document that is a 404 or a dead proxy, and not the terminal shell. */
export function embedLooksDown(doc: Document): boolean {
  if (dashboardReady(doc)) return false;
  const title = doc.title ?? "";
  if (title.startsWith("No such page")) return true;
  if (title.includes("Internal Server Error")) return true;
  const text = doc.body?.textContent ?? "";
  return (
    text.includes("Nothing is filed under this address.") ||
    text.includes("ECONNREFUSED") ||
    text.includes("Failed to proxy")
  );
}

/** Click the real anchor. If that does not change the frame URL, follow its href. */
export function activateNavLink(link: HTMLAnchorElement): () => void {
  let before: string | null = null;
  try {
    before = link.ownerDocument.location.href;
  } catch {
    before = null;
  }
  link.click();
  const timer = setTimeout(() => {
    if (!link.isConnected) return;
    let now: string | null = null;
    try {
      now = link.ownerDocument.location.href;
    } catch {
      return;
    }
    if (before != null && now === before) {
      try {
        link.ownerDocument.location.assign(link.href);
      } catch {
        /* The frame already moved. */
      }
    }
  }, CLICK_FALLBACK_MS);
  return () => clearTimeout(timer);
}
