/**
 * Credential-aware fetch (#2572).
 *
 * Node/undici follows redirects by default and forwards custom headers across
 * origins, stripping only `Authorization`. That means `X-BYOK-Key`,
 * `X-LiteLLM-Proxy-Key`, and the MCP token headers `X-Digi-Mcp-Servers` /
 * `X-Digi-Mcp-Session` (and other non-Authorization credential headers) would
 * ride a cross-origin 302 to an attacker-chosen host if an allowlisted digigraph
 * (or provider) ever redirected.
 *
 * Policy: when the request carries credential headers, force `redirect: "manual"`.
 * Same-origin redirects are followed with credentials (bounded hops). Cross-origin
 * redirects are refused — never re-issued with credentials. Callers that want a
 * stripped follow can catch `CredentialRedirectError` and decide; digichat does not
 * auto-strip-and-follow on the streaming / BYOK paths.
 */

export const CREDENTIAL_HEADER_NAMES = [
  "authorization",
  "cookie",
  "proxy-authorization",
  "x-api-key",
  "x-goog-api-key",
  "x-byok-key",
  "x-litellm-proxy-key",
  "x-digi-mcp-servers",
  "x-digi-mcp-session",
] as const;

/**
 * Any header under one of these prefixes is credential-bearing even if it is not
 * listed in `CREDENTIAL_HEADER_NAMES`. The MCP BFF forwards serialized upstream
 * tokens in `X-Digi-Mcp-Servers` (with `row.token`) and a client overlay in
 * `X-Digi-Mcp-Session`; prefix matching keeps a future `X-Digi-Mcp-*` token
 * header covered without editing the exact-name list (#3933).
 */
export const CREDENTIAL_HEADER_PREFIXES = ["x-digi-mcp-"] as const;

const CREDENTIAL_HEADER_SET = new Set<string>(CREDENTIAL_HEADER_NAMES);

const MAX_SAME_ORIGIN_HOPS = 4;

export class CredentialRedirectError extends Error {
  readonly code = "cross_origin_credential_redirect" as const;
  readonly fromOrigin: string;
  readonly toOrigin: string;

  constructor(fromOrigin: string, toOrigin: string) {
    super(
      `Refusing to follow cross-origin redirect with credential headers (${fromOrigin} → ${toOrigin}).`,
    );
    this.name = "CredentialRedirectError";
    this.fromOrigin = fromOrigin;
    this.toOrigin = toOrigin;
  }
}

export function normalizeHeaderName(name: string): string {
  return name.trim().toLowerCase();
}

