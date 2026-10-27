import { CONTAINER_BASE_PATH } from "./base-path";
import { constantTimeEqual } from "./constant-time";

/**
 * DIG-1210 / DIG-3585: /chat/occ is invite-only. It is the app's own embed
 * route, gated at the edge; nothing is served without a valid invite — no
 * title, branding or loader. Anything else gets the site's ordinary 404 page
 * with a real 404 status.
 *
 * A valid `?token=` also sets the tab-session cookie from DIG-1437
 * (b9dd6c4b8). The cookie holds an issued-at time and an HMAC over it keyed
 * with the invite key (see {@link occInviteCookieValue}), never the key itself
 * (HttpOnly, Secure, SameSite=Strict, Path=/chat, no Max-Age attribute: the
 * browser drops it with the session, and the edge refuses it once it is older
 * than `OCC_INVITE_MAX_AGE_DAYS`, default 30). A reload without `?token=`
 * presents the cookie instead of the query; reopening the link renews it.
 *
 * Path=/chat, not /chat/occ: the page is only half of the chat. Its API calls
 * (`/chat/api/embed/tenant-config`, every `/chat/api/chat` turn) need the
 * invite too, and after the 302 strips `?token=` the browser has no other copy
 * of it. The cookie reaches the edge on those calls and the edge turns it into
 * the app's own transport ({@link bindOccApiCall}); it is removed from every
 * request the container sees ({@link withoutInviteCookie}).
 *
 * There is deliberately ONE gate and ONE secret: the Worker validates, sets the
 * cookie, and proxies to the container it already serves `/chat` from. The
 * container is never asked for an uninvited request, and the Pages project is
 * not in the OCC path at all (2026-10-27 consolidation).
 */
/** The OCC page's public path, without the trailing slash. */
export const OCC_PAGE_PATH = "/chat/occ";

export function isOccShellPath(pathname: string): boolean {
  return pathname === OCC_PAGE_PATH || pathname.startsWith(`${OCC_PAGE_PATH}/`);
}

/** Constant-time string compare (length leak only); false when either side is empty. */
export function inviteTokenValid(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  return constantTimeEqual(given, expected);
}

/** Session cookie set once a valid invite link is opened (DIG-1437). */
export const OCC_INVITE_COOKIE = "occ_invite";

/** The cookie's scope: the whole app, so its API calls carry the invite too. */
export const OCC_INVITE_COOKIE_PATH = CONTAINER_BASE_PATH;

/** The scope the first edge gate used; retired, see {@link occLegacyCookieClear}. */
export const OCC_LEGACY_COOKIE_PATH = `${CONTAINER_BASE_PATH}/occ`;

/**
 * Domain-separation label for the cookie MAC. Bumping it retires every cookie;
 * v1 (a MAC over the label alone, no issued-at) was retired this way.
 */
const OCC_COOKIE_LABEL = "digichat/occ_invite/v2";

/** The version prefix of a cookie value: `v2.<issued-at>.<mac>`. */
const OCC_COOKIE_VERSION = "v2";

/** Default cookie lifetime when `OCC_INVITE_MAX_AGE_DAYS` is unset or invalid. */
export const OCC_INVITE_DEFAULT_MAX_AGE_DAYS = 30;

/** Upper bound on a configured lifetime: a typo must not mean "forever". */
export const OCC_INVITE_MAX_MAX_AGE_DAYS = 365;

/** Clock skew tolerated for an issued-at in the future (edge clocks differ). */
const OCC_COOKIE_FUTURE_SKEW_S = 300;

/**
 * How old an `occ_invite` cookie may be. `nowMs` is a test seam; the gate uses
 * the clock.
 */
export interface OccCookiePolicy {
  maxAgeSeconds: number;
  nowMs?: number;
}

/**
 * The cookie lifetime in seconds from the non-secret `OCC_INVITE_MAX_AGE_DAYS`
 * var: a whole number of days from 1 to {@link OCC_INVITE_MAX_MAX_AGE_DAYS}.
 * Unset, malformed, zero or negative falls back to the 30-day default; a larger
 * value is capped. Never unlimited.
 */
export function occInviteMaxAgeSeconds(raw: string | undefined | null): number {
  const text = (raw ?? "").trim();
  const days = /^\d{1,4}$/.test(text) ? Number(text) : NaN;
  const valid = Number.isInteger(days) && days >= 1;
  const capped = valid ? Math.min(days, OCC_INVITE_MAX_MAX_AGE_DAYS) : OCC_INVITE_DEFAULT_MAX_AGE_DAYS;
  return capped * 24 * 60 * 60;
}

