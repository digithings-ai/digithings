import {
  convertToModelMessages,
  streamText,
  smoothStream,
  type UIMessage,
} from "ai";
import {
  normalizeOpenRouterModel,
} from "@/lib/byok-openrouter";
import { byokRequiresModel } from "@/lib/byok-providers";
import { createDigiGraphClient, digigraphModelName } from "@/lib/digigraph";
import {
  DigigraphUpstreamAuthError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";
import { createDigigraphTraceStreamResponse } from "@/lib/adapters/digithings/stream";
import { createFoundryStreamResponse } from "@/lib/adapters/foundry/stream";
import { resolveLanguageCode } from "@/lib/languages";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import {
  checkEmbedIpRateLimit,
  clientIpForRateLimit,
} from "@/lib/embed-ip-rate-limit";
import {
  recordEmbedTrialTurn,
  isOverEmbedTrialLimit,
  unlockEmbedTrial,
} from "@/lib/embed-turn-quota";
import { consumeChatAccess } from "@/lib/embed-gate-provider";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import {
  embedConfigOf,
  isEmbedChatRequest,
  resolveEmbedChatTenant,
} from "@/lib/embed-chat-tenant";
import {
  acquireChatRunLock,
  releaseChatRunLockOnResponseEnd,
} from "@/lib/chat-run-lock";
import { isMutatingTurnMode, parseDigiTurnMode } from "@/lib/turn-mode";

export const maxDuration = 120;

function rateLimitResponse(message: string, retryAfterSec: number): Response {
  return new Response(
    JSON.stringify({ error: "rate_limit_exceeded", message }),
    {
      status: 429,
      headers: {
        "content-type": "application/json",
        "retry-after": String(retryAfterSec),
      },
    }
  );
}

function jsonError(
  status: number,
  error: string,
  message: string,
  headers?: Record<string, string>,
): Response {
  return new Response(JSON.stringify({ error, message }), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export async function POST(req: Request) {
  const authResult = await requireDigiChatAuth(req);
  const tenantCtx =
    authResult instanceof Response && isEmbedChatRequest(req)
      ? resolveEmbedChatTenant(req)
      : await resolveChatTenantContext(req, authResult);
  if (tenantCtx instanceof Response) {
    return tenantCtx;
  }
  const { tenantSlug, ownerUserSub } = tenantCtx;

  // Anonymous embed requests all share one bucket below (tenantSlug=embed,
  // ownerUserSub=embed:anonymous) — gate per-IP first so one visitor can't
  // exhaust it for everyone (#1251).
  if (ownerUserSub === "embed:anonymous") {
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return rateLimitResponse(
        "Too many requests from this address. Try again shortly.",
        ipRate.retryAfterSec
      );
    }
  }

  const rateKey = `chat:${tenantSlug}:${ownerUserSub}`;
  const rate = checkBffRateLimit(rateKey);
  if (!rate.allowed) {
    return rateLimitResponse("Too many chat requests. Try again shortly.", rate.retryAfterSec);
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

  const byokKey = req.headers.get("x-byok-key")?.trim() ?? "";
  const byokProvider = (req.headers.get("x-byok-provider")?.trim() ?? "").toLowerCase();
  const byokModel = normalizeOpenRouterModel(
    req.headers.get("x-byok-model")?.trim() ?? ""
  );
  const languageCode = resolveLanguageCode(req.headers.get("x-digi-language"));

  const sessionId =
    req.headers.get("x-digichat-session") ??
    req.headers.get("x-session-id") ??
    crypto.randomUUID();

  const rid =
    req.headers.get("x-request-id")?.trim() || crypto.randomUUID();

  const turnModeParsed = parseDigiTurnMode(req.headers.get("x-digi-turn-mode"));
  if (turnModeParsed === "invalid") {
    return jsonError(
      400,
      "invalid_turn_mode",
      "X-Digi-Turn-Mode must be send, regenerate, or edit_last_user",
    );
  }
  const turnMode = turnModeParsed;
  const runId = req.headers.get("x-digi-run-id")?.trim() || null;

  const responseHeaders = {
    "X-Digichat-Session": sessionId,
    "X-Request-Id": rid,
  };

  const embedConfig = embedConfigOf(tenantCtx);

  // trial_form gate: DataTap-branded embed that, after EMBED_FREE_TURN_LIMIT free
  // turns, defers the locked presentation to the embedding page (which shows the
  // trial form) rather than the BYOK/contact card. Enforced per client IP in
  // memory — best-effort anti-abuse per the design spec. Fail open on any internal
  // error so an infra hiccup never blocks a legitimate visitor.
  // When the tenant configures gate.consumeUrl and the client presents a chat
  // token, server-side quota supersedes the unlock header and the IP quota.
  let quotaSatisfied = false;
  if (embedConfig?.gateMode === "trial_form") {
    const chatToken = req.headers.get("x-embed-chat-token");
    if (embedConfig.gate && chatToken) {
      // Server-side quota supersedes the client-asserted unlock header for this request, and
      // replaces the IP quota entirely — a token-bearing visitor must not be gated twice.
      const verdict = await consumeChatAccess(embedConfig.gate.consumeUrl, chatToken);
      if (verdict === "deny") {
        return new Response(
          JSON.stringify({
            error: "trial_gate",
            message: "Complete the free trial form to keep chatting.",
          }),
          { status: 402, headers: { "content-type": "application/json" } },
        );
      }
      quotaSatisfied = true;
    }

    if (!quotaSatisfied) {
      try {
        const ip = clientIpForRateLimit(req);
        // "unknown" is what clientIpForRateLimit returns when the ingress fails
        // to set cf-connecting-ip/x-forwarded-for — it is not an identity (see
        // that module's own doc comment). Treating it as one would collapse
        // every visitor behind a broken/missing IP header into a single shared
        // quota bucket, permanently gating everyone after the first 3 turns
        // total. Skip the quota entirely in that case and fail open, consistent
        // with this module's "best-effort, not an authorization boundary"
        // philosophy (embed-turn-quota.ts).
        if (ip !== "unknown") {
          if (req.headers.get("x-embed-trial-unlock") === "1") {
            unlockEmbedTrial(ip);
          }
          if (isOverEmbedTrialLimit(ip)) {
            return new Response(
              JSON.stringify({
                error: "trial_gate",
                message: "Complete the free trial form to keep chatting.",
              }),
              { status: 402, headers: { "content-type": "application/json" } },
            );
          }
          recordEmbedTrialTurn(ip);
        }
      } catch (e) {
        console.warn("[trial-gate] quota error, failing open:", e);
      }
    }
  }

  const externalConversation = req.headers.get("x-external-conversation")?.trim() || null;
  const runLockKey = externalConversation
    ? `chat-run:${tenantSlug}:${sessionId}:${externalConversation}`
    : `chat-run:${tenantSlug}:${sessionId}`;
  const runLock = acquireChatRunLock(runLockKey, runId);
  if (!runLock.ok) {
    return jsonError(
      409,
      runLock.error,
      runLock.error === "run_in_progress"
        ? "A chat run is already in progress for this session."
        : "Duplicate X-Digi-Run-Id for this session; do not re-invoke.",
      responseHeaders,
    );
  }

  const finish = (res: Response) => releaseChatRunLockOnResponseEnd(res, runLock.release);

  if (embedConfig?.backend.type === "foundry") {
    const foundryRes = await createFoundryStreamResponse({
      projectEndpoint: embedConfig.backend.projectEndpoint,
      agentName: embedConfig.backend.agentName,
      messages,
      conversationId: externalConversation,
      responseHeaders,
      activityDetail: embedConfig.activityDetail,
      signal: req.signal,
      responseLanguage: languageCode,
      turnMode,
    });
    // JSON 4xx/501 from the adapter are not streams — release immediately.
    if (foundryRes.headers.get("content-type")?.includes("application/json")) {
      runLock.release();
      return foundryRes;
    }
    return finish(foundryRes);
  }

  const coreMessages = await convertToModelMessages(
    messages.map((m) => {
      const { id: _omit, ...rest } = m;
      void _omit;
      return rest;
    }) as Omit<UIMessage, "id">[]
  );

  // Non-OpenAI BYOK requires a model slug before forwarding to digigraph.
  const byokNeedsModel = byokRequiresModel(byokProvider);
  if (byokKey && byokNeedsModel && !byokModel) {
    runLock.release();
    return new Response(
      JSON.stringify({
        error: "byok_model_required",
        message: `${byokProvider} BYOK requires X-BYOK-Model (e.g. openai/gpt-4o-mini, claude-…, gemini/…).`,
      }),
      { status: 400, headers: { "content-type": "application/json" } }
    );
  }

  let upstreamBearer: string;
  let litellmProxyApiKey: string | null = null;
  try {
    const up = await resolveDigigraphUpstreamAuth(req, tenantSlug, ownerUserSub);
    upstreamBearer = up.bearer;
    litellmProxyApiKey = up.litellmProxyApiKey;
  } catch (e) {
    runLock.release();
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

  const eco = await getEcosystemEndpoints();
  const provider = createDigiGraphClient(eco.digigraphUrl, upstreamBearer);
  const model = provider(digigraphModelName());

  const upstreamHeaders: Record<string, string> = {
    "X-Session-Id": sessionId,
    "X-Request-ID": rid,
    "X-Digichat-Tenant": tenantSlug,
    "X-Digi-Tenant": tenantSlug,
    "X-Digi-Caller": "digichat",
    Authorization: `Bearer ${upstreamBearer}`,
  };
  if (embedConfig?.backend.type === "digigraph") {
    if (embedConfig.backend.digisearchIndex) {
      upstreamHeaders["X-Digi-Corpus-Index"] = embedConfig.backend.digisearchIndex;
    }
    if (embedConfig.backend.vaultPathPrefix) {
      upstreamHeaders["X-Digi-Vault-Prefix"] = embedConfig.backend.vaultPathPrefix;
    }
  }
  if (litellmProxyApiKey) {
    upstreamHeaders["X-LiteLLM-Proxy-Key"] = litellmProxyApiKey;
  }
  if (languageCode !== "en") {
    upstreamHeaders["X-Digi-Language"] = languageCode;
  }
  // X-Digi-Force-Tool is send-only — ignore leftover slash force on regen/edit (#3475).
  const forceTool = req.headers.get("x-digi-force-tool")?.trim();
  if (forceTool && !isMutatingTurnMode(turnMode)) {
    upstreamHeaders["X-Digi-Force-Tool"] = forceTool;
  }

  // BYOK: forward per-request key to digigraph; never log or persist.
  if (byokKey) {
    upstreamHeaders["X-BYOK-Key"] = byokKey;
    if (byokProvider) {
      upstreamHeaders["X-BYOK-Provider"] = byokProvider;
    }
    // Forward any model the caller sent. `byokNeedsModel` gates the 400 above —
    // whether a model is *mandatory* — and must not also gate whether an optional
    // one is passed on: that dropped an openai user's chosen model at the BFF even
    // when the browser sent it, leaving digigraph on its own default (#2490).
    if (byokModel) {
      upstreamHeaders["X-BYOK-Model"] = byokModel;
    }
  }

  const headerWantsTrace = req.headers.get("x-digichat-trace");
  const useTraceStream =
    process.env.DIGICHAT_TRACE_UI !== "0" && headerWantsTrace !== "0";

  if (useTraceStream) {
    return finish(
      await createDigigraphTraceStreamResponse({
        messages,
        digigraphBaseUrl: eco.digigraphUrl ?? "",
        upstreamHeaders,
        responseHeaders,
        activityDetail: embedConfig?.activityDetail ?? "full",
        signal: req.signal,
      }),
    );
  }

  const result = streamText({
    model,
    messages: coreMessages,
    headers: upstreamHeaders,
    abortSignal: req.signal,
    experimental_transform: smoothStream({ chunking: "word" }),
  });

  return finish(
    result.toUIMessageStreamResponse({
      headers: responseHeaders,
    }),
  );
}
