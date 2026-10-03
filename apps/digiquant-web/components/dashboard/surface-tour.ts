/** Homepage desk: which surface is in the frame, and which page comes next. */

import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";

export const SLIDER_MIN = 0;
export const SLIDER_MAX = 100;

/** 0 brings the terminal across the frame. 100 brings the web app across. */
export const TERMINAL_AT = SLIDER_MIN;
export const HOSTED_AT = SLIDER_MAX;

export const SELF_HOSTED_TITLE = "Self-hosted";
export const SELF_HOSTED_COPY =
  "The terminal runs on your computer. You run pipelines, models, and strategies yourself.";

export const HOSTED_TITLE = "Hosted";
export const HOSTED_COPY =
  "Paying makes the hosted services available. The web app hosts pipelines and runs the strategies.";

export const TOUR_CAPTION = "The pages tour until you move the slider or open a page.";

export const TOUR_DWELL_MS = 4_200;
export const IDLE_RESUME_MS = 8_000;

export const WEB_EMPTY_COPY =
  "The web app did not load. This frame stays empty. No figures are filled in.";

export type Surface = "terminal" | "web";

export type StagePhase = "opening" | "touring" | "yours" | "live" | "empty";

export function surfaceFromSlider(value: number): Surface {
  return value < 50 ? "terminal" : "web";
}

export function nextTerminalPath(current: string): string {
  const index = PAGES.findIndex((page) => page.path === current);
  return PAGES[(index + 1) % PAGES.length]?.path ?? PAGES[0].path;
}

/** `/app` and `/app/brief/` are the brief. Anything else keeps its desk path. */
export function deskPathFromLocation(pathname: string): string {
  const bare = pathname.replace(/\/+$/, "") || "/";
  if (bare === "/app") return "/brief";
  if (bare.startsWith("/app/")) return bare.slice("/app".length) || "/brief";
  return bare.startsWith("/") ? bare : `/${bare}`;
}

/** Next real desk route when the sidebar has not listed pages yet. */
export function nextWebPath(pathname: string): string {
  const current = deskPathFromLocation(pathname);
  const known = PAGES.some((page) => page.path === current);
  return nextTerminalPath(known ? current : "/brief");
}

export function prevTerminalPath(current: string): string {
  const index = PAGES.findIndex((page) => page.path === current);
  const start = index < 0 ? 0 : index;
  return PAGES[(start - 1 + PAGES.length) % PAGES.length]?.path ?? PAGES[0].path;
}

export function stageStatus(phase: StagePhase, surface: Surface): string {
  switch (phase) {
    case "opening":
      return surface === "web" ? "Opening the web app." : "Opening the terminal screens.";
    case "touring":
      return surface === "web" ? "Touring the web app." : "Touring the terminal.";
    case "yours":
      return "You have this view.";
    case "live":
      return "The web app is in this frame. The tour stays off because this frame is not same-origin.";
    case "empty":
      return "The web app did not load.";
    default: {
      const never: never = phase;
      return never;
    }
  }
}

function routePath(href: string): string {
  const noHash = href.replace(/[?#].*$/, "");
  const path = noHash.includes("://") ? (noHash.replace(/^[a-z][a-z0-9+.-]*:\/\/[^/]+/i, "") || "/") : noHash;
  return path.replace(/\/+$/, "") || "/";
}

/** The desk shell is up when its page rail is in the document.
 *  A failed manifest still draws that rail ("access unavailable"). Flight data
 *  can also carry the site's not-found sentence, so the rail is the check. */
export function deskShellLoaded(doc: Document): boolean {
  return doc.querySelector('nav[aria-label="Pages"]') != null;
}

/** Sidebar anchors that open a real `/app` page. The landing pipeline link does not. */
export function deskAnchors(doc: Document): HTMLAnchorElement[] {
  const nav = doc.querySelector('nav[aria-label="Pages"]');
  if (!nav) return [];
  const links: HTMLAnchorElement[] = [];
  for (const node of nav.querySelectorAll("a")) {
    const path = routePath(node.getAttribute("href") ?? "");
    if (path === "/app" || path.startsWith("/app/")) links.push(node as HTMLAnchorElement);
  }
  return links;
}

/** Next web-desk page in sidebar order. One link has nowhere to tour. */
export function nextDeskAnchor(doc: Document): HTMLAnchorElement | null {
  const links = deskAnchors(doc);
  if (links.length < 2) return null;
  let here = "";
  try {
    here = routePath(doc.location?.pathname ?? "");
  } catch {
    here = "";
  }
  let current = here ? links.findIndex((link) => routePath(link.getAttribute("href") ?? "") === here) : -1;
  if (current < 0) current = links.findIndex((link) => link.getAttribute("aria-current") === "page");
  return links[(current + 1) % links.length] ?? null;
}
