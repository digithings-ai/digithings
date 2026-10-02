import { PAGES, pageByPath } from "../../../../clients/digiquant-tui/src/catalog";

/** /app and /app/ are the brief. Every other slug is a terminal page path. */
export function deskPathFromSlug(slug: string[] | undefined): string | null {
  if (!slug || slug.length === 0) return "/brief";
  const path = `/${slug.join("/")}`;
  return pageByPath(path) ? path : null;
}

export function deskHref(path: string): string {
  return `/app${path}/`;
}

export function deskStaticParams(): { slug: string[] }[] {
  return PAGES.map((page) => ({ slug: page.path.split("/").filter(Boolean) }));
}

export function isDeskPath(path: string): boolean {
  const bare = path.replace(/\/+$/, "") || "/";
  return bare === "/app" || bare.startsWith("/app/");
}
