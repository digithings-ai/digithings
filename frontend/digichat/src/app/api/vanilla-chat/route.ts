import {
  isLocalVanillaPreview,
  vanillaUpstreamChatUrl,
  VANILLA_DEFAULT_UPSTREAM,
  VANILLA_UPSTREAM_USER_AGENT,
} from "@/lib/vanilla-preview";

export const maxDuration = 120;

function jsonError(status: number, error: string, message: string): Response {
  return new Response(JSON.stringify({ error, message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Localhost assistant-ui preview: proxy the live digithings.ai chat BFF.
 * 404 outside development loopback so it cannot ship as a public API.
 */
export async function POST(req: Request) {
  if (!isLocalVanillaPreview(req)) {
    return new Response(null, { status: 404 });
  }

  const upstream = vanillaUpstreamChatUrl();
  let body: ArrayBuffer;
  try {
    body = await req.arrayBuffer();
  } catch {
    return jsonError(400, "invalid_body", "Request body could not be read");
  }

  const headers = new Headers();
  headers.set("content-type", req.headers.get("content-type") || "application/json");
  headers.set("x-embed-host", "digithings.ai");
  headers.set("origin", "https://digithings.ai");
  headers.set("referer", "https://digithings.ai/embed?host=digithings.ai");
  headers.set(
    "user-agent",
    req.headers.get("user-agent")?.trim() || VANILLA_UPSTREAM_USER_AGENT,
  );
  const runId = req.headers.get("x-digi-run-id")?.trim();
  if (runId) headers.set("x-digi-run-id", runId);
  const session = req.headers.get("x-digichat-session")?.trim();
  if (session) headers.set("x-digichat-session", session);

  let res: Response;
  try {
    res = await fetch(upstream, {
      method: "POST",
      headers,
      body,
      signal: req.signal,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "upstream_unreachable";
    return jsonError(502, "vanilla_upstream_failed", message);
  }

  const contentType = res.headers.get("content-type") ?? "text/event-stream";
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": contentType },
  });
}

/** Exported for tests — documents the default pin. */
export function defaultVanillaUpstream(): string {
  return VANILLA_DEFAULT_UPSTREAM;
}
