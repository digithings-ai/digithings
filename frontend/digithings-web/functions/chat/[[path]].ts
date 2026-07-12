interface Env {
  DIGICHAT_ORIGIN?: string;
}

interface PagesContext {
  request: Request;
  env: Env;
}

const DEFAULT_DIGICHAT_ORIGIN =
  "https://digichat.ashyforest-551bae97.eastus.azurecontainerapps.io";

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

function stripHopByHopHeaders(input: Headers): Headers {
  const output = new Headers();
  for (const [key, value] of input.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) output.set(key, value);
  }
  return output;
}

function appendForwardedFor(existing: string | null, clientIp: string | null): string | null {
  if (!clientIp) return existing;
  if (!existing) return clientIp;
  return `${existing}, ${clientIp}`;
}

export const onRequest = async ({ request, env }: PagesContext): Promise<Response> => {
  const incoming = new URL(request.url);
  if (!incoming.pathname.startsWith("/chat")) {
    return new Response("Not found", { status: 404 });
  }

  const origin = new URL((env.DIGICHAT_ORIGIN ?? DEFAULT_DIGICHAT_ORIGIN).trim());
  const upstreamPath = incoming.pathname.replace(/^\/chat(?=\/|$)/, "") || "/";
  const upstreamUrl = new URL(upstreamPath + incoming.search, origin.toString());

  const headers = stripHopByHopHeaders(request.headers);
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));
  const forwardedFor = appendForwardedFor(
    request.headers.get("x-forwarded-for"),
    request.headers.get("cf-connecting-ip"),
  );
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const upstreamRequest = new Request(upstreamUrl.toString(), {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  });
  const upstreamResponse = await fetch(upstreamRequest);

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: stripHopByHopHeaders(upstreamResponse.headers),
  });
};