export function isCredentialHeaderName(name: string): boolean {
  const normalized = normalizeHeaderName(name);
  if (CREDENTIAL_HEADER_SET.has(normalized)) return true;
  return CREDENTIAL_HEADER_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

/** True when `init.headers` contains any credential-bearing header. */
export function hasCredentialHeaders(headers?: HeadersInit | null): boolean {
  if (!headers) return false;
  if (headers instanceof Headers) {
    for (const name of headers.keys()) {
      if (isCredentialHeaderName(name)) return true;
    }
    return false;
  }
  if (Array.isArray(headers)) {
    return headers.some(([name]) => isCredentialHeaderName(name));
  }
  return Object.keys(headers).some((name) => isCredentialHeaderName(name));
}

export function sameOrigin(a: URL, b: URL): boolean {
  return a.protocol === b.protocol && a.host === b.host;
}

function resolveRequestUrl(input: RequestInfo | URL): URL {
  if (input instanceof URL) return input;
  if (typeof input === "string") return new URL(input);
  return new URL(input.url);
}

function isRedirectStatus(status: number): boolean {
  return status >= 300 && status < 400;
}

type RequestInitWithDuplex = RequestInit & { duplex?: "half" };

/**
 * Release a redirect response we refuse to follow. An unconsumed body holds the
 * underlying undici socket open; cancel (not drain) avoids blocking on a stream
 * the peer may never finish.
 */
async function discardResponseBody(res: Response): Promise<void> {
  try {
    await res.body?.cancel();
  } catch {
    // Body absent, already consumed, or locked — nothing further to release.
  }
}

/**
 * Fetch that does not forward credential headers across origins.
 *
 * When no credential headers are present, behaves like `fetch` (default redirect
 * follow). When they are present, uses `redirect: "manual"` and only follows
 * same-origin Location hops.
 */
function requestCarriesCredentials(
  input: RequestInfo | URL,
  init?: RequestInit,
): boolean {
  if (hasCredentialHeaders(init?.headers)) return true;
  if (typeof Request !== "undefined" && input instanceof Request) {
    return hasCredentialHeaders(input.headers);
  }
  return false;
}

export async function fetchGuarded(
  input: RequestInfo | URL,
  init?: RequestInit,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  if (!requestCarriesCredentials(input, init)) {
    return fetchImpl(input, init);
  }

  // Caller may have set redirect already; credentialed path always overrides.
  const { redirect: _ignoredRedirect, ...rest } = init ?? {};
  void _ignoredRedirect;

  let currentUrl = resolveRequestUrl(input);
  const requestInput =
    typeof Request !== "undefined" && input instanceof Request ? input : null;

  // Prefer explicit init headers; fall back to Request headers when input is a Request.
  let headers = rest.headers;
  if (!headers && requestInput) {
    headers = requestInput.headers;
  }

  // Merge fields from a Request input that the explicit init does not override.
  // Without this, `fetchGuarded(request)` downgrades the credentialed request to
  // a bodyless GET and drops its abort signal.
  const derived: RequestInitWithDuplex = {};
  if (requestInput) {
    if (rest.method === undefined) derived.method = requestInput.method;
    if (rest.signal === undefined && requestInput.signal) derived.signal = requestInput.signal;
    if (rest.body === undefined && requestInput.body) {
      derived.body = requestInput.body;
      // Node/undici requires an explicit duplex mode for a stream body.
      derived.duplex = "half";
    }
  }

  let currentInit: RequestInitWithDuplex = {
    ...rest,
    ...derived,
    headers,
    redirect: "manual",
  };

  for (let hop = 0; hop <= MAX_SAME_ORIGIN_HOPS; hop++) {
    const res = await fetchImpl(currentUrl.toString(), currentInit);
    if (!isRedirectStatus(res.status)) {
      return res;
    }
    const loc = res.headers.get("location");
    if (!loc) {
      // No Location — surface the redirect response; caller can inspect status.
      return res;
    }
    const nextUrl = new URL(loc, currentUrl);
    if (!sameOrigin(currentUrl, nextUrl)) {
      await discardResponseBody(res);
      throw new CredentialRedirectError(currentUrl.origin, nextUrl.origin);
    }
    if (hop === MAX_SAME_ORIGIN_HOPS) {
      await discardResponseBody(res);
      throw new Error("too_many_same_origin_redirects");
    }
    currentUrl = nextUrl;
    // Drop body on redirects that are not 307/308 (WHATWG / browsers do this for
    // POST→GET on 301/302/303). Preserve method+body only for 307/308.
    if (res.status !== 307 && res.status !== 308) {
      const { body: _body, ...withoutBody } = currentInit;
      void _body;
      currentInit = {
        ...withoutBody,
        method: res.status === 303 ? "GET" : currentInit.method ?? "GET",
        redirect: "manual",
      };
      if (currentInit.method === "GET" || currentInit.method === "HEAD") {
        // GET/HEAD must not carry a body.
        const { body: _b2, ...clean } = currentInit;
        void _b2;
        currentInit = { ...clean, redirect: "manual" };
      }
    } else {
      currentInit = { ...currentInit, redirect: "manual" };
    }
  }

  throw new Error("too_many_same_origin_redirects");
}