/** The default policy: 30 days, the clock. */
export const DEFAULT_OCC_COOKIE_POLICY: OccCookiePolicy = {
  maxAgeSeconds: OCC_INVITE_DEFAULT_MAX_AGE_DAYS * 24 * 60 * 60,
};

function nowSeconds(policy: OccCookiePolicy): number {
  return Math.floor((policy.nowMs ?? Date.now()) / 1000);
}

function base64Url(bytes: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(bytes)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function cookieMac(expected: string, issuedAtS: number): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(expected),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const msg = enc.encode(`${OCC_COOKIE_LABEL}|${issuedAtS}`);
  return base64Url(await crypto.subtle.sign("HMAC", key, msg));
}

/**
 * The `occ_invite` cookie value: `v2.<issued-at>.<mac>`, where the MAC is
 * HMAC-SHA256 keyed with the invite key over the label and the issued-at
 * (unix seconds). The cookie proves the browser opened a valid invite link at
 * that time, without carrying the key: a leaked cookie is not the key, does
 * not work as `?token=`, stops working after the max age, and dies when the
 * key is rotated. Changing the issued-at breaks the MAC.
 */
export async function occInviteCookieValue(
  expected: string,
  issuedAtS: number = Math.floor(Date.now() / 1000),
): Promise<string> {
  const iat = Math.floor(issuedAtS);
  return `${OCC_COOKIE_VERSION}.${iat}.${await cookieMac(expected, iat)}`;
}

/**
 * The issued-at of a valid cookie value, or null. Valid means: the v2 shape,
 * a MAC that matches under this key (constant-time compare), an issued-at no
 * older than the policy's max age, and not in the future beyond a small skew.
 */
export async function occInviteCookieIssuedAt(
  value: string,
  expected: string,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<number | null> {
  const parts = value.split(".");
  if (parts.length !== 3 || parts[0] !== OCC_COOKIE_VERSION) return null;
  const [, iatText, mac] = parts as [string, string, string];
  if (!/^\d{1,12}$/.test(iatText) || !mac) return null;
  const iat = Number(iatText);
  const macOk = constantTimeEqual(mac, await cookieMac(expected, iat));
  const now = nowSeconds(policy);
  const fresh = iat <= now + OCC_COOKIE_FUTURE_SKEW_S && now - iat <= policy.maxAgeSeconds;
  return macOk && fresh ? iat : null;
}

/** The `Set-Cookie` value; `cookieValue` comes from {@link occInviteCookieValue}. */
export function occInviteCookieHeader(cookieValue: string): string {
  return `${OCC_INVITE_COOKIE}=${encodeURIComponent(cookieValue)}; Path=${OCC_INVITE_COOKIE_PATH}; Secure; HttpOnly; SameSite=Strict`;
}

/**
 * Expires a cookie an earlier gate scoped to /chat/occ. A browser that still
 * holds one would paint the page and then send every API call without the
 * invite, because that cookie never reaches /chat/api/*.
 */
export function occLegacyCookieClear(): string {
  return `${OCC_INVITE_COOKIE}=; Path=${OCC_LEGACY_COOKIE_PATH}; Max-Age=0; Secure; HttpOnly; SameSite=Strict`;
}

/** Every value of `name` in a Cookie header (a browser may send one per path). */
export function readCookies(header: string | null, name: string): string[] {
  if (!header) return [];
  const values: string[] = [];
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() !== name) continue;
    try {
      values.push(decodeURIComponent(part.slice(i + 1).trim()));
    } catch {
      /* a malformed value is not an invite */
    }
  }
  return values;
}

export function readCookie(header: string | null, name: string): string | null {
  return readCookies(header, name)[0] ?? null;
}

/**
 * The newest valid `occ_invite` value in the Cookie header (see
 * {@link occInviteCookieIssuedAt}), or null. Every value is checked, so the
 * time taken does not depend on which one is valid. Expired, tampered,
 * old-format and raw-key cookies are all null.
 */
