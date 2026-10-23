import {
  convertToModelMessages,
  streamText,
  smoothStream,
  toUIMessageStream,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";
import {
  normalizeOpenRouterModel,
} from "@/lib/byok-openrouter";
import { byokRequiresModel } from "@/lib/byok-providers";
import { byokModelExample } from "@/lib/byok-model-example";
import {
  AI_SDK_PROTOCOLS,
  NON_AI_SDK_PROTOCOLS,
  backendAdapterFor,
  isAiSdkConfig,
  isDigigraphConfig,
  isFoundryConfig,
  isNonAiSdkConfig,
} from "@/lib/backend-adapters";
import { createDigiGraphClient, digigraphModelName } from "@/lib/digigraph";
import { demoChatResponse, isDemoChatEnabled } from "@/lib/demo-chat";
import {
  DIGIKEY_UNAVAILABLE_RETRY_AFTER_SECONDS,
  DigigraphUpstreamAuthError,
  DigigraphUpstreamUnavailableError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";
import { createDigigraphTraceStreamResponse } from "@/lib/adapters/digithings/stream";
import { createFoundryStreamResponse } from "@/lib/adapters/foundry/stream";
import { createAiSdkStreamResponse } from "@/lib/adapters/ai-sdk/stream";
import { createNonAiSdkStreamResponse } from "@/lib/adapters/non-ai-sdk";
import { createTurnGuard, guardrailPrepareStep } from "@/lib/guardrails/turn";
import { admitChatTurn, projectedGuardrails } from "@/lib/limits/admit";
import { loadCatalogPrices } from "@/lib/limits/prices";
import { resolveLanguageCode } from "@/lib/languages";
import { deploymentRateLimitEnabled, premiumModelsHeader } from "@/lib/deploy-config/schema";
import { catalogModelRate, premiumIdsFromGroups } from "@/lib/model-picker-catalog";
import {
  applyPremiumBudget,
  premiumSpendIdentity,
  premiumUserKey,
} from "@/lib/premium-budget/budget";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { getHeartbeatContext, licenseRefusal } from "@/lib/license/state";
import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import {
  checkEmbedIpRateLimit,
  clientIpForEmbedLimit,
  clientIpForRateLimit,
} from "@/lib/embed-ip-rate-limit";
import {
  recordEmbedTrialTurn,
  isOverEmbedTrialLimit,
  unlockEmbedTrial,
} from "@/lib/embed-turn-quota";
import {
  EMBED_MONITOR_TOKEN_HEADER,
  isAllowlistedMonitorToken,
} from "@/lib/embed-monitor-token";
import { consumeChatAccess } from "@/lib/embed-gate-provider";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import {
  embedConfigOf,
  isEmbedChatRequest,
  resolveAnonymousInstallChat,
  resolveEmbedChatTenant,
} from "@/lib/embed-chat-tenant";
import { isPlanTierSatisfied } from "@/lib/embed-tenants";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { verifyPlanProof } from "@/lib/plan-proof";
import {
  acquireChatRunLock,
  releaseChatRunLockOnResponseEnd,
} from "@/lib/chat-run-lock";
import { isMutatingTurnMode, parseDigiTurnMode } from "@/lib/turn-mode";
import { uiMessagesForUpstream } from "@/lib/ui-stream-parts";
import { registerSession } from "@/lib/session-links";

// #4753: the boot-retry budget in adapters/digithings/stream.ts runs up to
// ~250s (stack portReady 180s + instanceGet 60s + margin). The route must
// outlive it or a slow cold boot is cut off mid-retry; 300s leaves headroom
// for the answer stream that follows.
export const maxDuration = 300;

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
  // Revoked/expired license refuses before auth: a revoked deployment
  // refuses even an authenticated caller, and the check is cheaper.
  const refusal = licenseRefusal();
  if (refusal) return refusal;
  const authResult = await requireDigiChatAuth(req);
  const tenantCtx =
    authResult instanceof Response && isEmbedChatRequest(req)
      ? resolveEmbedChatTenant(req)
      : authResult instanceof Response
        ? (resolveAnonymousInstallChat() ?? authResult)
        : await resolveChatTenantContext(req, authResult);
  if (tenantCtx instanceof Response) {
    return tenantCtx;
  }
  const { tenantSlug, ownerUserSub } = tenantCtx;
  const byokKey = req.headers.get("x-byok-key")?.trim() ?? "";
  const embedConfig = embedConfigOf(tenantCtx);

  // Resolve the deployment before the request limiter. The limiter is
  // per deployment (`guardrails.rateLimit`), and an own key skips it.
  let dep: DigichatDeployment | null = null;
  // A config read error must keep failing closed for an explicit model, so
  // track it separately from "no deployment matched this host".
  let configFailed = false;
  try {
    const { resolveDeploymentForHost, getDigichatConfig, embedTenantToDeployment } =
      await import("@/lib/deploy-config/loader");
    try {
      const config = getDigichatConfig();
      // Host selection is never authorization. On the embed surface the host
      // has already been verified (token / first-party origin) before we get
      // here, so X-Embed-Host is safe to consult. On the authenticated session
      // path it is just a client-supplied header — use the config's own
      // deployment block instead of letting a caller name another host.
      dep = embedConfig
        ? resolveDeploymentForHost(req.headers.get("x-embed-host"), config)
        : (config.deployment ?? null);
    } catch {
      configFailed = true;
      dep = null;
    }
    if (!dep && embedConfig) dep = embedTenantToDeployment(embedConfig);
  } catch {
    // Unreadable loader must never 500 a request that used to work.
    configFailed = true;
    dep = null;
  }

  const spendGuardrails = embedConfig?.guardrails ?? dep?.guardrails;
  // Own key: not our inference budget. OCC sets rateLimit false for everyone.
  const skipOurRequestLimit =
    byokKey.length > 0 || !deploymentRateLimitEnabled(spendGuardrails);

  // Anonymous embed requests all share one bucket below (tenantSlug=embed,
  // ownerUserSub=embed:anonymous) — gate per-IP first so one visitor can't
  // exhaust it for everyone (#1251).
  if (!skipOurRequestLimit && ownerUserSub === "embed:anonymous") {
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return rateLimitResponse(
        "Too many requests from this address. Try again shortly.",
        ipRate.retryAfterSec
      );
    }
  }

  if (!skipOurRequestLimit) {
    const rateKey = `chat:${tenantSlug}:${ownerUserSub}`;
    const rate = checkBffRateLimit(rateKey);
    if (!rate.allowed) {
      return rateLimitResponse("Too many chat requests. Try again shortly.", rate.retryAfterSec);
    }
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

  const byokProvider = (req.headers.get("x-byok-provider")?.trim() ?? "").toLowerCase();
  const byokModel = normalizeOpenRouterModel(
    req.headers.get("x-byok-model")?.trim() ?? ""
  );
  const languageCode = resolveLanguageCode(req.headers.get("x-digi-language"));

  // Dev-only: a canned reply so the tool chain (reasoning, grouped tool
  // calls, the banners around them) can be reviewed in the local embed
  // without a model behind it. Never in production.
  if (isDemoChatEnabled() && !byokKey) {
    return demoChatResponse();
  }

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

  const responseHeaders: Record<string, string> = {
    "X-Digichat-Session": sessionId,
    "X-Request-Id": rid,
  };

  // Embed wins wherever both exist so the embed surface stays byte-identical;
  // the change is the session surface gaining the deployment config.
  const backend = embedConfig?.backend ?? dep?.backend;
  const foundryAlias = backend && isFoundryConfig(backend) ? backend.maxToolCalls : undefined;
  const limitSlug = embedConfig?.slug ?? dep?.slug ?? tenantSlug;
  const limitGuardrails = embedConfig?.guardrails ?? dep?.guardrails;
  const limitConfig = embedConfig?.limits ?? dep?.limits;
  // The registry describes the backend once (#4522): the streaming path is
  // chosen from `adapter.protocol`, never from a `backend.type` comparison.
  const adapter = backendAdapterFor(backend?.type);
  const activityDetail = embedConfig?.activityDetail ?? dep?.gate.activityDetail ?? "labels";
  const requiredPlanTier = embedConfig?.requiredPlanTier ?? dep?.gate.requiredPlanTier;

  // Desk+ tier gate (#3662, Chris lock): when the embed config declares a
  // requiredPlanTier, the caller must present a valid HMAC-signed plan proof
  // token (X-Embed-Plan-Proof header) OR an authenticated digichat session
  // with plan_tier in app_metadata.  Raw client-asserted X-Embed-Plan-Tier
  // headers and ?plan_tier= query params are NEVER trusted — they are
  // spoofable.  Fail closed when proof is absent or tier below threshold.
  // Scoped to tenants with requiredPlanTier set — digithings.ai and all
  // other tenants are untouched.
  if (requiredPlanTier) {
    let callerTier: string | null = null;

    // Prefer: HMAC-signed plan proof token from the dashboard popup.
    const proofToken = req.headers.get("x-embed-plan-proof")?.trim();
    if (proofToken) {
      const proofSecret = process.env.DIGICHAT_PLAN_PROOF_SECRET?.trim();
      if (proofSecret) {
        callerTier = verifyPlanProof(proofToken, proofSecret);
      }
    }

    // Fallback: authenticated digichat session with plan_tier in JWT claims.
    if (!callerTier && authResult && !(authResult instanceof Response)) {
      callerTier = authResult.plan_tier ?? null;
    }

    // NEVER trust raw X-Embed-Plan-Tier / ?plan_tier= — client-asserted and spoofable.

    if (!isPlanTierSatisfied({ requiredPlanTier }, callerTier)) {
      return jsonError(
        403,
        "plan_tier_required",
        `Chat requires ${requiredPlanTier}+ plan tier.`,
      );
    }
  }

  // trial_form gate: DataTap-branded embed that, after EMBED_FREE_TURN_LIMIT free
  // turns, defers the locked presentation to the embedding page (which shows the
  // trial form) rather than the BYOK/contact card. Enforced per client IP in
  // memory — best-effort anti-abuse per the design spec. Fail open on any internal
  // error in the per-IP quota check so an infra hiccup never blocks a legitimate
  // visitor; the monitor-allowlist check below is the exception and fails closed.
  // When the tenant configures gate.consumeUrl and the client presents a chat
  // token, server-side quota supersedes the unlock header and the IP quota.
  let quotaSatisfied = false;
  // Set when the tenant's quota service could not answer (5xx, timeout, transport
  // error). The visitor is still admitted — a tenant outage must not 402 someone who
  // already completed the form, because verifying that form *is* the call that is down
  // — but the entitlement is unverified, so it is bounded server-side below instead of
  // being granted outright.
  let quotaServiceUnavailable = false;
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
      if (verdict === "unavailable") {
        // The tenant could not answer. Fall through to the per-IP budget with the
        // entitlement bounded server-side (see the degraded raise below) rather than
        // skipping the budget entirely, which is what an outage used to do.
        // Logged like the two sibling fail-open paths in this gate: without a log, a
        // tenant quota-service outage silently changes the entitlement from unbounded
        // to capped and ops never sees it.
        console.warn(
          "[trial-gate] tenant quota service unavailable, bounding the entitlement to the trial cap:",
        );
        quotaServiceUnavailable = true;
      } else {
        quotaSatisfied = true;
      }
    }

    if (!quotaSatisfied) {
      try {
        // An allowlisted internal monitor (DIG-613) holds a server-side secret
        // and is exempt from the per-IP free-turn budget, so an hourly check can
        // run every hour without spending the window's 3 turns in the first hour
        // and then reporting 402 for the next 24. The secret is not
        // X-Embed-Token — that one is a publishable key served in the embedding
        // page (DIG-619), so a bypass keyed on it would be public. Fails open:
        // no allowlist configured means this is false and the quota below runs
        // exactly as before. Scope is this gate only — every other check in this
        // route, and tenant resolution itself, is unchanged.
        if (isAllowlistedMonitorToken(req.headers.get(EMBED_MONITOR_TOKEN_HEADER))) {
          quotaSatisfied = true;
        }
      } catch (e) {
        // Fails CLOSED for the bypass: the assignment above never ran, so
        // quotaSatisfied stays false and the per-IP quota below applies to this
        // caller exactly as it did before the monitor check existed. Do not set
        // quotaSatisfied here to "reconcile" this log with the wording it replaced
        // ("failing open") — that would turn a safe fallback into a real quota
        // bypass (DIG-1165).
        console.warn(
          "[trial-gate] monitor allowlist error, falling back to the per-IP cap:",
          e,
        );
      }
    }

    if (!quotaSatisfied) {
      try {
        const ip = clientIpForEmbedLimit(req);
        // "unknown" is develop's key when no visitor header is present. The
        // trial quota skips it and admits the visitor uncounted, so
        // header-less traffic does not share one trial bucket. The embed
        // limiter still records embed_ip:unknown, which is develop's
        // collapse for that case. With DIGICHAT_TRUSTED_PROXIES unset the
        // key is the raw trimmed cf-connecting-ip, then the raw trimmed
        // first X-Forwarded-For hop, and the stamp is ignored. A non-IP
        // value stays the key (embed-turn-quota.ts).
        if (ip !== "unknown") {
          if (quotaServiceUnavailable) {
            // Degraded path: the tenant's quota service could not answer, so the
            // entitlement is unverified. Bound it server-side at the trial cap (100
            // turns per IP per 24h) instead of skipping the budget, which is what an
            // outage used to do — that granted unbounded free turns to anyone
            // presenting a chat token. Same counter and same cap as the
            // client-asserted unlock below, so a forged header buys nothing the server
            // did not grant.
            unlockEmbedTrial(ip);
          }
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

  // The artifact blob route keys link lifetime on the conversation id, because
  // that is what the path carries. Register the conversation here so a token
  // bound by the artifacts POST can validate. Re-registering the same id is
  // idempotent, so a render or poll does not kill a link the user is holding;
  // a reload mints a new conversation id, the old one is never re-registered,
  // and its links stop resolving with no TTL anywhere.
  if (externalConversation) {
    registerSession(externalConversation, ownerUserSub);
  }
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

  // Deploy `models.available` allowlist (fail closed when non-empty). Resolved
  // before the backend branch so it applies to foundry too, not just digigraph.
  // Prefer X-Digi-Model on the house path. Bound BYOK spends the visitor's
  // provider models — the CI picker must not reject those ids (#3829).
  // The tenant's curated default wins over the deployment-wide fallback:
  // `models.default` is what the picker shows as selected, so using it here
  // keeps the first turn on the same model the visitor sees (v4.1-flash for
  // OCC) instead of the digigraph operator default. Only a slug the tenant
  // actually offers is trusted; anything else falls back.
  // ONE artefact decides the session lock and the model allowlist (DIG-4589).
  // On the embed surface that artefact is the request's tenant: in production
  // it is the projection of the MERGED host deployment, so it carries the
  // deployment's lock and model list together with the registry tenant's own.
  // The lock is an embed control (DIG-1210), so it never reaches the
  // authenticated session surface, where the deployment config alone decides
  // the allowlist.
  const policyModels = embedConfig?.models ?? dep?.models;
  const policyAvailable = policyModels?.available ?? [];
  const policyLocked = embedConfig?.lockSessionControls === true;
  const curatedDefault = policyModels?.default?.trim();
  const tenantDefaultModel =
    curatedDefault &&
    (policyAvailable.length === 0 || policyAvailable.includes(curatedDefault))
      ? curatedDefault
      : undefined;
  let modelId = tenantDefaultModel || digigraphModelName();
  // A tenant with lockSessionControls pins the house default model (DIG-1210):
  // a visitor's /model pick or session_set_model result is never forwarded.
  // The lock and the allowlist below come from the same artefact, so the two
  // sources can never disagree: the merge keeps a lock set in the deployment
  // config AND a lock set in the tenant registry (a lock is a restriction,
  // so a merge never drops one), and it folds the registry's model list into
  // the deployment the tenant is projected from.
  // Exception: a locked tenant that curates its own `models.available` list
  // lets the visitor pick from exactly that list (allowlist enforced below).
  const lockedWithoutModelList = policyLocked && policyAvailable.length === 0;
  const requestedModel = lockedWithoutModelList
    ? undefined
    : req.headers.get("x-digi-model")?.trim() || undefined;
  // House-path session model (non-BYOK, allowlisted). digigraph only binds it
  // when the slug is also on its own DIGI_SESSION_MODEL_ALLOWLIST.
  let houseSessionModel: string | undefined;
  let routerModels: string | undefined;
  try {
    const { resolveHouseModelSelection, routerModelsHeader } = await import("@/lib/deploy-config");
    if (byokKey) {
      if (requestedModel) modelId = requestedModel;
    } else if (policyModels && policyAvailable.length > 0) {
      const allowed = resolveHouseModelSelection(policyModels, requestedModel);
      if (requestedModel && allowed === undefined) {
        runLock.release();
        return new Response(
          JSON.stringify({
            error: "model_not_allowed",
            message: "Requested model is not in the deployment allowlist.",
          }),
          { status: 400, headers: { "content-type": "application/json" } },
        );
      }
      if (allowed) modelId = allowed;
      if (requestedModel && allowed) {
        houseSessionModel = allowed;
        routerModels = routerModelsHeader(policyModels, allowed);
      }
    } else if (configFailed && requestedModel) {
      // The deployment config could not be read, so we cannot prove the model
      // is allowed → fail closed rather than forward an unverified id.
      runLock.release();
      return new Response(
        JSON.stringify({
          error: "model_not_allowed",
          message: "Deployment model allowlist could not be loaded.",
        }),
        { status: 400, headers: { "content-type": "application/json" } },
      );
    } else if (requestedModel) {
      modelId = requestedModel;
    }
  } catch {
    // Invalid deploy config with an explicit request → fail closed.
    if (requestedModel) {
      runLock.release();
      return new Response(
        JSON.stringify({
          error: "model_not_allowed",
          message: "Deployment model allowlist could not be loaded.",
        }),
        { status: 400, headers: { "content-type": "application/json" } },
      );
    }
  }

  // Pin the curated default on the house header. digigraph ignores the body
  // model, and the header was set only when the client sent X-Digi-Model.
  if (!byokKey && !houseSessionModel && dep?.models?.available?.includes(modelId)) {
    houseSessionModel = modelId;
  }

  let premiumNotice: string | undefined;
  let chargePremium: ((usage?: { inputTokens: number; outputTokens: number }) => void) | undefined;
  if (!byokKey && dep?.models) {
    const premiumIds = premiumIdsFromGroups(dep.models.picker?.groups);
    const applied = applyPremiumBudget({
      modelId,
      defaultModel: tenantDefaultModel,
      premium: premiumIds.includes(modelId),
      premiumIds,
      rate: catalogModelRate(modelId),
      budget: dep.models.costPerWindow,
      userKey: premiumUserKey(
        tenantSlug,
        premiumSpendIdentity({
          userId: ownerUserSub,
          ip: clientIpForRateLimit(req),
        }),
      ),
    });
    if (applied.notice) {
      modelId = applied.modelId;
      houseSessionModel = applied.modelId;
      routerModels = undefined;
      premiumNotice = applied.notice;
      responseHeaders["X-Digi-Premium-Fallback"] = "auto";
    } else {
      chargePremium = applied.charge;
    }
  }

  // The chat's /effort choice (low/medium/high), or undefined for the model's
  // own default. digigraph gets it as X-Digi-Effort; Foundry as reasoning.effort.
  const effortRaw = (req.headers.get("x-digi-effort") || "").trim().toLowerCase();
  const reasoningEffort =
    effortRaw === "low" || effortRaw === "medium" || effortRaw === "high" ? effortRaw : undefined;

  // models.costPerWindow stays on the premium budget above. The limits block
  // is the other gates (tokens, turns, sessions, tool calls, model tiers).
  const clientIp = clientIpForRateLimit(req);
  const admission = admitChatTurn({
    limits: limitConfig,
    guardrails: limitGuardrails,
    slug: limitSlug,
    userId: ownerUserSub,
    sessionId,
    ip: clientIp,
    conversationId: externalConversation,
    modelId,
    explicitModel: Boolean(requestedModel),
    autoModel: tenantDefaultModel || dep?.models?.default,
    outputCapUsdPerMillion: dep?.models?.priceCapUsdPerMillion,
    prices: loadCatalogPrices(),
  });
  if (admission.decision.action === "block") {
    runLock.release();
    return jsonError(429, "limit_exceeded", admission.decision.message, responseHeaders);
  }
  if (admission.model && !premiumNotice) {
    modelId = admission.model;
    houseSessionModel = undefined;
  }
  const guard = createTurnGuard({
    slug: limitSlug,
    guardrails: projectedGuardrails(limitConfig, limitGuardrails),
    foundryMaxToolCalls: foundryAlias,
    userId: ownerUserSub,
    ip: clientIp,
    ...(admission.summarize ? { summarize: { notice: admission.summarize.notice } } : {}),
  });
  const recordLimitUsage = guard.recordUsage.bind(guard);
  guard.recordUsage = (usage) => {
    recordLimitUsage(usage);
    admission.record(usage, modelId);
  };

  if (adapter.protocol === "foundry-responses" && isFoundryConfig(backend)) {
    const foundryBackend = backend;
    let foundryRes: Response;
    try {
      foundryRes = await createFoundryStreamResponse({
        projectEndpoint: foundryBackend.projectEndpoint,
        agentName: foundryBackend.agentName,
        messages,
        conversationId: externalConversation,
        responseHeaders,
        activityDetail,
        signal: req.signal,
        responseLanguage: languageCode,
        turnMode,
        maxToolCalls: guard.toolCap ?? foundryBackend.maxToolCalls,
        reasoningEffort,
        guard,
      });
    } catch (err) {
      runLock.release();
      throw err;
    }
    // JSON 4xx/501 from the adapter are not streams — release immediately.
    if (foundryRes.headers.get("content-type")?.includes("application/json")) {
      runLock.release();
      return foundryRes;
    }
    return finish(foundryRes);
  }

  // Non-AI-SDK backends (#4543): LangGraph / AG-UI / A2A each get their own
  // mapper, dispatched from the adapter's protocol. Placed before the
  // `coreMessages` conversion — these adapters take the UI messages and do
  // their own text mapping, so a conversion failure must not be able to fail
  // a request that would otherwise stream.
  if (NON_AI_SDK_PROTOCOLS.has(adapter.protocol) && isNonAiSdkConfig(backend)) {
    try {
      return finish(
        await createNonAiSdkStreamResponse({
          backend,
          messages,
          responseHeaders,
          activityDetail,
          signal: req.signal,
          guard,
        }),
      );
    } catch (err) {
      runLock.release();
      throw err;
    }
  }

  let coreMessages;
  try {
    coreMessages = await convertToModelMessages(
      uiMessagesForUpstream(messages).map((m) => {
        const { id: _omit, ...rest } = m;
        void _omit;
        return rest;
      }) as Omit<UIMessage, "id">[],
      { ignoreIncompleteToolCalls: true },
    );
  } catch (err) {
    runLock.release();
    throw err;
  }

  // Opt-in web search (#3420): client must ask AND tenant/env must allow.
  // Never forward on a silent default — corpus-only unless both gates pass.
  // Computed here so the AI-SDK backends (#4552) can pass their provider's
  // built-in search tool under the SAME gate the digigraph header below uses.
  // An embed tenant is authoritative for itself; on the session path the
  // deployment config decides, with `DIGICHAT_WEB_SEARCH` kept as the
  // documented fallback for installs that never set `gate.webSearch` (#4552).
  const clientWantsWeb =
    (req.headers.get("x-digi-enable-web-search") || "").trim().toLowerCase() === "1" ||
    (req.headers.get("x-digi-enable-web-search") || "").trim().toLowerCase() === "true";
  const tenantAllowsWeb = embedConfig
    ? embedConfig.webSearch === true
    : dep?.gate.webSearch === true || process.env.DIGICHAT_WEB_SEARCH === "1";
  const webSearchEnabled = clientWantsWeb && tenantAllowsWeb;

  // AI-SDK backends (#4535): OpenAI Completions / Responses run through one
  // `streamText` mapper. Sits after `coreMessages` (already built) and before
  // the BYOK guard, so foundry/digigraph behaviour is untouched and BYOK stays
  // a digigraph-only concern — the AI-SDK credential is the configured env key.
  if (AI_SDK_PROTOCOLS.has(adapter.protocol) && isAiSdkConfig(backend)) {
    try {
      return finish(
        await createAiSdkStreamResponse({
          backend,
          messages: coreMessages,
          responseHeaders,
          webSearch: webSearchEnabled,
          signal: req.signal,
          guard,
        }),
      );
    } catch (err) {
      runLock.release();
      throw err;
    }
  }

  // Non-OpenAI BYOK requires a model slug before forwarding to digigraph.
  const byokNeedsModel = byokRequiresModel(byokProvider);
  if (byokKey && byokNeedsModel && !byokModel) {
    runLock.release();
    return new Response(
      JSON.stringify({
        error: "byok_model_required",
        message: `${byokProvider} BYOK requires X-BYOK-Model (e.g. ${byokModelExample(byokProvider) ?? "your provider's model id"}).`,
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
    // The upstream exchange failed before any turn was produced, so the run id
    // must not refuse the retry: the client replays the same X-Digi-Run-Id
    // when it repeats the send, and the cold case is answered with a
    // Retry-After (DIG-4424).
    runLock.release({ forgetRunId: true });
    if (e instanceof DigigraphUpstreamUnavailableError) {
      // digikey was cold, asleep or down: the request is retryable, so it is
      // answered 503 with a Retry-After and NOT as an upstream_auth failure.
      // A 502 upstream_auth here told the operator to check the token for a
      // dependency that was only asleep (DIG-4424).
      return new Response(
        JSON.stringify({ error: "upstream_unavailable", message: e.message }),
        {
          status: 503,
          headers: {
            "content-type": "application/json",
            "retry-after": String(DIGIKEY_UNAVAILABLE_RETRY_AFTER_SECONDS),
          },
        }
      );
    }
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

  const model = provider(modelId);

  const upstreamHeaders: Record<string, string> = {
    "X-Session-Id": sessionId,
    "X-Request-ID": rid,
    "X-Digichat-Tenant": tenantSlug,
    "X-Digi-Tenant": tenantSlug,
    "X-Digi-Caller": "digichat",
    Authorization: `Bearer ${upstreamBearer}`,
  };
  if (adapter.capabilities.corpus && isDigigraphConfig(backend)) {
    const digigraphBackend = backend;
    if (digigraphBackend.digisearchIndex) {
      upstreamHeaders["X-Digi-Corpus-Index"] = digigraphBackend.digisearchIndex;
    }
    if (digigraphBackend.vaultPathPrefix) {
      upstreamHeaders["X-Digi-Vault-Prefix"] = digigraphBackend.vaultPathPrefix;
    }
  }
  if (litellmProxyApiKey) {
    upstreamHeaders["X-LiteLLM-Proxy-Key"] = litellmProxyApiKey;
  }
  if (languageCode !== "en") {
    upstreamHeaders["X-Digi-Language"] = languageCode;
  }
  if (reasoningEffort) {
    upstreamHeaders["X-Digi-Effort"] = reasoningEffort;
  }
  // Search engine choice for digisearch web_search (#4724): allowlisted names
  // only, unknown/blank dropped. "auto" is the hub default, so it is omitted
  // rather than forwarded. Effective engine is the browser choice, else the
  // tenant default from dep.gate.searchEngine (engine NAME only, never keys);
  // an explicit browser "auto" beats a tenant default via omission.
  const engineRaw = (req.headers.get("x-digi-search-engine") || "").trim().toLowerCase();
  const tenantEngineRaw = (dep?.gate?.searchEngine || "").trim().toLowerCase();
  const isEngineName = (v: string) =>
    v === "auto" ||
    v === "internal" ||
    v === "exa" ||
    v === "tavily" ||
    v === "parallel" ||
    v === "firecrawl" ||
    v === "tinyfish";
  const browserEngine = isEngineName(engineRaw) ? engineRaw : undefined;
  const tenantEngine =
    tenantEngineRaw !== "auto" && isEngineName(tenantEngineRaw) ? tenantEngineRaw : undefined;
  const effectiveEngine = browserEngine === "auto" ? undefined : (browserEngine ?? tenantEngine);
  if (effectiveEngine) {
    upstreamHeaders["X-Digi-Search-Engine"] = effectiveEngine;
  }
  // X-Digi-Force-Tool is send-only — ignore leftover slash force on regen/edit (#3475).
  // Session X-Digi-Disabled-Tools still forwards on Redo / edit (#3735 review).
  // Catalog allowlist from deployment config is source of truth (fail closed).
  // Operator MCP URLs come only from YAML — never from the browser (#3736).
  const forceToolRaw = req.headers.get("x-digi-force-tool")?.trim();
  const disabledToolsRaw = req.headers.get("x-digi-disabled-tools")?.trim();
  try {
    const {
      filterForceToolHeader,
      filterDisabledToolsHeader,
      omitForcedCatalogIds,
      mcpServersHeaderValue,
      operatorMcpServersForUpstream,
      parseMcpSessionOverlay,
      mergeMcpSessionOverlay,
      mcpUpstreamHeaderValue,
    } = await import("@/lib/deploy-config");
    // `dep` is resolved once at the top of the handler.
    const operator = operatorMcpServersForUpstream(dep);
    const overlay = parseMcpSessionOverlay(req.headers.get("x-digi-mcp-session"));
    const merged = mergeMcpSessionOverlay({
      operator,
      overlay,
      allowSessionUrls: dep?.mcp?.allowUserServers === true,
    });
    const mcpHeader = mcpUpstreamHeaderValue(merged) ?? mcpServersHeaderValue(dep);
    if (mcpHeader) {
      upstreamHeaders["X-Digi-Mcp-Servers"] = mcpHeader;
    }
    const allowed =
      forceToolRaw && !isMutatingTurnMode(turnMode)
        ? filterForceToolHeader(dep, forceToolRaw)
        : undefined;
    if (allowed) upstreamHeaders["X-Digi-Force-Tool"] = allowed;
    const disabled = omitForcedCatalogIds(
      filterDisabledToolsHeader(dep, disabledToolsRaw),
      allowed,
    );
    // Forward catalog ids as-is (#3807): digigraph `expand_disabled_tool_tokens`
    // expands digisearch/digivault aliases upstream. Do not expand to tool
    // names here — that would break the upstream contract.
    if (disabled.length) {
      upstreamHeaders["X-Digi-Disabled-Tools"] = disabled.join(",");
    }
  } catch {
    // Invalid deploy config — do not forward force-tool / disabled-tools / MCP.
  }

  // The web-search gate itself is computed above, shared with the AI-SDK
  // backends (#4552); only the digigraph upstream header is written here.
  if (webSearchEnabled) {
    upstreamHeaders["X-Digi-Enable-Web-Search"] = "1";
  }

  // Forward the container's in-memory license JWT so digigraph can enforce
  // hosted scopes (spec §7.1); unlicensed containers omit the header.
  const licenseJwt = getHeartbeatContext().rawJwt;
  if (licenseJwt) {
    upstreamHeaders["X-Digi-License"] = licenseJwt;
  }

  // BYOK: forward per-request key to digigraph; never log or persist.
  if (!byokKey && houseSessionModel) {
    upstreamHeaders["X-Digi-House-Model"] = houseSessionModel;
    if (routerModels) upstreamHeaders["X-Digi-Router-Models"] = routerModels;
  }
  if (!byokKey && dep?.models) {
    const premiumHeader = premiumModelsHeader(dep.models);
    if (premiumHeader) upstreamHeaders["X-Digi-Premium-Models"] = premiumHeader;
  }
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
    try {
      return finish(
        await createDigigraphTraceStreamResponse({
          messages,
          digigraphBaseUrl: eco.digigraphUrl ?? "",
          upstreamHeaders,
          responseHeaders,
          activityDetail,
          // BYOK models travel in their own header; only the house model
          // belongs in the request body. `modelId` is the pick (when the
          // tenant curates a list) or the curated default.
          model: byokKey ? undefined : modelId,
          signal: req.signal,
          preface: premiumNotice,
          onUsage: chargePremium,
          guard,
        }),
      );
    } catch (err) {
      runLock.release();
      throw err;
    }
  }

  if (chargePremium) chargePremium();

  if (guard.active) {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        try {
          if (premiumNotice) {
            const textId = "premium-fallback";
            writer.write({ type: "text-start", id: textId });
            writer.write({
              type: "text-delta",
              id: textId,
              delta: `${premiumNotice}\n\n`,
            });
            writer.write({ type: "text-end", id: textId });
          }
          const result = streamText({
            model,
            messages: coreMessages,
            headers: upstreamHeaders,
            abortSignal: req.signal,
            experimental_transform: smoothStream({ chunking: "word" }),
            prepareStep: (step) =>
              guardrailPrepareStep({
                guard,
                writer,
                signal: req.signal,
                steps: step.steps,
                messages: step.messages,
                initialInstructions:
                  typeof step.initialInstructions === "string"
                    ? step.initialInstructions
                    : undefined,
              }),
            onFinish: (event) => {
              guard.recordUsage(event.usage);
            },
          });
          writer.merge(
            toUIMessageStream({
              stream: result.stream,
              sendSources: true,
              sendReasoning: true,
            }),
          );
        } catch (err) {
          guard.release();
          throw err;
        }
      },
      onFinish: () => {
        guard.release();
      },
    });
    return finish(
      createUIMessageStreamResponse({
        stream,
        headers: responseHeaders,
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

  const modelStream = toUIMessageStream({
    stream: result.stream,
    sendSources: true,
    sendReasoning: true,
  });
  const stream = premiumNotice
    ? createUIMessageStream({
        execute({ writer }) {
          const textId = "premium-fallback";
          writer.write({ type: "text-start", id: textId });
          writer.write({
            type: "text-delta",
            id: textId,
            delta: `${premiumNotice}\n\n`,
          });
          writer.write({ type: "text-end", id: textId });
          writer.merge(modelStream);
        },
      })
    : modelStream;

  return finish(
    createUIMessageStreamResponse({
      stream,
      headers: responseHeaders,
    }),
  );
}
