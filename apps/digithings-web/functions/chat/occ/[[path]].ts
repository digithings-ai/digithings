/**
 * DIG-3585: Pages defence for /chat/occ when the Worker route is missing.
 * Uninvited requests get the site 404 and never the chat shell. That 404 is
 * byte-for-byte the response for a path that does not exist: status, body
 * and headers, so the address gives no hint that a page lives there.
 *
 * OCC_INVITE_KEY is the same Worker secret. This function fail-closes when it
 * is unset, so bind it on the Pages project before relying on Pages alone.
 * Do not put the value in this file.
 */
import {
  SITE_NOT_FOUND_PATH,
  inviteAccepted,
  occInviteCookieHeader,
} from "../../../../digichat-cloudflare/src/occ-gate";

type AssetsBinding = { fetch: (request: Request) => Promise<Response> };

export type OccPagesContext = {
  request: Request;
  env: { OCC_INVITE_KEY?: string; ASSETS?: AssetsBinding };
  next: () => Promise<Response>;
};

/** Only if the site 404 itself cannot be read: still a plain 404, never a 500. */
const FALLBACK_NOT_FOUND = "<!DOCTYPE html><title>404</title><h1>404</h1>";

async function siteNotFound(context: OccPagesContext, origin: string): Promise<Response> {
  const assetUrl = new URL(SITE_NOT_FOUND_PATH, origin);
  const assetRequest = new Request(assetUrl, { headers: { accept: "text/html" } });
  try {
    const nf = context.env.ASSETS
      ? await context.env.ASSETS.fetch(assetRequest)
      : await fetch(assetRequest);
    // The site's own 404, untouched: same status, body and headers as any
    // path the site does not have (/xyz, /chat/does-not-exist). No extra
    // header (not even cache-control) may mark this address as special.
    if (nf.status === 404) {
      return new Response(nf.body, { status: 404, statusText: nf.statusText, headers: nf.headers });
    }
  } catch {
    // fall through to the plain 404
  }
  return new Response(FALLBACK_NOT_FOUND, {
    status: 404,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

export async function onRequest(context: OccPagesContext): Promise<Response> {
  const url = new URL(context.request.url);
  const expected = context.env.OCC_INVITE_KEY;
  const accepted = inviteAccepted(context.request, expected);
  if (!accepted || !expected) return siteNotFound(context, url.origin);
  const res = await context.next();
  const headers = new Headers(res.headers);
  headers.set("cache-control", "no-store");
  if (accepted === "token") {
    headers.append("set-cookie", occInviteCookieHeader(expected));
  }
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}
