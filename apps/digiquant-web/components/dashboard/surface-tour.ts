/** Homepage desk: the shared page, and how the reveal handle sits. */

import { deskPathFromPathname } from "@/components/desk/paths";
import { publicCatalogPages } from "@/components/desk/public-surface";

const PAGES = publicCatalogPages();

export const TERMINAL_TITLE = "terminal UI";
export const TERMINAL_COPY =
  "the terminal UI, one-to-one with the web app. You run pipelines and strategies locally, host it yourself, and configure your own API tokens and local models.";

export const WEB_TITLE = "web app";
export const WEB_COPY =
  "the same desk, delegated. A subscription so you do not host the infrastructure on your own machine.";

export const TOUR_DWELL_MS = 4_200;
export const IDLE_RESUME_MS = 8_000;

/** The handle can close either side. Both frames stay full size under the clip. */
export const SPLIT_MIN = 0;
export const SPLIT_MAX = 1;

/** Where the handle rests after the one-time sweep, so both apps are visible. */
export const REVEAL_REST = 0.5;
export const REVEAL_SWEEP_MS = 900;
export const REVEAL_RETURN_MS = 600;

export const WEB_EMPTY_COPY =
  "The web app did not load. This frame stays empty. No figures are filled in.";

export type Surface = "terminal" | "web";

export type StagePhase = "opening" | "touring" | "yours" | "live" | "empty";

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

export function clampSplit(share: number): number {
  if (Number.isNaN(share)) return REVEAL_REST;
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, share));
}

/** Terminal-side fraction for a pointer on the stage. The handle may sit on either edge. */
export function splitFromPointer(clientX: number, left: number, width: number): number {
  if (width <= 0) return REVEAL_REST;
  return clampSplit((clientX - left) / width);
}

/** The sentence is placed only when its full width fits the visible slice. */
export function sentenceFits(textWidth: number, visibleWidth: number): boolean {
  if (!Number.isFinite(textWidth) || !Number.isFinite(visibleWidth) || visibleWidth <= 0) return false;
  return Math.ceil(textWidth) <= Math.floor(visibleWidth);
}

/** One sweep from the left edge to the right edge, then back to the resting split. */
export function revealShare(elapsedMs: number, reduced: boolean): number {
  if (reduced || !Number.isFinite(elapsedMs)) return REVEAL_REST;
  if (elapsedMs <= 0) return 0;
  if (elapsedMs < REVEAL_SWEEP_MS) return elapsedMs / REVEAL_SWEEP_MS;
  const back = elapsedMs - REVEAL_SWEEP_MS;
  if (back >= REVEAL_RETURN_MS) return REVEAL_REST;
  return 1 + (REVEAL_REST - 1) * (back / REVEAL_RETURN_MS);
}

export type WiderSide = Surface | "even";

/** Which story matches the wider pane. A tie lights neither tile. */
export function widerSide(share: number): WiderSide {
  if (share > 0.5) return "terminal";
  if (share < 0.5) return "web";
  return "even";
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
