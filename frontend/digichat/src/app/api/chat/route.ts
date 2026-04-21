import {
  convertToModelMessages,
  streamText,
  smoothStream,
  type UIMessage,
} from "ai";
import { auth } from "@/auth";
import { createDigiGraphClient, digigraphModelName } from "@/lib/digigraph";
import {
  DigigraphUpstreamAuthError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";
import { createDigigraphTraceStreamResponse } from "@/lib/stream-digigraph-trace";
import { validateMachineApiKey } from "@/lib/api-key";
import { tenantSlugForOidcSubject } from "@/lib/tenant";
import { getEcosystemEndpoints } from "@/lib/ecosystem";

export const maxDuration = 120;

export async function POST(req: Request) {
  const machine = await validateMachineApiKey(req.headers.get("authorization"));
  const session = await auth();

  if (!machine && !session?.user) {
    return new Response(
      JSON.stringify({
        error: "unauthorized",
        message: "Sign in or send a valid machine API key (Authorization: Bearer dgk_live_…).",
      }),
      { status: 401, headers: { "content-type": "application/json" } }
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

  const sub = session?.user?.id;
  let tenantSlug: string;
  try {
    tenantSlug = machine
      ? machine.tenantSlug
      : sub
        ? await tenantSlugForOidcSubject(sub)
        : "default";
  } catch (e) {
    const msg = e instanceof Error ? e.message : "tenant_resolution_failed";
    return new Response(JSON.stringify({ error: "tenant_error", message: msg }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  }

  const ownerUserSub = machine
    ? `machine:${tenantSlug}`
    : session?.user?.id ?? "unknown";

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
    experimental_transform: smoothStream({ chunking: "word" }),
  });

  return result.toUIMessageStreamResponse({
    headers: responseHeaders,
  });
}
