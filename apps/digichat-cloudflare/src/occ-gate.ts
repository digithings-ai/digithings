/**
 * DIG-1210: /chat/occ is invite-only. The Pages shell must never be served
 * without a valid `?token=` — no title, branding or loader. Anything else
 * gets the site's ordinary 404 page with a real 404 status.
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

export async function occGate(
  request: Request,
  expected: string | undefined,
  upstream: (req: Request | string, init?: RequestInit) => Promise<Response> = fetch,
): Promise<Response> {
  const url = new URL(request.url);
  if (inviteTokenValid(url.searchParams.get("token"), expected)) {
    // The page strips ?token= from the address bar after load (DIG-1437);
    // a tab-session cookie lets a reload of the bare path still through.
    const res = await upstream(request);
    const headers = new Headers(res.headers);
    headers.append(
      "set-cookie",
      `${OCC_INVITE_COOKIE}=${encodeURIComponent(expected!)}; Path=/chat/occ; Secure; HttpOnly; SameSite=Strict`,
    );
    headers.set("cache-control", "no-store");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }
  if (inviteTokenValid(readCookie(request.headers.get("cookie"), OCC_INVITE_COOKIE), expected)) {
    const res = await upstream(request);
    const headers = new Headers(res.headers);
    headers.set("cache-control", "no-store");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }
  const nf = await upstream(`${url.origin}${SITE_NOT_FOUND_PATH}`, {
    headers: { accept: "text/html" },
  });
  const headers = new Headers(nf.headers);
  headers.set("cache-control", "no-store");
  return new Response(nf.body, { status: 404, headers });
}
