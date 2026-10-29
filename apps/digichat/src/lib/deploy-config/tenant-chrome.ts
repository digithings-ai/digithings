/**
 * Tenant chat chrome: the path a tenant chat lives on, whether it is a product
 * chat, and its server-only access block (client-repos epic, Phase 2 U5a).
 *
 * The tenant document stores only the chat slug (`chrome.slug`); there is
 * no stored path. R0 builds the path: a tenant chat is always
 * `/chat/<slug>` (`tenantChatPath`). The Worker gate (U1) and digithings-web
 * (U5d) read the same slug, so the validator and the classifier below are the
 * single definition. The tenant writer must call `validateTenantChatSlug`
 * with every other tenant's slug before it stores a document.
 *
 * Fail closed: a path that is claimed by a gated tenant stays gated when its
 * document is missing, unreadable, or fails the schema. The claim comes from
 * a small R0-side list (`gatedTenantClaims`), not from the document, so the
 * absence of the document can never open the house default.
 */

import { z } from "zod";
import { LEGACY_GATED_TENANTS } from "./legacy-tenant-defaults";

/** Every tenant chat path is `/chat/<slug>`. */
export const TENANT_PATH_ROOT = "/chat";

/** Plain lowercase slug: alphanumeric runs joined by single hyphens. */
export const TENANT_PATH_SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/**
 * Segments a tenant slug may never take: the top-level routes of this app
 * (route groups stripped; a test walks `src/app` to keep the list
 * complete), the house chat surfaces, and the routes the public site
 * and the edge own next to `/chat`.
 */
export const HOUSE_ROUTE_SEGMENTS: ReadonlySet<string> = new Set([
  // src/app top-level segments
  "actions",
  "api",
  "baseline",
  "devkit",
  "embed",
  "healthz",
  // edge-owned prefixes (cannot match the slug rule, listed for the writer)
  "_dtchat",
  "_digichat",
  "_digichat-admin",
  // house chat + public site neighbours
  "chat",
  "dashboard",
  "tools",
  "health",
  "auth",
  "login",
  "logout",
  "signup",
  "settings",
  "admin",
  "private",
  "public",
  "static",
  "assets",
  "widget",
  "matrix",
  "stock",
  "new",
  "share",
  "c",
  // house tenant names
  "digithings",
  "digichat",
  "house",
  "www",
]);

/** `/chat/<slug>` for a validated slug. */
export function tenantChatPath(slug: string): string {
  return `${TENANT_PATH_ROOT}/${slug}`;
}

function segments(path: string): string[] {
  return path.split("/").filter(Boolean);
}

/**
 * The tenant chat slug a path sits under, or null: `/chat/example/x` →
 * `example`; `/chat`, `/chat/api` (a house route) and `/embed` → null.
 */
export function tenantChatSlugFromPath(pathname: string): string | null {
  const segs = segments(pathname);
  if (segs[0] !== segments(TENANT_PATH_ROOT)[0] || segs.length < 2) return null;
  const slug = segs[1] as string;
  if (!TENANT_PATH_SLUG.test(slug) || HOUSE_ROUTE_SEGMENTS.has(slug)) return null;
  return slug;
}

/**
 * True when one path is the other, or one sits under the other, compared by
 * whole segments: `/abc` and `/abcd` do not overlap; `/chat` and `/chat/x` do.
 */
export function pathsOverlap(a: string, b: string): boolean {
  const sa = segments(a);
  const sb = segments(b);
  const n = Math.min(sa.length, sb.length);
  for (let i = 0; i < n; i += 1) {
    if (sa[i] !== sb[i]) return false;
  }
  return true;
}

export type TenantChatSlugClaim = {
  /** The tenant (document `slug`) that owns the chat slug; its rows may share it. */
  tenant: string;
  chatSlug: string;
};

export type TenantChatSlugResult =
  | { ok: true; slug: string; path: string }
  | { ok: false; reason: "not-a-slug" | "house-route" | "collision"; detail: string };

/**
 * Validate a tenant's `chrome.slug`. Exported for the tenant writer: run it
 * with every other tenant's claim before storing a document. Returns the
 * built `/chat/<slug>` path with the slug.
 *
 * - plain lowercase slug (`TENANT_PATH_SLUG`);
 * - not a house route segment (the path would overlap a house route);
 * - the built path does not overlap another tenant's, compared by whole
 *   segments (a duplicate slug). Rows of the same tenant may share it.
 */
