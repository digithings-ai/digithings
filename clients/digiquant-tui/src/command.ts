import { DESKS } from "../../../apps/dashboard-api/src/access";
import { deskForPath, railRows, type RailRow } from "./rail";

/** How many path matches the web desk shows at once. */
export const COMMAND_LIMIT = 8;

export type DeskChoice = { id: string; label: string; blurb: string };

export type CommandHit = { path: string; label: string; desk: string };

function inviteText(value: string): boolean {
  return /12x/i.test(value) || /fx hub/i.test(value);
}

/** A desk with an invite group is not on the public terminal. */
export function isPublicDesk(desk: { id: string; label: string; blurb: string; group?: string }): boolean {
  if (desk.group === "12x" || desk.id === "fx") return false;
  if (inviteText(desk.label) || inviteText(desk.blurb)) return false;
  return true;
}

/** Invite pages stay out of the public page list, whatever desk currently owns them. */
export function isPublicPage(path: string, label = ""): boolean {
  if (path === "/fx" || path.startsWith("/fx/")) return false;
  if (inviteText(path) || inviteText(label)) return false;
  const owner = deskForPath(path);
  if (!owner) return true;
  const desk = DESKS.find((item) => item.id === owner);
  return desk ? isPublicDesk(desk) : false;
}

/** Public desks only. Baseline is the public desk. */
export function deskChoices(): DeskChoice[] {
  return DESKS.filter((desk) => isPublicDesk(desk)).map((desk) => ({
    id: desk.id,
    label: desk.label,
    blurb: desk.blurb,
  }));
}

export function deskIndex(id: string): number {
  const index = deskChoices().findIndex((desk) => desk.id === id);
  return index < 0 ? 0 : index;
}

/** Next public desk. An invite id stays on the public desk. */
export function nextDesk(id: string): string {
  const choices = deskChoices();
  const first = choices[0]?.id ?? "baseline";
  if (choices.length === 0) return first;
  const index = choices.findIndex((desk) => desk.id === id);
  if (index < 0) return first;
  return choices[(index + 1) % choices.length]?.id ?? first;
}

function withoutEmptyTitles(rows: RailRow[]): RailRow[] {
  return rows.filter((row, index) => {
    if (row.kind !== "title") return true;
    return rows[index + 1]?.kind === "page";
  });
}

/** The public web rail: same pages, order, and labels, without invite rows. */
export function publicRailRows(id: string): RailRow[] {
  const choices = deskChoices();
  const desk = choices.find((item) => item.id === id) ?? choices[0];
  if (!desk) return [];
  const rows = railRows(desk.id).flatMap((row) => {
    if (row.kind === "title") return inviteText(row.text) ? [] : [row];
    if (!isPublicPage(row.path, row.label)) return [];
    if (row.tag && inviteText(row.tag)) return [];
    return [row];
  });
  return withoutEmptyTitles(rows);
}

export function publicRailPaths(id: string): string[] {
  return publicRailRows(id).flatMap((row) => (row.kind === "page" ? [row.path] : []));
}

/** Rail pages for the public desk. An invite desk id still returns that public list. */
export function commandPages(activeDesk: string): CommandHit[] {
  const ids = deskChoices().map((desk) => desk.id);
  const ordered = ids.includes(activeDesk) ? [activeDesk, ...ids.filter((id) => id !== activeDesk)] : ids;
  const hits: CommandHit[] = [];
  const seen = new Set<string>();
  for (const id of ordered) {
    for (const row of publicRailRows(id)) {
      if (row.kind !== "page" || seen.has(row.path)) continue;
      seen.add(row.path);
      hits.push({ path: row.path, label: row.label, desk: id });
    }
  }
  return hits;
}

/** Case-insensitive match on the public rail path, its label, or the web desk href. */
export function searchCommandPages(query: string, activeDesk: string): CommandHit[] {
  const trimmed = query.trim().toLowerCase();
  const needle = trimmed.replace(/^\//, "").replace(/^app\/?/, "");
  const all = commandPages(activeDesk);
  if (!needle) return all;
  return all.filter((page) => {
    const path = page.path.toLowerCase();
    const href = `/app${path}/`.toLowerCase();
    const label = page.label.toLowerCase();
    return path.replace(/^\//, "").includes(needle) || label.includes(needle) || href.includes(trimmed);
  });
}
