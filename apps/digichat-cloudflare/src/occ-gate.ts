import { CONTAINER_BASE_PATH } from "./base-path";

/**
 * DIG-1210 / DIG-3585: /chat/occ is invite-only. It is the app's own embed
 * route, gated at the edge; nothing is served without a valid invite — no
 * title, branding or loader. Anything else gets the site's ordinary 404 page
 * with a real 404 status.
 *
 * A valid `?token=` also sets the tab-session cookie from DIG-1437
 * (b9dd6c4b8). That cookie is the invite key itself (HttpOnly, SameSite=Strict,
 * Path=/chat/occ, no Max-Age), which is what the deployed gate stores. A reload
 * without `?token=` presents the cookie instead of the query.
 *
 * There is deliberately ONE gate and ONE secret: the Worker validates, sets the
 * cookie, and proxies to the container it already serves `/chat` from. The
 * container is never asked for an uninvited request, and the Pages project is
 * not in the OCC path at all (2026-10-27 consolidation).
 */
export function isOccShellPath(pathname: string): boolean {
  return pathname === "/chat/occ" || pathname.startsWith("/chat/occ/");
}

/** Constant-time string compare (length leak only). */
export function inviteTokenValid(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}

/** Session cookie set once a valid invite link is opened (DIG-1437). */
export const OCC_INVITE_COOKIE = "occ_invite";

export function occInviteCookieHeader(expected: string): string {
  return `${OCC_INVITE_COOKIE}=${encodeURIComponent(expected)}; Path=/chat/occ; Secure; HttpOnly; SameSite=Strict`;
}

export function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() === name) {
      try {
        return decodeURIComponent(part.slice(i + 1).trim());
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** A path Pages does not have, so its ordinary 404 page comes back. */
export const SITE_NOT_FOUND_PATH = "/__not-found__";

export function inviteAccepted(
  request: Request,
  expected: string | undefined,
): "token" | "cookie" | null {
  const url = new URL(request.url);
  if (inviteTokenValid(url.searchParams.get("token"), expected)) return "token";
  if (inviteTokenValid(readCookie(request.headers.get("cookie"), OCC_INVITE_COOKIE), expected)) {
    return "cookie";
  }
  return null;
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
  return containerRequest;
}

export async function occGate(
  request: Request,
  expected: string | undefined,
  containerUpstream: (req: Request) => Promise<Response> = fetch,
  siteUpstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response> {
  const url = new URL(request.url);
  const accepted = inviteAccepted(request, expected);
  if (accepted === "token" && expected) {
    // DIG-1437: the key must not stay in the address bar or in browser
    // history. Set the session cookie and bounce to the same URL without
    // `token`, so the browser re-requests with the cookie and the key is gone
    // from the glass. The Pages shell used to do this from the client
    // (`stripInviteTokenFromUrl` + replaceState); after the 2026-10-27
    // consolidation the edge owns it, which also keeps the key out of the
    // container request entirely and works with scripting disabled.
    const clean = new URL(request.url);
    clean.searchParams.delete("token");
    const headers = new Headers({ location: clean.toString(), "cache-control": "no-store" });
    headers.append("set-cookie", occInviteCookieHeader(expected));
    return new Response(null, { status: 302, headers });
  }
  if (accepted === "cookie" && expected) {
    const res = await containerUpstream(occContainerRequest(request, expected));
    const headers = new Headers(res.headers);
    headers.set("cache-control", "no-store");
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