export function validateTenantChatSlug(
  chatSlug: string,
  options: { tenant?: string; others?: readonly TenantChatSlugClaim[] } = {},
): TenantChatSlugResult {
  if (typeof chatSlug !== "string" || !TENANT_PATH_SLUG.test(chatSlug)) {
    return {
      ok: false,
      reason: "not-a-slug",
      detail: "chrome.slug must be a plain lowercase slug (a-z, 0-9, single hyphens)",
    };
  }
  if (HOUSE_ROUTE_SEGMENTS.has(chatSlug)) {
    return {
      ok: false,
      reason: "house-route",
      detail: `chrome.slug "${chatSlug}" is a reserved house route`,
    };
  }
  const path = tenantChatPath(chatSlug);
  for (const other of options.others ?? []) {
    if (options.tenant && other.tenant === options.tenant) continue;
    if (!TENANT_PATH_SLUG.test(other.chatSlug)) continue;
    if (pathsOverlap(path, tenantChatPath(other.chatSlug))) {
      return {
        ok: false,
        reason: "collision",
        detail: `chrome.slug "${chatSlug}" is already used by tenant "${other.tenant}"`,
      };
    }
  }
  return { ok: true, slug: chatSlug, path };
}

/**
 * TODO(P-exit): one release only. A document written before `chrome.slug`
 * may still store the full path in `chrome.pathPrefix`. Its only accepted
 * shape is `/chat/<slug>`; it normalises to the slug, and when the slug is
 * also present the two must agree (fail closed otherwise).
 */
export function resolveTenantChatSlug(input: {
  slug?: unknown;
  pathPrefix?: unknown;
}): { ok: true; slug: string | undefined } | { ok: false; detail: string } {
  let fromPath: string | undefined;
  if (input.pathPrefix !== undefined) {
    const raw = input.pathPrefix;
    const segs = typeof raw === "string" ? raw.split("/") : [];
    // Exactly "", "chat", "<slug>": no trailing slash, no extra segment.
    const ok =
      typeof raw === "string" &&
      segs.length === 3 &&
      segs[0] === "" &&
      `/${segs[1]}` === TENANT_PATH_ROOT &&
      validateTenantChatSlug(segs[2] as string).ok;
    if (!ok) {
      return { ok: false, detail: "chrome.pathPrefix must be /chat/<slug> (legacy field)" };
    }
    fromPath = segs[2] as string;
  }
  if (input.slug !== undefined) {
    const result = validateTenantChatSlug(input.slug as string);
    if (!result.ok) return { ok: false, detail: result.detail };
    if (fromPath !== undefined && fromPath !== result.slug) {
      return { ok: false, detail: "chrome.slug and legacy chrome.pathPrefix disagree" };
    }
    return { ok: true, slug: result.slug };
  }
  return { ok: true, slug: fromPath };
}

/** Zod field for `chrome.slug` (slug + house-route rule; collisions are registry-level). */
export const TenantChatSlugSchema = z.string().superRefine((value, ctx) => {
  const result = validateTenantChatSlug(value);
  if (!result.ok) ctx.addIssue({ code: "custom", message: result.detail });
});

/**
 * Server-only access block. `access.invite` holds the invite settings (mode,
 * how the invite key is stored, cookie name, max age). PENDING: how the key
 * is stored (the secret's env name, or an HMAC of the key) is decided with
 * the Worker gate (U1), so only the cookie fields are typed and the rest
 * passes through untouched. It never reaches a browser: the client config is
 * built from an allowlist of display fields (`toEmbedClientConfig`).
 */
export const TenantInviteAccessSchema = z
  .object({
    cookieName: z
      .string()
      .regex(/^[a-z][a-z0-9_-]{0,63}$/, "cookieName must be a lowercase cookie name")
      .optional(),
    label: z.string().min(1).max(120).optional(),
    maxAgeDays: z.number().int().positive().max(400).optional(),
  })
  .passthrough();

export const TenantAccessSchema = z
  .object({ invite: TenantInviteAccessSchema.optional() })
  .strict();

export type TenantAccess = z.infer<typeof TenantAccessSchema>;

/** The fields of a tenant document the path classifier reads. */
export type TenantChromeDoc = {
  slug: string;
  host?: string;
  /** `chrome.slug`. */
  chatSlug?: string;
  gated: boolean;
};

/** A gated claim, recorded outside the document. */
export type GatedTenantClaim = { slug: string; chatSlug: string; host?: string };

/** The key `gatedTenantClaims` dedupes on. */
function claimKey(claim: GatedTenantClaim): string {
  return `${claim.chatSlug}|${claim.host ?? ""}`;
}

/**
 * Append `claims` to `into`, skipping any key already present. The result is
 * frozen at runtime, array and every claim (a frozen copy, so the caller's
 * objects are left alone): the cached list is shared by every caller, so no
 * caller can add, drop or rewrite a gated claim.
 */
