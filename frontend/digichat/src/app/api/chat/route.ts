import {
  convertToModelMessages,
  streamText,
  smoothStream,
  type UIMessage,
} from "ai";
import { createDigiGraphClient, digigraphModelName } from "@/lib/digigraph";
import {
  DigigraphUpstreamAuthError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";
import { createDigigraphTraceStreamResponse } from "@/lib/stream-digigraph-trace";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";

export const maxDuration = 120;

function isEmbedReferer(req: Request): boolean {
  const ref = req.headers.get("referer") ?? req.headers.get("referrer");
  if (!ref) return false;
  try {
    return new URL(ref).pathname.includes("/embed");
  } catch {
    return false;
  }
}

function isEmbedAllowed(req: Request): boolean {
  if (process.env.DIGICHAT_EMBED_ENABLED === "1") return true;
  const token = req.headers.get("x-embed-token")?.trim();
  const expected = process.env.DIGICHAT_EMBED_TOKEN?.trim();
  return Boolean(expected && token === expected);
}

export async function POST(req: Request) {
  const embedFromReferer = isEmbedReferer(req);
  const embedHost =
    req.headers.get("x-embed-host")?.trim() || (embedFromReferer ? "referer" : undefined);
  const authResult = await requireDigiChatAuth(req);
  let tenantSlug: string;
  let ownerUserSub: string;

  if (authResult instanceof Response) {
    if (embedHost && isEmbedAllowed(req)) {
      tenantSlug = "embed";
      ownerUserSub = "embed:anonymous";
    } else if (embedHost) {
      return new Response(
        JSON.stringify({
          error: "embed_disabled",
          message:
            "Embed chat requires DIGICHAT_EMBED_ENABLED=1 or a valid X-Embed-Token. See frontend/digichat/README.md.",
        }),
        { status: 503, headers: { "content-type": "application/json" } }
      );
    } else {
      return authResult;
    }
  } else {
    tenantSlug = authResult.tenantSlug;
    ownerUserSub = authResult.ownerUserSub;
  }

  const rateKey = `chat:${tenantSlug}:${ownerUserSub}`;
  const rate = checkBffRateLimit(rateKey);
  if (!rate.allowed) {
    return new Response(
      JSON.stringify({
        error: "rate_limit_exceeded",
        message: "Too many chat requests. Try again shortly.",
      }),
      {
        status: 429,
        headers: {
          "content-type": "application/json",
          "retry-after": String(rate.retryAfterSec),
        },
      }
    );
  }

  let body: { messages?: UIMessage[] };
  try {
    body = (await req.json()) as { messages?: UIMessage[] };
  } catch {
    return new Response(JSON.stringify({ error: "invalid_json" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }

  const messages = body.messages;
  if (!messages?.length) {
    return new Response(JSON.stringify({ error: "messages_required" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }

  let upstreamBearer: string;
  let litellmProxyApiKey: string | null = null;
  try {
    const up = await resolveDigigraphUpstreamAuth(req, tenantSlug, ownerUserSub);
    upstreamBearer = up.bearer;
    litellmProxyApiKey = up.litellmProxyApiKey;
  } catch (e) {
    const msg =
      e instanceof DigigraphUpstreamAuthError
        ? e.message
        : e instanceof Error
          ? e.message
          : "upstream_auth_failed";
    return new Response(JSON.stringify({ error: "upstream_auth", message: msg }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }

  const sessionId =
    req.headers.get("x-digichat-session") ??
    req.headers.get("x-session-id") ??
    crypto.randomUUID();

  const rid =
    req.headers.get("x-request-id")?.trim() || crypto.randomUUID();

  const eco = await getEcosystemEndpoints();
  const provider = createDigiGraphClient(eco.digigraphUrl, upstreamBearer);
  const model = provider(digigraphModelName());
  const coreMessages = await convertToModelMessages(
    messages.map((m) => {
      const { id: _omit, ...rest } = m;
      void _omit;
      return rest;
    }) as Omit<UIMessage, "id">[]
  );

  const upstreamHeaders: Record<string, string> = {
    "X-Session-Id": sessionId,
    "X-Request-ID": rid,
    "X-Digichat-Tenant": tenantSlug,
    "X-Digi-Tenant": tenantSlug,
    "X-Digi-Caller": "digichat",
    Authorization: `Bearer ${upstreamBearer}`,
  };
  if (litellmProxyApiKey) {
    upstreamHeaders["X-LiteLLM-Proxy-Key"] = litellmProxyApiKey;
  }

  // BYOK: forward per-request key to DigiGraph; never log or persist
  const byokKey = req.headers.get("x-byok-key")?.trim() ?? "";
  const byokProvider = req.headers.get("x-byok-provider")?.trim() ?? "";
  if (byokKey) {
    upstreamHeaders["X-BYOK-Key"] = byokKey;
    if (byokProvider) {
      upstreamHeaders["X-BYOK-Provider"] = byokProvider;
    }
  }

  const responseHeaders = {
    "X-Digichat-Session": sessionId,
    "X-Request-Id": rid,
  };

  const headerWantsTrace = req.headers.get("x-digichat-trace");
  const useTraceStream =
    process.env.DIGICHAT_TRACE_UI !== "0" && headerWantsTrace !== "0";

  if (useTraceStream) {
    return await createDigigraphTraceStreamResponse({
      messages,
      digigraphBaseUrl: eco.digigraphUrl ?? "",
      upstreamHeaders,
      responseHeaders,
      upstreamBearer,
    });
  }

  const result = streamText({
    model,
    messages: coreMessages,
    headers: upstreamHeaders,
    abortSignal: req.signal,
    experimental_transform: smoothStream({ chunking: "word" }),
  });

  return result.toUIMessageStreamResponse({
    headers: responseHeaders,
  });
}
