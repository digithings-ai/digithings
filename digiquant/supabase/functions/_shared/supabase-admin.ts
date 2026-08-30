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
}

export interface MemberRow {
  user_id: string;
  role: string;
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
    .select("role, workspace_id, workspaces!inner(id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending)")
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

/**
 * Insert stripe_events row. Returns:
 *   - "inserted" on success
 *   - "duplicate" on unique violation (idempotent no-op)
 *   - "error" on other failures
 */
export async function insertStripeEvent(
  admin: AdminClient,
  args: {
    stripeEventId: string;
    eventType: string;
    workspaceId: string | null;
    payload: Record<string, unknown>;
  },
): Promise<"inserted" | "duplicate" | "error"> {
  const { error } = await admin.from("stripe_events").insert({
    stripe_event_id: args.stripeEventId,
    event_type: args.eventType.slice(0, 100),
    workspace_id: args.workspaceId,
    payload: args.payload,
  });
  if (!error) return "inserted";
  const msg = (error.message ?? "").toLowerCase();
  const code = (error as { code?: string }).code ?? "";
  if (code === "23505" || msg.includes("duplicate") || msg.includes("unique")) {
    return "duplicate";
  }
  return "error";
}

/**
 * Max Stripe event `created` previously applied for this subscription / workspace.
 * Used for the out-of-order guard (T2 binding #1).
 */
export async function maxAppliedEventCreated(
  admin: AdminClient,
  args: {
    workspaceId: string | null;
    subscriptionId: string | null;
    excludeEventId: string;
  },
): Promise<number> {
  // Prefer workspace-scoped history; fall back to scanning recent events when
  // workspace is not yet attached (first checkout).
  let query = admin
    .from("stripe_events")
    .select("stripe_event_id, payload")
    .neq("stripe_event_id", args.excludeEventId)
    .order("processed_at", { ascending: false })
    .limit(50);
  if (args.workspaceId) {
    query = query.eq("workspace_id", args.workspaceId);
  }
  const { data, error } = await query;
  if (error || !data) return 0;
  let maxCreated = 0;
  for (const row of data as Array<{ stripe_event_id: string; payload: Record<string, unknown> | null }>) {
    const payload = row.payload ?? {};
    const created = typeof payload.created === "number" ? payload.created : 0;
    const subId = typeof payload.subscription_id === "string" ? payload.subscription_id : null;
    if (args.subscriptionId && subId && subId !== args.subscriptionId) continue;
    if (created > maxCreated) maxCreated = created;
  }
  return maxCreated;
}
