import { CONTAINER_BASE_PATH } from "./base-path";
import { constantTimeEqual } from "./constant-time";
import {
  DIGI_TENANT_HEADER,
  EMBED_HOST_HEADER,
  EMBED_TOKEN_HEADER,
  OCC_INVITE_COOKIE,
  OCC_PAGE_PATH,
  OCC_REFERRER_POLICY,
  type OccCookiePolicy,
  embedHostOf,
  isEmbedSurfacePath,
  readCookies,
  siteNotFound,
} from "./occ-gate";

/**
 * Invite-only tenant pages beyond OCC, configured rather than hard-coded.
 *
 * OCC's gate (`occ-gate.ts`) is the model and stays exactly as it is. Every
 * other invite-only tenant is one entry of the NON-SECRET Worker var
 * `DIGICHAT_INVITE_PAGES`:
 *
 *   {"<slug>": {"host": "<tenant host>", "keyEnv": "<SECRET_NAME>"}}
 *
 * - `/chat/<slug>` is gated here exactly like `/chat/occ`: a valid `?token=`
 *   is traded for a `<slug>_invite` cookie (HttpOnly, Secure,
 *   SameSite=Strict, Path=/chat, `v2.<issued-at>.<mac>`), the browser is
 *   302'd to `/chat/<slug>/`, and a valid cookie is proxied to the app's
 *   `/chat/embed?host=<host>` with the key in `x-embed-token`. Anything else
 *   gets the site's own 404.
 * - `keyEnv` names the Worker secret holding the invite key. The value is
 *   read from the Worker env at request time and never forwarded except as
 *   the tenant's `x-embed-token`. A missing secret fails closed (404).
 * - The page's `/chat/api/*` calls are bound to the tenant only with a valid
 *   cookie and a same-origin Referer on that page (same rule as OCC).
 * - `/embed?host=<host>` without the key answers the site 404.
 *
 * The var is the record of which paths are gated, and it lives outside the
 * tenant document on purpose: a missing or unreadable tenant row cannot make
 * a gated path look open. An invalid entry is dropped and logged; the path it
 * named is then not served by this gate, and the app has no route there.
 */
export const INVITE_PAGES_VAR = "DIGICHAT_INVITE_PAGES";

export interface InvitePage {
  slug: string;
  /** `/chat/<slug>`, no trailing slash. */
  path: string;
  /** The tenant host the app resolves for this page. */
  host: string;
  /** Name of the Worker secret holding the invite key. */
  keyEnv: string;
  /** `<slug>_invite`. */
  cookie: string;
}

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const HOST_RE = /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
const ENV_NAME_RE = /^[A-Z][A-Z0-9_]*$/;

/**
 * First path segments under /chat the app or the edge already owns. A tenant
 * page can never take one of them.
 */
export const RESERVED_CHAT_SEGMENTS: ReadonlySet<string> = new Set([
  OCC_PAGE_PATH.slice(`${CONTAINER_BASE_PATH}/`.length),
  "embed",
  "api",
  "healthz",
  "devkit",
  "baseline",
  "stock",
  "actions",
  "auth",
  "_next",
  "_dtchat",
]);

/** Secrets an invite page may never name as its key. */
const FORBIDDEN_KEY_ENVS: ReadonlySet<string> = new Set([
  "AUTH_SECRET",
  "DIGICHAT_ADMIN_KEY",
  "DIGICHAT_EMBED_TENANTS",
  "DIGICHAT_MCP_EDGE_KEY",
  "DIGICHAT_MCP_IDENTITY_KEY",
  "DIGIKEY_BFF_TOKEN",
  "DIGICHAT_PLAN_PROOF_SECRET",
  "OCC_INVITE_KEY",
  "ZAMMAD_API_TOKEN",
  "ZAMMAD_EDGE_KEY",
]);

