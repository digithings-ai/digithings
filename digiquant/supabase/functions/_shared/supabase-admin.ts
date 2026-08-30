/**
 * Service-role Supabase admin client for billing Edge Functions (T2).
 *
 * Uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (injected by the Edge Runtime).
 * Never log or return the service role key.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type AdminClient = SupabaseClient;

export function createAdminClient(
  getEnv: (key: string) => string | undefined = (k) => Deno.env.get(k),
): AdminClient {
  const url = getEnv("SUPABASE_URL") ?? getEnv("CORE_SUPABASE_URL");
  const key = getEnv("SUPABASE_SERVICE_ROLE_KEY") ?? getEnv("CORE_SUPABASE_SERVICE_KEY");
  if (!url || !key) {
    throw new Error("Supabase admin env not configured");
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export interface WorkspaceRow {
  id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_status: string;
  plan_tier: string;
  claim_sync_pending: boolean;
  last_stripe_event_created: number | null;
}

export interface MemberRow {
  user_id: string;
  role: string;
}

export interface StripeEventRow {
  stripe_event_id: string;
  event_type: string;
  workspace_id: string | null;
  payload: Record<string, unknown> | null;
  applied_at: string | null;
}

/** Stable JSON error body — never include stack traces or secrets. */
export function jsonError(
  status: number,
  code: string,
  message: string,
): Response {
  return new Response(JSON.stringify({ code, message }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function jsonOk(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Resolve the caller's primary workspace via workspace_members.
 * Prefers an `owner` row; otherwise the earliest membership.
 */
export async function resolveCallerWorkspace(
  admin: AdminClient,
  userId: string,
): Promise<{ workspace: WorkspaceRow; role: string } | null> {
  const { data, error } = await admin
    .from("workspace_members")
    .select(
      "role, workspace_id, workspaces!inner(id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending, last_stripe_event_created)",
    )
    .eq("user_id", userId);
  if (error || !data || data.length === 0) {
    return null;
  }
  type JoinRow = {
    role: string;
    workspace_id: string;
    workspaces: WorkspaceRow | WorkspaceRow[];
  };
  const rows = data as unknown as JoinRow[];
  const normalized = rows.map((r) => {
    const ws = Array.isArray(r.workspaces) ? r.workspaces[0] : r.workspaces;
    return { role: r.role, workspace: ws };
  }).filter((r) => r.workspace != null);
  if (normalized.length === 0) return null;
  const owner = normalized.find((r) => r.role === "owner");
  return owner ?? normalized[0]!;
}

export async function listWorkspaceMembers(
  admin: AdminClient,
  workspaceId: string,
): Promise<MemberRow[]> {
  const { data, error } = await admin
    .from("workspace_members")
    .select("user_id, role")
    .eq("workspace_id", workspaceId);
  if (error || !data) return [];
  return data as MemberRow[];
}

/**
 * Sync plan_tier into auth.users.app_metadata for every workspace member.
 * Returns false if any update fails (caller should set claim_sync_pending).
 * Auth updates are last in the webhook apply path — see T2 binding #3.
 */
export async function syncPlanTierClaims(
  admin: AdminClient,
  memberUserIds: string[],
  planTier: string,
): Promise<boolean> {
  let ok = true;
  for (const userId of memberUserIds) {
    try {
      const { data: userData, error: getErr } = await admin.auth.admin.getUserById(userId);
      if (getErr || !userData?.user) {
        ok = false;
        continue;
      }
      const prev = (userData.user.app_metadata ?? {}) as Record<string, unknown>;
      const { error: updErr } = await admin.auth.admin.updateUserById(userId, {
        app_metadata: { ...prev, plan_tier: planTier },
      });
      if (updErr) ok = false;
    } catch {
      // Never rethrow — claim sync failure must not 5xx Stripe.
      ok = false;
    }
  }
  return ok;
}

export type InsertStripeEventResult =
  | { status: "inserted" }
  | { status: "duplicate_applied" }
  | { status: "duplicate_pending" }
  | { status: "error" };

/**
 * Insert stripe_events with applied_at NULL.
 * On PK conflict: look up the row — already-applied ⇒ no-op; pending ⇒ re-apply.
 */
export async function insertStripeEvent(
  admin: AdminClient,
  args: {
    stripeEventId: string;
    eventType: string;
    workspaceId: string | null;
    payload: Record<string, unknown>;
  },
): Promise<InsertStripeEventResult> {
  const { error } = await admin.from("stripe_events").insert({
    stripe_event_id: args.stripeEventId,
    event_type: args.eventType.slice(0, 100),
    workspace_id: args.workspaceId,
    payload: args.payload,
    applied_at: null,
  });
  if (!error) return { status: "inserted" };

  const msg = (error.message ?? "").toLowerCase();
  const code = (error as { code?: string }).code ?? "";
  if (!(code === "23505" || msg.includes("duplicate") || msg.includes("unique"))) {
    return { status: "error" };
  }

  const existing = await getStripeEvent(admin, args.stripeEventId);
  if (!existing) return { status: "error" };
  if (existing.applied_at != null) return { status: "duplicate_applied" };
  return { status: "duplicate_pending" };
}

export async function getStripeEvent(
  admin: AdminClient,
  stripeEventId: string,
): Promise<StripeEventRow | null> {
  const { data, error } = await admin
    .from("stripe_events")
    .select("stripe_event_id, event_type, workspace_id, payload, applied_at")
    .eq("stripe_event_id", stripeEventId)
    .maybeSingle();
  if (error || !data) return null;
  return data as StripeEventRow;
}

/** Mark an event applied after a successful (or deliberately no-op) apply path. */
export async function markStripeEventApplied(
  admin: AdminClient,
  stripeEventId: string,
): Promise<void> {
  const { error } = await admin
    .from("stripe_events")
    .update({ applied_at: new Date().toISOString() })
    .eq("stripe_event_id", stripeEventId)
    .is("applied_at", null);
  if (error) {
    throw new Error("stripe_events applied_at update failed");
  }
}

/**
 * CAS billing write: update workspace columns only if this event is newer than
 * `last_stripe_event_created`. Returns false when zero rows matched (stale).
 * Propagates PostgREST errors as throws (500-retryable; applied_at stays NULL).
 */
export async function casUpdateWorkspaceBilling(
  admin: AdminClient,
  workspaceId: string,
  eventCreated: number,
  patch: Record<string, unknown>,
): Promise<boolean> {
  const { data, error } = await admin
    .from("workspaces")
    .update({
      ...patch,
      last_stripe_event_created: eventCreated,
    })
    .eq("id", workspaceId)
    .or(
      `last_stripe_event_created.is.null,last_stripe_event_created.lt.${eventCreated}`,
    )
    .select("id");
  if (error) {
    throw new Error("workspaces CAS update failed");
  }
  return Array.isArray(data) && data.length > 0;
}
