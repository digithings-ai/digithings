/**
 * digiweb's route inventory.
 *
 * This is the machine-readable form of the IA: every route declared once, and
 * `lib/routes.test.ts` walks `app/` to prove the list matches the filesystem,
 * so a moved page cannot drift silently. `lib/nav.test.ts` proves every route
 * is reachable from the top bar.
 */

export type RouteEntry = {
  /** The URL as served (no trailing slash). */
  route: string;
  /** The page family the route belongs to. */
  group: string;
  /** Repo-relative path to the route's `page.tsx`. */
  page: string;
};

export const ROUTES: readonly RouteEntry[] = [
  { route: "/", group: "reference", page: "app/page.tsx" },
  { route: "/foundations", group: "foundations", page: "app/foundations/page.tsx" },
  { route: "/components", group: "components", page: "app/components/page.tsx" },
  { route: "/rtl", group: "rtl", page: "app/rtl/page.tsx" },
  { route: "/brand", group: "brand", page: "app/brand/page.tsx" },
] as const;