/** Parse `DIGICHAT_INVITE_PAGES`. Never throws; bad entries are dropped and logged. */
export function parseInvitePages(raw: string | undefined | null): InvitePage[] {
  const text = (raw ?? "").trim();
  if (!text) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    console.error(`[invite-pages] ${INVITE_PAGES_VAR} is not JSON; no configured invite pages`);
    return [];
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    console.error(`[invite-pages] ${INVITE_PAGES_VAR} must be an object keyed by slug`);
    return [];
  }
  const pages: InvitePage[] = [];
  const hosts = new Set<string>();
  const keys = new Set<string>();
  for (const [slug, value] of Object.entries(parsed as Record<string, unknown>)) {
    const v = (value ?? {}) as Record<string, unknown>;
    const host = typeof v.host === "string" ? v.host.trim().toLowerCase() : "";
    const keyEnv = typeof v.keyEnv === "string" ? v.keyEnv.trim() : "";
    const problem = !SLUG_RE.test(slug)
      ? "slug must be a lowercase slug"
      : RESERVED_CHAT_SEGMENTS.has(slug)
        ? "slug is a reserved /chat segment"
        : !HOST_RE.test(host)
          ? "host must be a lowercase hostname"
          : hosts.has(host)
            ? "host is already gated by another entry"
            : !ENV_NAME_RE.test(keyEnv) || FORBIDDEN_KEY_ENVS.has(keyEnv)
              ? "keyEnv must name a dedicated secret"
              : keys.has(keyEnv)
                ? "keyEnv is already used by another entry"
                : null;
    if (problem) {
      console.error(`[invite-pages] dropping entry "${slug}": ${problem}`);
      continue;
    }
    hosts.add(host);
    keys.add(keyEnv);
    pages.push({ slug, path: `${CONTAINER_BASE_PATH}/${slug}`, host, keyEnv, cookie: `${slug}_invite` });
  }
  return pages;
}

function onPagePath(page: InvitePage, pathname: string): boolean {
  return pathname === page.path || pathname.startsWith(`${page.path}/`);
}

export function invitePageFor(pages: readonly InvitePage[], pathname: string): InvitePage | null {
  return pages.find((p) => onPagePath(p, pathname)) ?? null;
}

/** The page's key from the Worker env, trimmed; undefined when unset (fail closed). */
export function invitePageKey(page: InvitePage, env: Record<string, unknown>): string | undefined {
  const v = env[page.keyEnv];
  return typeof v === "string" && v.trim() ? v.trim() : undefined;
}

const COOKIE_VERSION = "v2";
const FUTURE_SKEW_S = 300;

