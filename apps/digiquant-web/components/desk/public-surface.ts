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

/**
 * Desk settings (folded in from apps/digiquant-app). On the desk, not in the
 * marketing tour, and not a legacy /dashboard target: /dashboard/settings is
 * still the apps/dashboard account page until that app retires.
 */
export function isAccountSurface(path: string): boolean {
  return path === "/settings" || path.startsWith("/settings/");
}

/** Catalog pages the public desk, tour, and command list may show. */
export function publicCatalogPages(): Page[] {
  return PAGES.filter((page) => !isInviteSurface(page.path, page.label));
}

type GrantView = {
  access: "granted" | "locked";
  pages: { path: string; access: "granted" | "locked" }[];
};

/**
 * An invite page the caller's access manifest grants, on a granted desk.
 * Only then does the desk draw it or name it. The static HTML never does.
 */
export function inviteGranted(desks: readonly GrantView[] | null | undefined, path: string): boolean {
  if (!desks) return false;
  return desks.some(
    (desk) => desk.access === "granted" && desk.pages.some((page) => page.path === path && page.access === "granted"),
  );
}

/** A desk the public rail and picker may name. Invite desks stay off this site. */
export function isPublicDeskChrome(desk: { id: string; label: string; blurb?: string; reason?: string }): boolean {
  if (desk.id === "fx") return false;
  return !INVITE.test(`${desk.label} ${desk.blurb ?? ""} ${desk.reason ?? ""}`);
}

/** Public desks, plus an invite desk once the manifest grants it to this caller. */
export function isVisibleDesk(desk: {
  id: string;
  label: string;
  blurb?: string;
  reason?: string;
  access: "granted" | "locked";
}): boolean {
  return isPublicDeskChrome(desk) || desk.access === "granted";
}
