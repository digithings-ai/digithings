/** Homepage desk: one embedded app. Terminal first, then the web app. */

import { deskPathFromPathname } from "@/components/desk/paths";
import { isAccountSurface, publicCatalogPages } from "@/components/desk/public-surface";

const PAGES = publicCatalogPages().filter((page) => !isAccountSurface(page.path));

export const TERMINAL_TITLE = "terminal UI";
export const TERMINAL_COPY =
  "The terminal UI and the web app are nearly one to one. Here you self-host: run your own pipelines on this machine, connect local models, and serve digiquant yourself.";
export const TERMINAL_EDGE =
  "Advantage: your machine, your models, and pipelines that stay on your infrastructure.";

export const WEB_TITLE = "web app";
export const WEB_COPY =
  "The web app and the terminal UI are nearly one to one. Use the free tier, or the base subscription with the baseline pipeline. Paid hosting runs your own pipelines, and those pipelines appear on this desk too.";
export const WEB_EDGE =
  "Advantage: nothing to run yourself. The baseline pipeline is included, and the pipelines you pay to host show up here.";

/** Scrolling must pause this long, with the stage on screen, before the next scroll may switch views. */
export const SCROLL_SETTLE_MS = 180;

export type Surface = "terminal" | "web";

export type StageScroll = {
  surface: Surface;
  /** The automatic terminal-to-web switch has already happened. */
  slid: boolean;
  /** The stage is on screen and scrolling has paused, so the next scroll may switch. */
  armed: boolean;
};

export function initialStageScroll(): StageScroll {
  return { surface: "terminal", slid: false, armed: false };
}

/**
 * A scroll while the stage is visible. An unarmed scroll does not switch.
 * The first armed scroll moves the terminal view to the web app, once.
 * Leaving the screen before that switch disarms it, so arrival scrolling
 * does not skip the terminal.
 */
export function onStageScroll(state: StageScroll, visible: boolean): StageScroll {
  if (state.slid) return state;
  if (!visible) return state.armed ? { ...state, armed: false } : state;
  if (!state.armed) return state;
  return { surface: "web", slid: true, armed: true };
}

/** Arm the switch after scrolling has paused with the stage on screen. */
export function armStageScroll(state: StageScroll, visible: boolean): StageScroll {
  if (state.slid || !visible || state.armed) return state;
  return { ...state, armed: true };
}

export function nextTerminalPath(current: string): string {
  const index = PAGES.findIndex((page) => page.path === current);
  return PAGES[(index + 1) % PAGES.length]?.path ?? PAGES[0].path;
}

/** `/app` and `/app/brief/` are the brief. Anything else keeps its desk path. */
export function deskPathFromLocation(pathname: string): string {
  return deskPathFromPathname(pathname);
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
