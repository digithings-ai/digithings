/** Homepage desk: the shared page, and how wide each pane is. */

import { publicCatalogPages } from "@/components/desk/public-surface";

const PAGES = publicCatalogPages();

export const SELF_HOSTED_TITLE = "Self-hosted";
export const SELF_HOSTED_COPY =
  "The terminal UI, one-to-one with the hosted desk. You run pipelines and strategies locally, host it yourself, and configure your own API tokens and local models.";

export const HOSTED_TITLE = "Hosted";
export const HOSTED_COPY =
  "The same desk, delegated. A subscription so you do not host the infrastructure on your own machine.";

export const TOUR_DWELL_MS = 4_200;
export const IDLE_RESUME_MS = 8_000;
export const PAGE_FADE_MS = 700;

/** Both panes stay on screen. The gap cannot close either one. */
export const SPLIT_MIN = 0.28;
export const SPLIT_MAX = 0.72;

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

export function clampSplit(share: number): number {
  if (Number.isNaN(share)) return 0.5;
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, share));
}

/** Left-pane fraction for a pointer on the stage. `gap` is the center column. */
export function splitFromPointer(clientX: number, left: number, width: number, gap = 0): number {
  const usable = width - gap;
  if (usable <= 0) return 0.5;
  return clampSplit((clientX - left - gap / 2) / usable);
}

export type WiderSide = Surface | "even";

/** Which story matches the wider pane. A tie lights neither tile. */
export function widerSide(share: number): WiderSide {
  if (share > 0.5) return "terminal";
  if (share < 0.5) return "web";
  return "even";
}

/** Pages mounted together so the outgoing page can fade while the next one loads. */
export function paneLayers(
  settled: string,
  path: string,
  leaving: string | null,
  preload: string | null,
): string[] {
  const layers: string[] = [];
  for (const item of [leaving, settled, path, preload]) {
    if (item && !layers.includes(item)) layers.push(item);
  }
  return layers;
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
