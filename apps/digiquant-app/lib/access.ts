/**
 * Access manifest (dashboard-api CONTRACT §6.9). The API owns entitlements:
 * the app renders sidebar, page guards and locked blocks from this alone.
 */
import type { NavGroup, NavNode } from './nav';

export type Access = 'granted' | 'locked';
export type BlockEntry = { id: string; route: string; access: Access; reason?: string };
export type PageEntry = { path: string; label: string; status?: 'wip' | 'soon'; access: Access; reason?: string; blocks: BlockEntry[] };
export type DeskEntry = { id: string; label: string; blurb: string; access: Access; reason?: string; pages: PageEntry[] };
export type Manifest = { caller: { tier: string; groups: string[] }; desks: DeskEntry[]; routes: string[] };

/** Short tag for a locked node: "Requires pro" → "pro", "Requires the 12x group" → "12x". */
export function lockTag(reason?: string): string {
  const m = reason?.match(/^Requires (?:the )?(\S+)/);
  return m ? m[1] : 'locked';
}

/** First desk (preferring `prefer`) that lists this path. */
export function findEntry(m: Manifest, path: string, prefer?: string): { desk: DeskEntry; page: PageEntry } | null {
  const hits = m.desks.flatMap((desk) => desk.pages.filter((p) => p.path === path).map((page) => ({ desk, page })));
  return hits.find((h) => h.desk.id === prefer) ?? hits[0] ?? null;
}

/** First granted block with this id anywhere, else the first locked one, else null (not governed). */
export function blockAccess(m: Manifest, id: string): BlockEntry | null {
  let locked: BlockEntry | null = null;
  for (const d of m.desks) for (const p of d.pages) for (const b of p.blocks) {
    if (b.id !== id) continue;
    if (b.access === 'granted') return b;
    locked ??= b;
  }
  return locked;
}

/**
 * Desk pages → sidebar groups. A page is a child when its parent path is also
 * a page of the desk; otherwise it is top-level, grouped under its first
 * segment when it has two (`/tools/charts` → "tools").
 */
export function navFromDesk(desk: DeskEntry): NavGroup[] {
  const paths = new Set(desk.pages.map((p) => p.path));
  const node = (p: PageEntry): NavNode => ({ path: p.path, label: p.label, status: p.status, lock: p.access === 'locked' ? lockTag(p.reason) : undefined });
  const parentOf = (path: string) => path.slice(0, path.lastIndexOf('/'));
  const tops: NavNode[] = [];
  for (const p of desk.pages) {
    const parent = parentOf(p.path);
    if (parent && paths.has(parent)) continue;
    const n = node(p);
    const kids = desk.pages.filter((c) => parentOf(c.path) === p.path).map(node);
    if (kids.length) n.children = kids;
    tops.push(n);
  }
  const groups: NavGroup[] = [];
  for (const n of tops) {
    const seg = n.path.split('/').filter(Boolean);
    const title = seg.length >= 2 ? seg[0] : null;
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.items.push(n);
    else groups.push({ title, items: [n] });
  }
  return groups;
}

export function flatNav(groups: NavGroup[]): NavNode[] {
  const out: NavNode[] = [];
  const walk = (n: NavNode) => { out.push(n); n.children?.forEach(walk); };
  groups.forEach((g) => g.items.forEach(walk));
  return out;
}
