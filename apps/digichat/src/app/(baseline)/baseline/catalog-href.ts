import { p } from "@/lib/base-path";

/**
 * Href for a catalog skin / theme link. The nav uses plain <a> tags, which
 * Next does not basePath-prefix (only <Link> and the router do), so under
 * /chat an unprefixed "/baseline?theme=dark" 404ed. p() adds the base path
 * ("" when the app is served at the root).
 */
export function catalogHref(skin: string, theme: string): string {
  const qs = new URLSearchParams();
  if (skin !== "base") qs.set("skin", skin);
  if (theme === "dark") qs.set("theme", "dark");
  const query = qs.toString();
  return p(query ? `/baseline?${query}` : "/baseline");
}