function mergeClaims(
  into: readonly Readonly<GatedTenantClaim>[],
  claims: readonly Readonly<GatedTenantClaim>[],
): readonly Readonly<GatedTenantClaim>[] {
  const out: Readonly<GatedTenantClaim>[] = [...into];
  const seen = new Set(out.map(claimKey));
  for (const claim of claims) {
    const key = claimKey(claim);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(Object.isFrozen(claim) ? claim : Object.freeze({ ...claim }));
  }
  return Object.freeze(out);
}

/** Last-good claims, deduped on write, so repeated loads cannot grow it. Frozen. */
let lastGoodGatedClaims: readonly Readonly<GatedTenantClaim>[] = Object.freeze([]);
/** Legacy seed + last-good claims, rebuilt only when the last-good list changes. */
let gatedClaimsView: readonly Readonly<GatedTenantClaim>[] = mergeClaims([], LEGACY_GATED_TENANTS);

/**
 * Record the gated tenants of every registry that parsed cleanly, so a later
 * missing, empty or unreadable registry still keeps them gated. Claims only
 * accumulate (process-local): a doc that disappears is indistinguishable from
 * a doc that failed to load, so un-gating a tenant needs a restart. Each claim
 * is stored once per `chatSlug|host`, so loading the same registry again adds
 * nothing. Persistence across restarts is U1's.
 */
export function rememberGatedTenantDocs(docs: readonly TenantChromeDoc[]): void {
  const next = docs
    .filter((d) => d.gated && (d.chatSlug || d.host))
    .map((d) => ({ slug: d.slug, chatSlug: d.chatSlug ?? "", host: d.host }));
  const merged = mergeClaims(lastGoodGatedClaims, next);
  if (merged.length === lastGoodGatedClaims.length) return;
  lastGoodGatedClaims = merged;
  gatedClaimsView = mergeClaims(mergeClaims([], LEGACY_GATED_TENANTS), lastGoodGatedClaims);
}

/** Test-only reset of the last-good cache. */
export function resetGatedTenantCacheForTests(): void {
  lastGoodGatedClaims = Object.freeze([]);
  gatedClaimsView = mergeClaims([], LEGACY_GATED_TENANTS);
}

/** Test-only: how many claims the last-good cache holds. */
export function lastGoodGatedClaimCountForTests(): number {
  return lastGoodGatedClaims.length;
}

/**
 * The R0-side list of gated claims: the legacy seed plus the last good
 * registry, deduped by `chatSlug|host`. Independent of the current document,
 * by design. Cached: rebuilt only when a load adds a new claim.
 */
export function gatedTenantClaims(): readonly Readonly<GatedTenantClaim>[] {
  return gatedClaimsView;
}

/** True when `host` belongs to a gated claim (legacy seed or last good doc). */
export function isClaimedGatedHost(host: string | null | undefined): boolean {
  if (!host) return false;
  const h = host.trim().toLowerCase();
  return gatedTenantClaims().some((c) => c.host === h);
}

export type TenantPathClass =
  | { kind: "house" }
  | { kind: "tenant"; slug: string; gated: boolean }
  /** A tenant path whose document could not be trusted. Serve private / deny. */
  | { kind: "gated-unknown"; chatSlug: string };

/**
 * Classify a request path. `docs` is the parsed registry, or `null` when it
 * was missing or unreadable. Fail closed:
 * - a claimed gated path stays gated whatever the document says;
 * - a `/chat/<slug>` path with no valid document is `gated-unknown`, never
 *   the open house default.
 */
export function classifyTenantChatPath(
  pathname: string,
  docs: readonly TenantChromeDoc[] | null,
): TenantPathClass {
  const segs = segments(pathname);
  if (segs[0] !== segments(TENANT_PATH_ROOT)[0] || segs.length < 2) {
    return { kind: "house" };
  }
  const candidate = segs[1] as string;
  if (HOUSE_ROUTE_SEGMENTS.has(candidate)) return { kind: "house" };
  const claimed = gatedTenantClaims().find((c) => c.chatSlug === candidate);
  const doc = docs?.find((d) => d.chatSlug === candidate);
  if (claimed) {
    return doc
      ? { kind: "tenant", slug: doc.slug, gated: true }
      : { kind: "gated-unknown", chatSlug: candidate };
  }
  // Not a valid slug, or no valid document: never the open house default.
  if (!doc) return { kind: "gated-unknown", chatSlug: candidate };
  return { kind: "tenant", slug: doc.slug, gated: doc.gated };
}