function base64Url(bytes: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(bytes)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function cookieMac(page: InvitePage, key: string, iat: number): Promise<string> {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
  return base64Url(await crypto.subtle.sign("HMAC", k, enc.encode(`digichat/${page.cookie}/v2|${iat}`)));
}

function nowSeconds(policy: OccCookiePolicy): number {
  return Math.floor((policy.nowMs ?? Date.now()) / 1000);
}

export async function invitePageCookieValue(page: InvitePage, key: string, iat: number): Promise<string> {
  const t = Math.floor(iat);
  return `${COOKIE_VERSION}.${t}.${await cookieMac(page, key, t)}`;
}

async function cookieIssuedAt(
  page: InvitePage,
  value: string,
  key: string,
  policy: OccCookiePolicy,
): Promise<number | null> {
  const parts = value.split(".");
  if (parts.length !== 3 || parts[0] !== COOKIE_VERSION) return null;
  const [, iatText, mac] = parts as [string, string, string];
  if (!/^\d{1,12}$/.test(iatText) || !mac) return null;
  const iat = Number(iatText);
  const macOk = constantTimeEqual(mac, await cookieMac(page, key, iat));
  const now = nowSeconds(policy);
  return macOk && iat <= now + FUTURE_SKEW_S && now - iat <= policy.maxAgeSeconds ? iat : null;
}

/** The newest valid cookie value for this page, or null. Every value is checked. */
export async function validInvitePageCookie(
  page: InvitePage,
  header: string | null,
  key: string | undefined,
  policy: OccCookiePolicy,
): Promise<string | null> {
  if (!key) return null;
  let best: { value: string; iat: number } | null = null;
  for (const value of readCookies(header, page.cookie)) {
    const iat = await cookieIssuedAt(page, value, key, policy);
    if (iat !== null && (best === null || iat > best.iat)) best = { value, iat };
  }
  return best?.value ?? null;
}

export function invitePageCookieHeader(page: InvitePage, value: string): string {
  return `${page.cookie}=${encodeURIComponent(value)}; Path=${CONTAINER_BASE_PATH}; Secure; HttpOnly; SameSite=Strict`;
}

/** Drops every invite cookie (OCC's and each configured page's) from the headers. */
export function withoutInvitePageCookies(headers: Headers, pages: readonly InvitePage[]): void {
  const raw = headers.get("cookie");
  if (raw === null) return;
  const names = new Set([OCC_INVITE_COOKIE, ...pages.map((p) => p.cookie)]);
  const kept = raw
    .split(";")
    .filter((part) => {
      const i = part.indexOf("=");
      return !names.has((i < 0 ? part : part.slice(0, i)).trim());
    })
    .map((part) => part.trim())
    .filter(Boolean);
  if (kept.length) headers.set("cookie", kept.join("; "));
  else headers.delete("cookie");
}

function containerRequestFor(page: InvitePage, request: Request, key: string, pages: readonly InvitePage[]): Request {
  const target = new URL(request.url);
  target.pathname = `${CONTAINER_BASE_PATH}/embed`;
  target.searchParams.set("host", page.host);
  target.searchParams.delete("token");
  const req = new Request(target.toString(), request);
  req.headers.set(EMBED_TOKEN_HEADER, key);
  req.headers.set(EMBED_HOST_HEADER, page.host);
  req.headers.delete(DIGI_TENANT_HEADER);
  withoutInvitePageCookies(req.headers, pages);
  return req;
}

/** `/chat/<slug>` for a configured page: same contract as `occGate`. */
export async function invitePageGate(
  page: InvitePage,
  pages: readonly InvitePage[],
  request: Request,
  key: string | undefined,
  containerUpstream: (req: Request) => Promise<Response>,
  siteUpstream: (req: Request | string, init?: RequestInit) => Promise<Response>,
  policy: OccCookiePolicy,
): Promise<Response> {
  const url = new URL(request.url);
  if (key) {
    const token = url.searchParams.get("token")?.trim() || null;
    if (token && constantTimeEqual(token, key)) {
      const clean = new URL(request.url);
      clean.searchParams.delete("token");
      if (clean.pathname === page.path) clean.pathname = `${page.path}/`;
      const headers = new Headers({
        location: clean.toString(),
        "cache-control": "no-store",
        "referrer-policy": OCC_REFERRER_POLICY,
      });
      headers.append(
        "set-cookie",
        invitePageCookieHeader(page, await invitePageCookieValue(page, key, nowSeconds(policy))),
      );
      return new Response(null, { status: 302, headers });
    }
    const value = await validInvitePageCookie(page, request.headers.get("cookie"), key, policy);
    if (value !== null) {
      const res = await containerUpstream(containerRequestFor(page, request, key, pages));
      const headers = new Headers(res.headers);
      headers.set("cache-control", "no-store");
      headers.set("referrer-policy", OCC_REFERRER_POLICY);
      headers.append("set-cookie", invitePageCookieHeader(page, value));
      return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
    }
  }
  return siteNotFound(url.origin, siteUpstream);
}

function refererPage(request: Request, pages: readonly InvitePage[]): InvitePage | null {
  const raw = request.headers.get("referer");
  if (!raw) return null;
  try {
    const self = new URL(request.url).origin;
    const ref = new URL(raw);
    if (ref.origin !== self) return null;
    const page = invitePageFor(pages, ref.pathname);
    if (!page) return null;
    const site = request.headers.get("sec-fetch-site");
    if (site !== null && site.trim().toLowerCase() !== "same-origin") return null;
    const origin = request.headers.get("origin");
    if (origin !== null && origin.trim() !== self) return null;
    return page;
  } catch {
    return null;
  }
}

/**
 * Binds a configured page's `/chat/api/*` call to its tenant, in place (same
 * rule as `bindOccApiCall`). From the page, the client's own tenant headers
 * are always dropped and set only with a valid cookie. Calls from anywhere
 * else are untouched here.
 */
export async function bindInvitePageApiCall(
  request: Request,
  pages: readonly InvitePage[],
  env: Record<string, unknown>,
  policy: OccCookiePolicy,
): Promise<void> {
  const page = refererPage(request, pages);
  if (!page) return;
  const key = invitePageKey(page, env);
  const invited = (await validInvitePageCookie(page, request.headers.get("cookie"), key, policy)) !== null;
  request.headers.delete(DIGI_TENANT_HEADER);
  request.headers.delete(EMBED_TOKEN_HEADER);
  request.headers.delete(EMBED_HOST_HEADER);
  if (invited && key) {
    request.headers.set(EMBED_TOKEN_HEADER, key);
    request.headers.set(EMBED_HOST_HEADER, page.host);
  }
}

/** `/embed?host=<configured host>` without its key: the site 404. Null means proxy as usual. */
export async function invitePageEmbedGate(
  request: Request,
  pages: readonly InvitePage[],
  env: Record<string, unknown>,
  upstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response | null> {
  const url = new URL(request.url);
  if (!isEmbedSurfacePath(url)) return null;
  const explicit = url.searchParams.get("host")?.trim();
  const host = embedHostOf(explicit ? explicit : request.headers.get("referer"));
  const page = host ? pages.find((p) => p.host === host) : undefined;
  if (!page) return null;
  const key = invitePageKey(page, env);
  const token = url.searchParams.get("token")?.trim() || null;
  if (key && token && constantTimeEqual(token, key)) return null;
  return siteNotFound(url.origin, upstream);
}
