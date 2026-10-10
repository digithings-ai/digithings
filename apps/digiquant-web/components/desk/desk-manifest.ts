import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import { deskHref } from "./paths";
import { isVisibleDesk } from "./public-surface";
import { WEB_SLOTS } from "./web-slots";

/** Caller entitlements from GET /access/manifest. The worker decides access. */
export type Access = "granted" | "locked";

export type ManifestPage = {
  path: string;
  label: string;
  status?: "wip" | "soon";
  access: Access;
  reason?: string;
};

export type ManifestDesk = {
  id: string;
  label: string;
  blurb: string;
  access: Access;
  reason?: string;
  pages: ManifestPage[];
};

export type Manifest = {
  caller: { tier: string; groups: string[] };
  desks: ManifestDesk[];
};

export type NavNode = {
  path: string;
  label: string;
  status?: "wip" | "soon";
  lock?: string;
  children?: NavNode[];
};

export type NavGroup = { title: string | null; items: NavNode[] };

const OPENABLE = new Set<string>([...PAGES.map((page) => page.path), ...WEB_SLOTS.map((slot) => slot.path)]);

/** A manifest page the web desk already has a route for. Access is the manifest's call. */
export function canOpenDeskPath(path: string): boolean {
  return OPENABLE.has(path);
}

/** Browser path (`/app/fx/ideas/`) → the manifest path (`/fx/ideas`). */
export function manifestPath(pathname: string): string {
  const bare = pathname.replace(/\/+$/, "") || "/";
  if (bare === "/app") return "/brief";
  if (bare.startsWith("/app/")) return bare.slice("/app".length);
  return bare;
}

/** "Requires the 12x group" → "12x". "Requires brief" → "brief". */
export function lockTag(reason?: string): string {
  const match = reason?.match(/^Requires (?:the |a |an )?(\S+)/i);
  const tag = match?.[1].replace(/[.,;:]+$/, "").toLowerCase();
  return tag || "locked";
}

export function sectionOf(path: string): string {
  return `/${path.split("/").filter(Boolean)[0] ?? ""}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readAccess(value: unknown): Access | null {
  if (value === "granted" || value === "locked") return value;
  return null;
}

/** Read the worker envelope. A missing or partial catalog is not filled in. */
export function parseManifest(body: unknown): Manifest | null {
  const root = isRecord(body) && isRecord(body.data) ? body.data : body;
  if (!isRecord(root) || !Array.isArray(root.desks)) return null;
  const caller = isRecord(root.caller) ? root.caller : {};
  const desks: ManifestDesk[] = [];
  for (const item of root.desks) {
    if (!isRecord(item) || typeof item.id !== "string" || typeof item.label !== "string") return null;
    if (!Array.isArray(item.pages)) return null;
    const access = readAccess(item.access);
    if (!access) return null;
    const pages: ManifestPage[] = [];
    for (const page of item.pages) {
      if (!isRecord(page) || typeof page.path !== "string" || typeof page.label !== "string") return null;
      const pageAccess = readAccess(page.access);
      if (!pageAccess) return null;
      const status = page.status === "wip" || page.status === "soon" ? page.status : undefined;
      pages.push({
        path: page.path,
        label: page.label,
        access: pageAccess,
        ...(status ? { status } : {}),
        ...(typeof page.reason === "string" ? { reason: page.reason } : {}),
      });
    }
    desks.push({
      id: item.id,
      label: item.label,
      blurb: typeof item.blurb === "string" ? item.blurb : "",
      access,
      ...(typeof item.reason === "string" ? { reason: item.reason } : {}),
      pages,
    });
  }
  const groups = Array.isArray(caller.groups)
    ? caller.groups.filter((group): group is string => typeof group === "string")
    : [];
  return {
    caller: { tier: typeof caller.tier === "string" ? caller.tier : "", groups },
    desks,
  };
}

/**
 * Desk pages → folder groups. A page is a child when its parent path is also
 * a page; otherwise it is top-level, grouped under its first segment when it
 * has two (`/tools/charts` → "tools").
 */
export function navFromDesk(desk: ManifestDesk): NavGroup[] {
  const pages = desk.pages;
  const paths = new Set(pages.map((page) => page.path));
  const node = (page: ManifestPage): NavNode => ({
    path: page.path,
    label: page.label,
    status: page.status,
    lock: page.access === "locked" ? lockTag(page.reason) : undefined,
  });
  const parentOf = (path: string) => path.slice(0, path.lastIndexOf("/"));
  const tops: NavNode[] = [];
  for (const page of pages) {
    const parent = parentOf(page.path);
    if (parent && paths.has(parent)) continue;
    const item = node(page);
    const kids = pages.filter((child) => parentOf(child.path) === page.path).map(node);
    if (kids.length) item.children = kids;
    tops.push(item);
  }
  const groups: NavGroup[] = [];
  for (const item of tops) {
    const seg = item.path.split("/").filter(Boolean);
    const title = seg.length >= 2 ? seg[0] : null;
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.items.push(item);
    else groups.push({ title, items: [item] });
  }
  return groups;
}

/** Where Enter on a desk goes. A locked desk has nowhere to go. */
export function deskHomeHref(desk: ManifestDesk): string | null {
  if (desk.access === "locked") return null;
  const home = desk.pages.find((page) => page.access === "granted" && canOpenDeskPath(page.path));
  return home ? deskHref(home.path) : null;
}

export function findDeskId(manifest: Manifest, path: string, prefer?: string | null): string | null {
  const hits = manifest.desks.filter((desk) => desk.pages.some((page) => page.path === path));
  return hits.find((desk) => desk.id === prefer)?.id ?? hits[0]?.id ?? null;
}

/** The granted desk that owns the path, else the stored desk, else the first granted desk. */
export function selectDesk(manifest: Manifest | null, prefer: string | null): ManifestDesk | null {
  if (!manifest) return null;
  const desks = manifest.desks.filter((desk) => isVisibleDesk(desk));
  const granted = desks.find((desk) => desk.access === "granted");
  return (
    desks.find((desk) => desk.id === prefer && desk.access === "granted") ??
    granted ??
    desks[0] ??
    null
  );
}
