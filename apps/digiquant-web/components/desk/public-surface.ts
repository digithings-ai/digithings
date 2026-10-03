import { PAGES, pageByPath, type Page } from "../../../../clients/digiquant-tui/src/catalog";

/** Invite-only names. The public site does not print them or route to them. */
const INVITE = /12x|fx hub/i;

/**
 * FX Hub and the 12x desk stay off the public website.
 * An invited caller still reaches them through the access manifest, not these pages.
 */
export function isInviteSurface(path: string, label = ""): boolean {
  if (path === "/fx" || path.startsWith("/fx/")) return true;
  if (INVITE.test(path) || INVITE.test(label)) return true;
  const page = pageByPath(path);
  if (!page) return false;
  return page.group === "FX Hub" || INVITE.test(page.group) || INVITE.test(page.label);
}

/** Catalog pages the public desk, tour, and command list may show. */
export function publicCatalogPages(): Page[] {
  return PAGES.filter((page) => !isInviteSurface(page.path, page.label));
}

/** A desk the public rail and picker may name. Invite desks stay off this site. */
export function isPublicDeskChrome(desk: { id: string; label: string; blurb?: string; reason?: string }): boolean {
  if (desk.id === "fx") return false;
  return !INVITE.test(`${desk.label} ${desk.blurb ?? ""} ${desk.reason ?? ""}`);
}
