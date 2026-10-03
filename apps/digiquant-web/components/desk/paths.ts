import { pageByPath } from "../../../../clients/digiquant-tui/src/catalog";
import { isInviteSurface, publicCatalogPages } from "./public-surface";

/** /app and /app/ are the brief. Invite-only paths are not public routes. */
export function deskPathFromSlug(slug: string[] | undefined): string | null {
  if (!slug || slug.length === 0) return "/brief";
  const path = `/${slug.join("/")}`;
  if (!pageByPath(path) || isInviteSurface(path)) return null;
  return path;
}

export function deskHref(path: string): string {
  return `/app${path}/`;
}

export function deskStaticParams(): { slug: string[] }[] {
  return publicCatalogPages().map((page) => ({ slug: page.path.split("/").filter(Boolean) }));
}

export function isDeskPath(path: string): boolean {
  const bare = path.replace(/\/+$/, "") || "/";
  return bare === "/app" || bare.startsWith("/app/");
}

/** `/app` and `/app/brief/` are the brief. A desk path stays a desk path. */
export function deskPathFromPathname(pathname: string): string {
  const bare = pathname.replace(/\/+$/, "") || "/";
  if (bare === "/app") return "/brief";
  if (bare.startsWith("/app/")) return bare.slice("/app".length) || "/brief";
  return bare.startsWith("/") ? bare : `/${bare}`;
}

/** Same-origin message the marketing preview uses to change the desk page. */
export const DESK_GO_TYPE = "dq-desk-go";

export function readDeskGo(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const record = data as { type?: unknown; path?: unknown };
  if (record.type !== DESK_GO_TYPE || typeof record.path !== "string") return null;
  if (!record.path.startsWith("/") || record.path.startsWith("//")) return null;
  return record.path;
}
