/**
 * POST /api/chat/approve — forward a human decision about a pending MCP tool call.
 *
 * This is the human half of 284.5. digigraph decides *whether* a tool call
 * suspends (284.4's brake, `_requires_human_approval`) and records the payload it
 * would run in a process-local pending store under an opaque id. This route does
 * exactly three things:
 *
 *   1. names nothing — it accepts the opaque pending id and a verdict, and
 *   2. forwards both to digigraph for the session that raised it, and
 *   3. returns whatever digigraph decided.
 *
 * D3 (plan §2): digigraph executes the payload it already recorded. This request
 * is therefore *incapable* of overriding it — there is no parameter here for a
 * tool name or for arguments, and `UNSUPPORTED_BODY_KEYS` rejects any body that
 * tries to smuggle one. The same holds for the operator-owned MCP config keys
 * (`url`, `authHeader`, `allowedTools`, `mutatingTools`): they are refused by name
 * so a caller cannot reach the trust boundary that 284.2 put behind the
 * operator-only allowlist.
 *
 * D2 (plan §2) and brief fact 3: the decision is a *separate request for the same
 * session*, never a second turn through `/api/chat`. The confirm suspends the turn
 * rather than re-entering it, because LangGraph's `interrupt_after` silently drops
 * the resume value. Do not "simplify" this into a chat resend.
 *
 * The session is read from the header, never the body: `pending_mcp_decision` in
 * digigraph is keyed `(session_id, pending_id)`, so passing the session is what
 * makes a pending id belonging to another session fail closed upstream instead of
 * being decided here.
 *
 * UPSTREAM CONTRACT — not yet implemented on digigraph (284.6, owner's recorded
 * finding F1: `decide_mcp_call` had no production caller). This route defines the
 * contract; `DIGIGRAPH_MCP_DECISION_PATH` is exported so 284.6 targets exactly this
 * path with exactly this body and these headers. Until then the upstream answers
 * 404 and this route surfaces `decision_upstream_unavailable` (502) rather than
 * reporting a decision that was not recorded.
 */
