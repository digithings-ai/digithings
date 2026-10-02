import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import { deskHref } from "./paths";
import { WEB_SLOTS } from "./web-slots";

/** Pages the slash field can open. LuxAlgo is not one of them. */
const COMMAND_PAGES: { path: string; label: string }[] = [
  ...PAGES.map((page) => ({ path: page.path, label: page.label })),
  ...WEB_SLOTS.map((slot) => ({ path: slot.path, label: slot.label })),
];

export type DeskCommandHit = { path: string; label: string; href: string };

/** Case-insensitive match on the catalog path, the label, or the desk href. */
export function searchDeskPages(q: string): DeskCommandHit[] {
  const needle = q.trim().toLowerCase().replace(/^\//, "");
  const all = COMMAND_PAGES.map((page) => ({ ...page, href: deskHref(page.path) }));
  if (!needle) return all;
  return all.filter(
    (page) =>
      page.path.toLowerCase().includes(needle) ||
      page.label.toLowerCase().includes(needle) ||
      page.href.toLowerCase().includes(needle),
  );
}
