/**
 * DIG-1210 / DIG-3585: /chat/occ is invite-only. The Pages shell must never be
 * served without a valid invite — no title, branding or loader. Anything else
 * gets the site's ordinary 404 page with a real 404 status.
 *
 * A valid `?token=` also sets the tab-session cookie from DIG-1437
 * (b9dd6c4b8). That cookie is the invite key itself (HttpOnly, SameSite=Strict,
 * Path=/chat/occ, no Max-Age), which is what the deployed gate stores. A reload
 * after the page strips `?token=` presents the cookie instead of the query.
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

export async function occGate(
  request: Request,
  expected: string | undefined,
  upstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response> {
  const url = new URL(request.url);
  const accepted = inviteAccepted(request, expected);
  if (accepted && expected) {
    const res = await upstream(request);
    const headers = new Headers(res.headers);
    headers.set("cache-control", "no-store");
    if (accepted === "token") {
      headers.append("set-cookie", occInviteCookieHeader(expected));
    }
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }
  return siteNotFound(url.origin, upstream);
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
  return new Response(nf.body, { status: 404, statusText: nf.statusText, headers: nf.headers });
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

/** /embed (or /embed/*) asking for an invite-only tenant via ?host=. */
export function isInviteOnlyEmbedRequest(url: URL): boolean {
  if (url.pathname !== "/embed" && !url.pathname.startsWith("/embed/")) return false;
  const host = embedHostOf(url.searchParams.get("host"));
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
  if (!isInviteOnlyEmbedRequest(url)) return null;
  if (inviteTokenValid(url.searchParams.get("token"), expected)) return null;
  return siteNotFound(url.origin, upstream);
}
