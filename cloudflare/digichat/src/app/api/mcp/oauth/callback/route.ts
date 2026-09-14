import {
  callbackHtml,
  clearOAuthCookieHeader,
  exchangeAuthorizationCode,
  oauthSecret,
  readOAuthCookie,
  verifyOAuthState,
} from "@/lib/mcp-oauth";

export const maxDuration = 30;

function html(body: string, extraHeaders?: HeadersInit): Response {
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": "default-src 'none'; script-src 'unsafe-inline';",
      ...extraHeaders,
    },
  });
}

/** GET /api/mcp/oauth/callback — exchange code, postMessage token to opener. */
export async function GET(req: Request): Promise<Response> {
  const origin = new URL(req.url).origin;
  const params = new URL(req.url).searchParams;
  const code = params.get("code")?.trim() ?? "";
  const state = params.get("state")?.trim() ?? "";
  const oauthError = params.get("error")?.trim();
  const secret = oauthSecret();
  const rawCookie = readOAuthCookie(req);
  const clear = { "set-cookie": clearOAuthCookieHeader(req.url) };

  const payload = secret && rawCookie ? verifyOAuthState(rawCookie, secret) : null;
  const id = payload?.id ?? "";

  if (oauthError) {
    return html(callbackHtml({ origin, id, error: oauthError }), clear);
  }
  if (!payload || !state || payload.nonce !== state) {
    return html(callbackHtml({ origin, id, error: "invalid_oauth_state" }), clear);
  }
  if (!code) {
    return html(callbackHtml({ origin, id, error: "missing_code" }), clear);
  }
  try {
    const accessToken = await exchangeAuthorizationCode(payload, code);
    return html(callbackHtml({ origin, id, accessToken }), clear);
  } catch {
    return html(callbackHtml({ origin, id, error: "oauth_token_failed" }), clear);
  }
}
