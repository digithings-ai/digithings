/**
 * DIG-3585: Pages defence for /chat/occ when the Worker route is missing.
 * Uninvited requests get the site 404 and never the chat shell.
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

export async function onRequest(context: OccPagesContext): Promise<Response> {
  const url = new URL(context.request.url);
  const expected = context.env.OCC_INVITE_KEY;
  const accepted = inviteAccepted(context.request, expected);
  if (!accepted || !expected) {
    const assetUrl = new URL(SITE_NOT_FOUND_PATH, url.origin);
    const assetRequest = new Request(assetUrl, { headers: { accept: "text/html" } });
    const nf = context.env.ASSETS
      ? await context.env.ASSETS.fetch(assetRequest)
      : await fetch(assetRequest);
    const headers = new Headers(nf.headers);
    headers.set("cache-control", "no-store");
    return new Response(nf.body, { status: 404, headers });
  }
  const res = await context.next();
  const headers = new Headers(res.headers);
  headers.set("cache-control", "no-store");
  if (accepted === "token") {
    headers.append("set-cookie", occInviteCookieHeader(expected));
  }
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}