export async function validInviteCookie(
  header: string | null,
  expected: string | undefined,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<string | null> {
  const key = expected?.trim();
  if (!key) return null;
  let best: { value: string; iat: number } | null = null;
  for (const value of readCookies(header, OCC_INVITE_COOKIE)) {
    const iat = await occInviteCookieIssuedAt(value, key, policy);
    if (iat !== null && (best === null || iat > best.iat)) best = { value, iat };
  }
  return best?.value ?? null;
}

/** True when the Cookie header carries a valid `occ_invite` (see {@link validInviteCookie}). */
export async function inviteCookieValid(
  header: string | null,
  expected: string | undefined,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<boolean> {
  return (await validInviteCookie(header, expected, policy)) !== null;
}

/**
 * The Cookie header without `occ_invite`. The cookie is derived from the invite
 * key; the edge is the only place that needs it, so it never reaches the container
 * (its logs, its request objects, the app's own cookie parsing).
 */
export function withoutInviteCookie(headers: Headers): void {
  const raw = headers.get("cookie");
  if (raw === null) return;
  const kept = raw
    .split(";")
    .filter((part) => {
      const i = part.indexOf("=");
      const name = (i < 0 ? part : part.slice(0, i)).trim();
      return name !== OCC_INVITE_COOKIE;
    })
    .map((part) => part.trim())
    .filter(Boolean);
  if (kept.length) headers.set("cookie", kept.join("; "));
  else headers.delete("cookie");
}

/** A path Pages does not have, so its ordinary 404 page comes back. */
export const SITE_NOT_FOUND_PATH = "/__not-found__";

/** The proof a request carries: a valid `?token=`, or a valid cookie (its value). */
export type InviteProof = { kind: "token" } | { kind: "cookie"; value: string };

/**
 * Which proof this request carries. The query token and the key are trimmed
 * the same way the container and the /embed gate trim them, so a link pasted
 * with a trailing space or newline still opens.
 */
export async function inviteAccepted(
  request: Request,
  expected: string | undefined,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<InviteProof | null> {
  const key = expected?.trim();
  if (!key) return null;
  const url = new URL(request.url);
  if (inviteTokenValid(url.searchParams.get("token")?.trim() || null, key)) return { kind: "token" };
  const value = await validInviteCookie(request.headers.get("cookie"), key, policy);
  return value === null ? null : { kind: "cookie", value };
}

/** The tenant host the OCC embed resolves for this shell. */
export const OCC_EMBED_HOST = "occ.digithings.ai";

/** The app route that renders the embed shell under the container base path. */
export const OCC_CONTAINER_PATH = `${CONTAINER_BASE_PATH}/embed`;

/**
 * The header the app already uses for the per-tenant embed secret
 * (`apps/digichat/src/lib/embed-token-transport.ts`). The edge puts the key
 * here and removes it from the URL, so the token never reaches the container
 * request line, the HTML, or the App Router flight payload.
 */
export const EMBED_TOKEN_HEADER = "x-embed-token";

/** The app's tenant-selection header (`embedHostOf` in digichat). */
export const EMBED_HOST_HEADER = "x-embed-host";

/**
 * The backend tenant header. The app sets it server-side on its upstream call
 * to digigraph; a browser has no business sending it, so the edge drops it.
 */
export const DIGI_TENANT_HEADER = "x-digi-tenant";

/**
 * The referrer policy on the OCC page. `same-origin` keeps the full Referer on
 * the page's own API calls — which is how the edge tells an OCC call from a
 * house one — and sends none at all to another origin.
 */
export const OCC_REFERRER_POLICY = "same-origin";

/**
 * The request the Container serves for a valid invite.
 *
 * `/chat/occ` is the app's own embed route, not a Pages shell: the path is
 * rewritten to the base-path embed surface, the tenant host is set, the
 * invite is moved from the query to `x-embed-token`, and the query token is
 * dropped. The response is the chat itself — there is no iframe and no second
 * origin in the chain.
 */
export function occContainerRequest(request: Request, invite: string): Request {
  const target = new URL(request.url);
  target.pathname = OCC_CONTAINER_PATH;
  target.searchParams.set("host", OCC_EMBED_HOST);
  target.searchParams.delete("token");
  const containerRequest = new Request(target.toString(), request);
  // Overwrite rather than append: a client-supplied header must never be
  // able to stand in for the edge's own verdict.
  containerRequest.headers.set(EMBED_TOKEN_HEADER, invite);
  containerRequest.headers.set(EMBED_HOST_HEADER, OCC_EMBED_HOST);
  containerRequest.headers.delete(DIGI_TENANT_HEADER);
  withoutInviteCookie(containerRequest.headers);
  return containerRequest;
}

/** The app's API under its base path: what the OCC page calls after it paints. */
export function isChatApiPath(pathname: string): boolean {
  return pathname.startsWith(`${CONTAINER_BASE_PATH}/api/`);
}

/**
 * True when the call says it comes from the OCC page itself: a same-origin
 * Referer whose path is /chat/occ, plus, when the browser sends them,
 * `Sec-Fetch-Site: same-origin` and an `Origin` equal to ours.
 *
 * What this does and does not prove:
 * - A cross-site page cannot pass: its Referer and Origin name its own
 *   origin, its Sec-Fetch-Site is `cross-site`, and the cookie is
 *   SameSite=Strict, so it never carries the invite anyway.
 * - Script on OUR origin can pass. Referer is a forbidden header name, but
 *   `fetch(url, { referrer: "/chat/occ" })` may set any same-origin referrer.
 *   So this check only tells an OCC call apart from a house call made by the
 *   app's own code. It is not a security boundary against same-origin script.
 *   The boundary is the HttpOnly invite cookie, which only a browser that
 *   opened a valid invite link holds.
 * - A non-browser caller can send any header. Without the cookie it gets
 *   nothing from this.
 */
export function refererIsOccPage(request: Request): boolean {
  const raw = request.headers.get("referer");
  if (!raw) return false;
  try {
    const self = new URL(request.url).origin;
    const ref = new URL(raw);
    if (ref.origin !== self || !isOccShellPath(ref.pathname)) return false;
    const site = request.headers.get("sec-fetch-site");
    if (site !== null && site.trim().toLowerCase() !== "same-origin") return false;
    const origin = request.headers.get("origin");
    if (origin !== null && origin.trim() !== self) return false;
    return true;
  } catch {
    return false;
  }
}

/**
 * Binds an OCC page's API call (`/chat/api/*`) to the invite, in place, on the
 * request the container is about to receive.
 *
 * - `X-Digi-Tenant` is always dropped: only the app sets it, server-side.
 * - From the OCC page, the client's own `x-embed-token` / `X-Embed-Host` are
 *   always dropped. The edge alone decides whether this call is OCC: when the
 *   `occ_invite` cookie is valid it sets the invite as `x-embed-token` and the
 *   host as `occ.digithings.ai`; otherwise the call goes on with neither, and
 *   the app answers it as an unverified caller (house defaults or refused).
 * - From anywhere else (the house chat, a customer's embed) the tenant headers
 *   are the caller's own and pass through: a cookie never makes a house call
 *   OCC, and other tenants keep their token transport.
 * - The `occ_invite` cookie itself never reaches the container.
 *
 * `request` must be the edge's own copy (its headers are mutable); the
 * Referer and Cookie are read from it before anything is removed.
 */
export async function bindOccApiCall(
  request: Request,
  expected: string | undefined,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<void> {
  const key = expected?.trim();
  const fromOccPage = refererIsOccPage(request);
  const invited =
    fromOccPage &&
    Boolean(key) &&
    (await inviteCookieValid(request.headers.get("cookie"), key, policy));
  const headers = request.headers;
  headers.delete(DIGI_TENANT_HEADER);
  if (fromOccPage) {
    headers.delete(EMBED_TOKEN_HEADER);
    headers.delete(EMBED_HOST_HEADER);
    if (invited && key) {
      headers.set(EMBED_TOKEN_HEADER, key);
      headers.set(EMBED_HOST_HEADER, OCC_EMBED_HOST);
    }
  }
  withoutInviteCookie(headers);
}

export async function occGate(
  request: Request,
  expected: string | undefined,
  containerUpstream: (req: Request) => Promise<Response> = fetch,
  siteUpstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
  policy: OccCookiePolicy = DEFAULT_OCC_COOKIE_POLICY,
): Promise<Response> {
  const url = new URL(request.url);
  const key = expected?.trim();
  const accepted = await inviteAccepted(request, key, policy);
  if (accepted?.kind === "token" && key) {
    // DIG-1437: the key must not stay in the address bar or in browser
    // history. Set the session cookie and bounce to the same URL without
    // `token`, so the browser re-requests with the cookie and the key is gone
    // from the glass. The Pages shell used to do this from the client
    // (`stripInviteTokenFromUrl` + replaceState); after the 2026-10-27
    // consolidation the edge owns it, which also keeps the key out of the
    // container request entirely and works with scripting disabled.
    // A token hit always issues a FRESH cookie (new issued-at): reopening the
    // link is how a visitor renews an expired session.
    // The bare `/chat/occ?token=` link lands on `/chat/occ/`, the same clean
    // address as `/chat/occ/?token=`: one canonical URL, no key in it, and no
    // second hop for a trailing-slash redirect after the cookie is set.
    const clean = new URL(request.url);
    clean.searchParams.delete("token");
    if (clean.pathname === OCC_PAGE_PATH) clean.pathname = `${OCC_PAGE_PATH}/`;
    const headers = new Headers({
      location: clean.toString(),
      "cache-control": "no-store",
      "referrer-policy": OCC_REFERRER_POLICY,
    });
    const issuedAt = nowSeconds(policy);
    headers.append("set-cookie", occInviteCookieHeader(await occInviteCookieValue(key, issuedAt)));
    headers.append("set-cookie", occLegacyCookieClear());
    return new Response(null, { status: 302, headers });
  }
  if (accepted?.kind === "cookie" && key) {
    const res = await containerUpstream(occContainerRequest(request, key));
    const headers = new Headers(res.headers);
    headers.set("cache-control", "no-store");
    headers.set("referrer-policy", OCC_REFERRER_POLICY);
    // A browser that still holds a /chat/occ-scoped cookie from an earlier gate
    // gets it moved to /chat here, so its API calls carry the invite too. The
    // SAME value is re-set (same issued-at): a cookie hit never extends the
    // session, only a fresh `?token=` hit does.
    headers.append("set-cookie", occInviteCookieHeader(accepted.value));
    headers.append("set-cookie", occLegacyCookieClear());
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }
  // The 404 is the site's own page, never the container's: it goes to the
  // site upstream even when the caller handed us a container for the shell.
  return siteNotFound(url.origin, siteUpstream);
}

/**
 * The site's ordinary 404, passed through untouched: same status, body and
 * headers as a path the site does not have (/xyz). Nothing extra (not even
 * cache-control) may mark a gated address as special.
 */
export async function siteNotFound(
  origin: string,
  upstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response> {
  const nf = await upstream(`${origin}${SITE_NOT_FOUND_PATH}`, {
    headers: { accept: "text/html" },
  });
  if (nf.status === 404) {
    return new Response(nf.body, { status: 404, statusText: nf.statusText, headers: nf.headers });
  }
  // Same as the Pages twin: anything but the site's own 404 is not passed through.
  return new Response("Not Found", { status: 404, headers: { "content-type": "text/plain" } });
}

/** Invite-only embed tenants (mirrors digichat INVITE_ONLY_EMBED_HOSTS). */
export const INVITE_ONLY_EMBED_HOSTS: ReadonlySet<string> = new Set(["occ.digithings.ai"]);

/** Same normalisation as digichat `normalizeEmbedHost`. */
function embedHostOf(raw: string | null): string | null {
  const v = (raw ?? "").trim().toLowerCase();
  if (!v) return null;
  if (v.includes("://")) {
    try {
      return new URL(v).hostname.replace(/\.$/, "") || null;
    } catch {
      return null;
    }
  }
  return v.split("/")[0]!.split(":")[0]!.replace(/\.$/, "") || null;
}

/**
 * The public paths that render the embed shell.
 *
 * DIG-5121 moved the app under the base path, so the embed surface has two
 * spellings: the compatibility route (/embed) and the base-path route
 * (/chat/embed) — the same shell, served by the same component
 * (apps/digichat/src/app/(digichat)/embed-route-shell.tsx). The app root also
 * answers the embed shell when it asks for it with ?mode=embed
 * (/chat/?mode=embed).
 */
function isEmbedSurfacePath(url: URL): boolean {
  const path = url.pathname;
  if (path === "/embed" || path.startsWith("/embed/")) return true;
  const embed = `${CONTAINER_BASE_PATH}/embed`;
  if (path === embed || path.startsWith(`${embed}/`)) return true;
  if (url.searchParams.get("mode") !== "embed") return false;
  return path === CONTAINER_BASE_PATH || path === `${CONTAINER_BASE_PATH}/`;
}

/**
 * An embed request asking for an invite-only tenant. The tenant host is the
 * one the container resolves: `?host=` when it is non-empty, else the
 * Referer origin (`resolveEmbedHostParamOrReferer` in digichat).
 */
export function isInviteOnlyEmbedRequest(url: URL, referer: string | null = null): boolean {
  if (!isEmbedSurfacePath(url)) return false;
  const explicit = url.searchParams.get("host")?.trim();
  const host = embedHostOf(explicit ? explicit : referer);
  return host !== null && INVITE_ONLY_EMBED_HOSTS.has(host);
}

/**
 * The /embed form of an invite-only tenant without its key answers the site
 * 404, exactly like /chat/occ and like any nonexistent path — never the
 * container's own error page. Null means "invited, proxy as usual".
 */
export async function occEmbedGate(
  request: Request,
  expected: string | undefined,
  upstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response | null> {
  const url = new URL(request.url);
  if (!isInviteOnlyEmbedRequest(url, request.headers.get("referer"))) return null;
  // Trimmed like the container and the parent page do. The gate reads the
  // query only: no browser path sends the x-embed-token header to /embed.
  // With the Worker secret unset, the embed fails closed here.
  if (inviteTokenValid(url.searchParams.get("token")?.trim() || null, expected?.trim()))
    return null;
  return siteNotFound(url.origin, upstream);
}