import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveChatTenantContext } from "@/lib/chat-route-context";
import { licenseRefusal } from "@/lib/license/state";
import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import {
  DigigraphUpstreamAuthError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";

export const runtime = "nodejs";

/** Path on digigraph that consumes a decision. Implemented by 284.6. */
export const DIGIGRAPH_MCP_DECISION_PATH = "/v1/mcp/decisions";

/** The only keys this route reads. Everything else is refused by name. */
export const ALLOWED_BODY_KEYS = ["pendingId", "decision"] as const;

/**
 * Operator-owned MCP configuration (284.2). Reaching these through a *client*
 * request would turn a decision endpoint into a config endpoint, so they are
 * refused with their own error code rather than folded into the generic one.
 */
export const OPERATOR_ONLY_BODY_KEYS = [
  "url",
  "authHeader",
  "allowedTools",
  "mutatingTools",
] as const;

/** Anything a human may be asked to agree to is named; anything else is refused. */
export const DECISIONS = ["approve", "deny"] as const;
export type Decision = (typeof DECISIONS)[number];

const SUPPORTED_BODY_KEYS: readonly string[] = [...ALLOWED_BODY_KEYS];
const OPERATOR_ONLY_KEYS: readonly string[] = [...OPERATOR_ONLY_BODY_KEYS];

/** Opaque id digigraph minted with `secrets.token_hex(16)`. Shape-checked, not trusted. */
const PENDING_ID_RE = /^[0-9a-f]{16,64}$/;

function jsonError(status: number, code: string, message: string, extra?: Record<string, unknown>) {
  return new Response(JSON.stringify({ error: code, message, ...extra }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function rateLimitResponse(retryAfterSec: number) {
  return new Response(
    JSON.stringify({ error: "rate_limited", message: "Too many decisions. Try again shortly." }),
    {
      status: 429,
      headers: { "content-type": "application/json", "retry-after": String(retryAfterSec) },
    }
  );
}

/**
 * Validate the body as a closed set. Extra keys are a *named* refusal, never a
 * silent ignore: an ignored `arguments` field would make the gate look enforced
 * while the caller's intent was actually discarded.
 */
export function validateDecisionBody(
  raw: unknown
): { ok: true; value: { pendingId: string; decision: Decision } } | { ok: false; response: Response } {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {
      ok: false,
      response: jsonError(400, "invalid_body", "Body must be a JSON object."),
    };
  }
  const body = raw as Record<string, unknown>;
  const keys = Object.keys(body);
  const operatorOnly = keys.filter((k) => OPERATOR_ONLY_KEYS.includes(k));
  if (operatorOnly.length) {
    return {
      ok: false,
      response: jsonError(
        403,
        "operator_only_field",
        "These fields are operator-owned and cannot be set by a client request.",
        { fields: operatorOnly.sort() }
      ),
    };
  }
  const unsupported = keys.filter((k) => !SUPPORTED_BODY_KEYS.includes(k));
  if (unsupported.length) {
    return {
      ok: false,
      response: jsonError(
        400,
        "unsupported_field",
        `This endpoint accepts only ${ALLOWED_BODY_KEYS.join(" and ")}. ` +
          "A decision carries the pending id and the verdict, nothing else.",
        { fields: unsupported.sort() }
      ),
    };
  }
  const pendingId = body.pendingId;
  if (typeof pendingId !== "string" || !PENDING_ID_RE.test(pendingId)) {
    return {
      ok: false,
      response: jsonError(400, "invalid_pending_id", "pendingId must be the opaque id digigraph issued."),
    };
  }
  const decision = body.decision;
  if (typeof decision !== "string" || !DECISIONS.includes(decision as Decision)) {
    return {
      ok: false,
      response: jsonError(
        400,
        "invalid_decision",
        `decision must be one of: ${DECISIONS.join(", ")}.`
      ),
    };
  }
  return { ok: true, value: { pendingId, decision: decision as Decision } };
}

/** Same session resolution as `/api/chat`, so a decision reaches the turn that raised it. */
function sessionIdOf(req: Request): string {
  return req.headers.get("x-digichat-session") ?? req.headers.get("x-session-id") ?? "";
}

export async function POST(req: Request): Promise<Response> {
  const refusal = licenseRefusal();
  if (refusal) return refusal;

  const authResult = await requireDigiChatAuth(req);
  if (authResult instanceof Response) return authResult;
  const tenantCtx = await resolveChatTenantContext(req, authResult);
  if (tenantCtx instanceof Response) return tenantCtx;
  const { tenantSlug, ownerUserSub } = tenantCtx;

  const sessionId = sessionIdOf(req);
  if (!sessionId) {
    return jsonError(
      400,
      "session_required",
      "Send the session header (x-digichat-session) that raised the pending decision."
    );
  }

  const rate = checkBffRateLimit(`chat-decision:${tenantSlug}:${ownerUserSub}`);
  if (!rate.allowed) return rateLimitResponse(rate.retryAfterSec ?? 30);

  let parsedBody: unknown;
  try {
    parsedBody = await req.json();
  } catch {
    return jsonError(400, "invalid_json", "Body must be valid JSON.");
  }
  const validated = validateDecisionBody(parsedBody);
  if (!validated.ok) return validated.response;
  const { pendingId, decision } = validated.value;

  const eco = await getEcosystemEndpoints();
  let upstreamBearer: string;
  try {
    const up = await resolveDigigraphUpstreamAuth(req, tenantSlug, ownerUserSub);
    upstreamBearer = up.bearer;
  } catch (err) {
    if (err instanceof DigigraphUpstreamAuthError) {
      return jsonError(401, "upstream_auth_failed", "Could not authenticate to digigraph.");
    }
    throw err;
  }

  const target = `${eco.digigraphUrl.replace(/\/+$/, "")}${DIGIGRAPH_MCP_DECISION_PATH}`;
  const upstreamRes = await fetch(target, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Session-Id": sessionId,
      "X-Digichat-Tenant": tenantSlug,
      "X-Digi-Tenant": tenantSlug,
      "X-Digi-Caller": "digichat",
      Authorization: `Bearer ${upstreamBearer}`,
    },
    // The whole payload: an id and a verdict. digigraph runs what it recorded.
    body: JSON.stringify({ pending_id: pendingId, approve: decision === "approve" }),
  });

  if (upstreamRes.status === 404) {
    return jsonError(
      502,
      "decision_upstream_unavailable",
      "digigraph has no decision endpoint yet (284.6). No decision was recorded."
    );
  }
  if (!upstreamRes.ok) {
    return jsonError(502, "decision_upstream_failed", "digigraph did not record the decision.");
  }

  const decided = (await upstreamRes.json()) as { status?: string };
  if (decided?.status !== "approved" && decided?.status !== "denied") {
    return jsonError(502, "decision_upstream_failed", "digigraph returned an unexpected decision.");
  }

  return new Response(JSON.stringify(decided), {
    status: 200,
    headers: { "content-type": "application/json", "X-Digichat-Session": sessionId },
  });
}
