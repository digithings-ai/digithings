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
