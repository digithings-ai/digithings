import {
  callbackHtml,
  clearOAuthCookieHeader,
  exchangeAuthorizationCode,
  MCP_OAUTH_MESSAGE,
  oauthResultCookieHeader,
  oauthSecret,
  readOAuthCookie,
  verifyOAuthState,
} from "@/lib/mcp-oauth";

export const maxDuration = 30;

const PAGE = callbackHtml();

function html(cookies: string[]): Response {
  const headers = new Headers({
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; script-src 'unsafe-inline';",
  });
  for (const cookie of cookies) headers.append("set-cookie", cookie);
  return new Response(PAGE, { status: 200, headers });
}

function finish(
  reqUrl: string,
  msg: { id: string; accessToken?: string; error?: string },
): Response {
  return html([
    clearOAuthCookieHeader(reqUrl),
    oauthResultCookieHeader({ type: MCP_OAUTH_MESSAGE, ...msg }, reqUrl),
  ]);
}

/** GET /api/mcp/oauth/callback — exchange code, postMessage token to opener. */
export async function GET(req: Request): Promise<Response> {
  const params = new URL(req.url).searchParams;
  const code = params.get("code")?.trim() ?? "";
  const state = params.get("state")?.trim() ?? "";
  const oauthError = params.get("error")?.trim();
  const secret = oauthSecret();
  const rawCookie = readOAuthCookie(req);

  const payload = secret && rawCookie ? verifyOAuthState(rawCookie, secret) : null;
  const id = payload?.id ?? "";

  if (oauthError) {
    return finish(req.url, { id, error: oauthError });
  }
  if (!payload || !state || payload.nonce !== state) {
    return finish(req.url, { id, error: "invalid_oauth_state" });
  }
  if (!code) {
    return finish(req.url, { id, error: "missing_code" });
  }
  try {
    const accessToken = await exchangeAuthorizationCode(payload, code);
    return finish(req.url, { id, accessToken });
  } catch {
    return finish(req.url, { id, error: "oauth_token_failed" });
  }
}
