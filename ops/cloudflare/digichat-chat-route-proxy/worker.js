/**
 * Cloudflare Worker for path-routing DigiChat behind digithings.ai/chat*.
 *
 * This preserves a single public domain while forwarding chat traffic to a
 * separately hosted DigiChat origin.
 */

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
]);

function appendForwardedFor(existing, clientIp) {
  if (!clientIp) return existing ?? "";
  if (!existing) return clientIp;
  return `${existing}, ${clientIp}`;
}

function requireOrigin(rawOrigin) {
  if (!rawOrigin) {
    throw new Error("DIGICHAT_ORIGIN is required (example: https://chat-origin.example.com)");
  }
  const parsed = new URL(rawOrigin);
  if (!["https:", "http:"].includes(parsed.protocol)) {
    throw new Error("DIGICHAT_ORIGIN must be an http(s) URL");
  }
  if (!parsed.hostname) {
    throw new Error("DIGICHAT_ORIGIN must include a hostname");
  }
  return parsed;
}

function filterHeaders(input) {
  const out = new Headers();
  for (const [key, value] of input.entries()) {
    if (HOP_BY_HOP_HEADERS.has(key.toLowerCase())) continue;
    out.set(key, value);
  }
  return out;
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (!incoming.pathname.startsWith("/chat")) {
      return new Response("Not found", { status: 404 });
    }

    let origin;
    try {
      origin = requireOrigin(env.DIGICHAT_ORIGIN);
    } catch (error) {
      return new Response(
        JSON.stringify({
          error: "proxy_not_configured",
          detail: error instanceof Error ? error.message : "invalid DIGICHAT_ORIGIN",
        }),
        {
          status: 503,
          headers: { "content-type": "application/json; charset=utf-8" },
        },
      );
    }

    const upstreamUrl = new URL(incoming.pathname + incoming.search, origin.toString());
    const headers = filterHeaders(request.headers);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));

    const clientIp = request.headers.get("cf-connecting-ip");
    const priorForwardedFor = request.headers.get("x-forwarded-for");
    const forwardedFor = appendForwardedFor(priorForwardedFor, clientIp);
    if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

    const upstreamRequest = new Request(upstreamUrl.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });

    const upstreamResponse = await fetch(upstreamRequest);
    const responseHeaders = filterHeaders(upstreamResponse.headers);
    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: responseHeaders,
    });
  },
};
