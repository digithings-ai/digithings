import { DESKS } from "../../../apps/dashboard-api/src/access";
import {
  navFromDesk,
  type ManifestDesk,
  type NavGroup,
} from "../../../apps/digiquant-web/components/desk/desk-manifest";

export type RailPage = {
  kind: "page";
  path: string;
  label: string;
  depth: 0 | 1;
  folder: boolean;
  tag?: string;
};

export type RailRow = { kind: "title"; text: string } | RailPage;

/** The same desk the web rail folds, with every page granted. Locks stay off. */
export function grantedDesk(id: string): ManifestDesk | null {
  const desk = DESKS.find((item) => item.id === id);
  if (!desk) return null;
  return {
    id: desk.id,
    label: desk.label,
    blurb: desk.blurb,
    access: "granted",
    pages: desk.pages.map((page) => ({
      path: page.path,
      label: page.label,
      access: "granted" as const,
      ...(page.status ? { status: page.status } : {}),
    })),
  };
}

export function deskLabel(id: string): string {
  return grantedDesk(id)?.label ?? id;
}

export function deskForPath(path: string): string | null {
  for (const desk of DESKS) {
    if (desk.pages.some((page) => page.path === path)) return desk.id;
  }
  return null;
}

export function railGroups(id: string): NavGroup[] {
  const desk = grantedDesk(id);
  return desk ? navFromDesk(desk) : [];
}

/** Folder rows in web order. `/settings` is already dropped by `navFromDesk`. */
export function railRows(id: string): RailRow[] {
  const rows: RailRow[] = [];
  for (const group of railGroups(id)) {
    if (group.title) rows.push({ kind: "title", text: group.title });
    for (const item of group.items) {
      const kids = item.children ?? [];
      rows.push({
        kind: "page",
        path: item.path,
        label: item.label,
        depth: 0,
        folder: kids.length > 0,
        ...(item.lock ? { tag: item.lock } : item.status ? { tag: item.status } : {}),
      });
      for (const child of kids) {
        rows.push({
          kind: "page",
          path: child.path,
          label: child.label,
          depth: 1,
          folder: false,
          ...(child.lock ? { tag: child.lock } : child.status ? { tag: child.status } : {}),
        });
      }
    }
  }
  return rows;
}

export function railPaths(id: string): string[] {
  return railRows(id).flatMap((row) => (row.kind === "page" ? [row.path] : []));
}

export function railLine(row: RailPage): string {
  const tri = row.folder ? "▾" : "▸";
  const pad = row.depth ? "  " : "";
  const tag = row.tag ? ` [${row.tag}]` : "";
  return `${pad}${tri} ${row.path}${tag}`;
}
