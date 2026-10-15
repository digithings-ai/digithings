/**
 * Art. 9 transcript screening hop for the conversation write path (DIG-1178 leaf 12d).
 *
 * The `PUT /api/conversations/[id]` handler calls {@link screenConversationWrite}
 * after the request body is parsed and validated and before any database handle
 * exists. A conversation that trips a screening category is never written to
 * `conversation_messages.payload`.
 *
 * Fail-closed: the write proceeds only on a `200` whose body carries
 * `decision == "allow"`. Every other outcome — policy refusal (including
 * `mask`, for which v1 has no lawful basis to store a transcript), oversized
 * payload, hop failure, transport error, missing configuration — refuses the
 * write. Single attempt, no retry.
 *
 * URL resolution reads `process.env.DIGISEARCH_INTERNAL_URL` ONLY. It never
 * reads `digisearchUrl` from the capability object (which
 * `withDigisearchCapability()` deletes when the digisearch *feature* is off)
 * and never reads the `digichat-endpoints` cookie (which is
 * tenant-influenced). A filter that quietly turns itself off is worse than no
 * filter, so neither alternate source is consulted on any path.
 *
 * The outgoing request carries no tenant, no `ownerUserSub`, no client name,
 * and no message content beyond the `{ surface, conversation_id, messages }`
 * the screener needs. Refusals are logged with category ids and the stable
 * reason code only — never the screened payload.
 */

import { resolveDigigraphUpstreamAuth } from "@/lib/digigraph-upstream";

export const ART9_SCREEN_PATH = "/internal/art9/screen";
export const ART9_SURFACE = "digichat";

export const CODE_REFUSED = "art9_refused";
export const CODE_UNAVAILABLE = "art9_screen_unavailable";

export type ScreenVerdict =
  | { allowed: true }
  | {
      allowed: false;
      /** Stable machine code: `art9_refused` (policy, incl. mask) or `art9_screen_unavailable`. */
      code: string;
      /** Category identifiers only — never a matched value. */
      categories: string[];
      /** Stable `art9:<category>:<signal>` reason code, never the value. */
      reason: string;
    };

/**
 * Resolve the screening base URL from the environment only. Returns `null`
 * when unconfigured so the caller fails closed. Never consults the capability
 * object or the endpoints cookie (see module docstring).
 */
export function resolveScreenBaseUrl(): string | null {
  const raw = process.env.DIGISEARCH_INTERNAL_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/$/, "");
}

function refused(
  code: string,
  categories: string[] = [],
  reason: string = code
): Extract<ScreenVerdict, { allowed: false }> {
  return { allowed: false, code, categories, reason };
}

function logRefusal(v: Extract<ScreenVerdict, { allowed: false }>): void {
  // Category ids and reason code only. The screened transcript is never logged.
  console.warn(
    `[art9-screen] refused code=${v.code} categories=${v.categories.join(",")} reason=${v.reason}`
  );
}

/**
 * Screen one validated transcript before it reaches storage.
 *
 * Fail-closed on every path: unconfigured URL, failed upstream auth exchange,
 * transport error, non-200 status, unparseable body, or any decision other
 * than `"allow"` (including `"mask"`) all refuse the write.
 */
export async function screenConversationWrite(args: {
  req: Request;
  tenantSlug: string;
  ownerUserSub: string;
  conversationId: string;
  messages: unknown[];
}): Promise<ScreenVerdict> {
  const base = resolveScreenBaseUrl();
  if (!base) {
    const v = refused(CODE_UNAVAILABLE);
    logRefusal(v);
    return v;
  }

  let bearer: string;
  try {
    const up = await resolveDigigraphUpstreamAuth(
      args.req,
      args.tenantSlug,
      args.ownerUserSub
    );
    bearer = up.bearer;
  } catch {
    const v = refused(CODE_UNAVAILABLE);
    logRefusal(v);
    return v;
  }

  let res: Response;
  try {
    res = await fetch(`${base}${ART9_SCREEN_PATH}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        Authorization: `Bearer ${bearer}`,
      },
      body: JSON.stringify({
        surface: ART9_SURFACE,
        conversation_id: args.conversationId,
        messages: args.messages,
      }),
    });
  } catch {
    const v = refused(CODE_UNAVAILABLE);
    logRefusal(v);
    return v;
  }

  let data: Record<string, unknown> | null = null;
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    data = null;
  }

  if (res.ok && data?.decision === "allow") {
    return { allowed: true };
  }

  const categories = Array.isArray(data?.categories)
    ? (data.categories as unknown[]).filter(
        (c): c is string => typeof c === "string"
      )
    : [];
  const reason =
    typeof data?.reason === "string" ? data.reason : CODE_UNAVAILABLE;
  const code =
    res.status === 422 || data?.decision === "mask" || data?.decision === "refuse"
      ? CODE_REFUSED
      : CODE_UNAVAILABLE;
  const v = refused(code, categories, reason);
  logRefusal(v);
  return v;
}
