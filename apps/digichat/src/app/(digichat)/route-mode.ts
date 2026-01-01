/**
 * Surface selected by `?mode=` on the single digichat route `/`.
 *
 * Bare `/` is the product chat. The three-surface menu is a development tool,
 * reachable only through `?mode=menu`: the DIG-5121 cutover moved this root onto
 * the public digithings.ai/chat, where a dev menu is not a landing page.
 * Unknown or repeated values fall through to the product surface, never the
 * menu, so a stray query parameter can never replace the chat with a picker.
 */
export type RouteMode = "product" | "embed" | "catalog" | "menu";

export function resolveRouteMode(
  mode: string | string[] | undefined,
): RouteMode {
  if (mode === "embed") return "embed";
  if (mode === "catalog") return "catalog";
  if (mode === "menu") return "menu";
  return "product";
}
