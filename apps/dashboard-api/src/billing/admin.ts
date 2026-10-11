/**
 * Billing data access.
 *
 * The edge functions reached Supabase through `SupabaseClient` from
 * `@supabase/supabase-js`. That dependency does not exist in this worker
 * (`src/supabase.ts` already talks to PostgREST with plain `fetch` and `env`),
 * so the port deliberately does NOT vendor a query-builder client.
 *
 * It defines `AdminDb` — the narrow set of operations the three billing routes
 * and the webhook handler actually perform — and one PostgREST-over-`fetch`
 * implementation. Every semantic the edge version relied on is preserved
 * explicitly:
 *
 *  - the `ensure_personal_workspace` RPC still owns workspace creation; the
 *    port never invents membership client-side;
 *  - `insertStripeEvent` still returns the four-state result, still detects a
 *    duplicate by Postgres `23505` OR a duplicate/unique message, and still
 *    re-reads the row to distinguish `duplicate_applied` from
 *    `duplicate_pending`;
 *  - `casUpdateWorkspaceBilling` still only writes when
 *    `last_stripe_event_created` is null or older, and returns `false` for a
 *    stale write rather than throwing — that is the out-of-order guard, and it
 *    is why an older Stripe event can never roll a newer plan back;
 *  - `syncPlanTierClaims` still never rethrows: a failed claim sync must not
 *    turn a 200 into a 5xx and make Stripe retry.
 *
 * Supabase stays live and untouched (2-week rollback). This module is the only
 * thing that talks to it, so a later D1-backed leaf replaces this file and
 * leaves every handler untouched.
 */

import { envFirst, type BillingEnv } from "./env";

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

export type InsertStripeEventResult =
  | { status: "inserted" }
  | { status: "duplicate_applied" }
  | { status: "duplicate_pending" }
  | { status: "error"; reason?: string };

export type WorkspaceLookup = "id" | "stripe_subscription_id" | "stripe_customer_id";

export interface CallerWorkspace {
  workspace: WorkspaceRow;
  role: string;
}

export interface AdminDb {
  /** Membership + inner-joined workspace for a user; null when not found. */
  resolveCallerWorkspace(userId: string): Promise<CallerWorkspace | null>;
  /** Creates the personal workspace via RPC when absent; null on failure. */
  ensureCallerWorkspace(userId: string): Promise<CallerWorkspace | null>;
  getWorkspaceBy(lookup: WorkspaceLookup, value: string): Promise<WorkspaceRow | null>;
  listWorkspaceMembers(workspaceId: string): Promise<MemberRow[]>;
  syncPlanTierClaims(userIds: string[], planTier: string): Promise<boolean>;
  insertStripeEvent(args: {
    stripeEventId: string;
    eventType: string;
    workspaceId: string | null;
    payload: Record<string, unknown>;
  }): Promise<InsertStripeEventResult>;
  getStripeEvent(stripeEventId: string): Promise<StripeEventRow | null>;
  markStripeEventApplied(stripeEventId: string): Promise<void>;
  /** Returns false when the write was skipped as stale (out-of-order event). */
  casUpdateWorkspaceBilling(
    workspaceId: string,
    eventCreated: number,
    patch: Partial<WorkspaceRow>,
  ): Promise<boolean>;
  setClaimSyncPending(workspaceId: string, pending: boolean): Promise<void>;
}

export class AdminNotConfiguredError extends Error {
  constructor() {
    super("Supabase admin env not configured");
    this.name = "AdminNotConfiguredError";
  }
}

const WORKSPACE_COLUMNS =
  "id,stripe_customer_id,stripe_subscription_id,subscription_status,plan_tier,claim_sync_pending,last_stripe_event_created";

export function supabaseBase(env: BillingEnv): { url: string; serviceKey: string; anonKey: string } {
  const url = envFirst(env, ["SUPABASE_URL", "CORE_SUPABASE_URL"]);
  const serviceKey = envFirst(env, ["SUPABASE_SERVICE_ROLE_KEY", "CORE_SUPABASE_SERVICE_KEY"]);
  const anonKey = envFirst(env, ["SUPABASE_ANON_KEY", "CORE_SUPABASE_ANON_KEY"]);
  if (!url || !serviceKey || !anonKey) throw new AdminNotConfiguredError();
  return {
    url: url.replace(/\/+$/, ""),
    serviceKey,
    anonKey,
  };
}

function isUniqueViolation(status: number, code: string | null, message: string): boolean {
  if (code === "23505") return true;
  if (status !== 409) return false;
  const lowered = message.toLowerCase();
  return lowered.includes("duplicate") || lowered.includes("unique");
}

export function createPostgrestAdmin(env: BillingEnv): AdminDb {
  const { url, serviceKey } = supabaseBase(env);

  async function rest(
    path: string,
    init: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<{ status: number; code: string | null; message: string; data: unknown }> {
    const headers: Record<string, string> = {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
      ...init.headers,
    };
    const res = await fetch(`${url}/rest/v1/${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    const text = await res.text();
    let data: unknown = null;
    let code: string | null = null;
    let message = text;
    if (text.length > 0) {
      try {
        data = JSON.parse(text);
        if (Array.isArray(data)) {
          code = null;
          message = text;
        } else if (data && typeof data === "object") {
          code = (data as { code?: string }).code ?? null;
          message = (data as { message?: string }).message ?? text;
        }
      } catch {
        data = null;
      }
    }
    return { status: res.status, code, message, data };
  }

  function firstRow(data: unknown): WorkspaceRow | null {
    const row = Array.isArray(data) ? (data[0] as WorkspaceRow | undefined) : undefined;
    return row ?? null;
  }

  return {
    async resolveCallerWorkspace(userId) {
      const res = await rest(
        `workspace_members?select=role,workspaces!inner(${WORKSPACE_COLUMNS})&user_id=eq.${encodeURIComponent(userId)}`,
      );
      if (res.status >= 400) return null;
      const rows = Array.isArray(res.data) ? (res.data as Array<{ role: string; workspaces: unknown }>) : [];
      const normalized = rows
        .map((row) => {
          const ws = Array.isArray(row.workspaces)
            ? (row.workspaces[0] as WorkspaceRow | undefined)
            : (row.workspaces as WorkspaceRow | undefined);
          return ws ? { workspace: ws, role: row.role } : null;
        })
        .filter((v): v is { workspace: WorkspaceRow; role: string } => v !== null);
      if (normalized.length === 0) return null;
      // Prefer an owner membership so a member of someone else's workspace can
      // still manage their own billing, matching the edge version's ordering.
      return normalized.find((row) => row.role === "owner") ?? normalized[0]!;
    },

    async ensureCallerWorkspace(userId) {
      const existing = await this.resolveCallerWorkspace(userId);
      // Return the membership, not the bare row: callers need `role` to tell an
      // owner from a member. Returning `existing.workspace` here drops it and
      // silently demotes every owner to an unauthenticated 403.
      if (existing) return existing;
      const rpc = await rest("rpc/ensure_personal_workspace", {
        method: "POST",
        body: { p_user_id: userId },
      });
      if (rpc.status >= 400) {
        console.error("ensure_personal_workspace failed", rpc.code ?? "unknown");
        return null;
      }
      const reResolved = await this.resolveCallerWorkspace(userId);
      return reResolved ?? null;
    },

    async getWorkspaceBy(lookup, value) {
      const res = await rest(
        `workspaces?select=${WORKSPACE_COLUMNS}&${lookup}=eq.${encodeURIComponent(value)}&limit=1`,
      );
      if (res.status >= 400) return null;
      return firstRow(res.data);
    },

    async listWorkspaceMembers(workspaceId) {
      const res = await rest(
        `workspace_members?select=user_id,role&workspace_id=eq.${encodeURIComponent(workspaceId)}`,
      );
      if (res.status >= 400) return [];
      return Array.isArray(res.data) ? (res.data as MemberRow[]) : [];
    },

    async syncPlanTierClaims(userIds, planTier) {
      let ok = true;
      for (const userId of userIds) {
        // Never rethrow: a claim sync failure must not fail the Stripe webhook.
        try {
          const current = await rest(
            `auth/v1/admin/users/${encodeURIComponent(userId)}`,
            { headers: {} },
          );
          const existing =
            current.data && typeof current.data === "object"
              ? ((current.data as { app_metadata?: Record<string, unknown> }).app_metadata ?? {})
              : {};
          const merged = { ...existing, plan_tier: planTier };
          const update = await fetch(`${url}/auth/v1/admin/users/${encodeURIComponent(userId)}`, {
            method: "PUT",
            headers: {
              apikey: serviceKey,
              Authorization: `Bearer ${serviceKey}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ app_metadata: merged }),
          });
          if (!update.ok) ok = false;
        } catch {
          ok = false;
        }
      }
      return ok;
    },

    async insertStripeEvent(args) {
      const insert = await rest("stripe_events", {
        method: "POST",
        headers: { Prefer: "return=minimal" },
        body: {
          stripe_event_id: args.stripeEventId,
          event_type: args.eventType,
          workspace_id: args.workspaceId,
          payload: args.payload,
          applied_at: null,
        },
      });
      if (insert.status < 400) return { status: "inserted" };
      if (!isUniqueViolation(insert.status, insert.code, insert.message)) {
        return { status: "error", reason: insert.code ?? String(insert.status) };
      }
      const existing = await this.getStripeEvent(args.stripeEventId);
      if (!existing) return { status: "error", reason: "duplicate_row_not_found" };
      return existing.applied_at != null
        ? { status: "duplicate_applied" }
        : { status: "duplicate_pending" };
    },

    async getStripeEvent(stripeEventId) {
      const res = await rest(
        `stripe_events?select=stripe_event_id,event_type,workspace_id,payload,applied_at&stripe_event_id=eq.${encodeURIComponent(stripeEventId)}&limit=1`,
      );
      if (res.status >= 400) return null;
      return firstRow(res.data) as StripeEventRow | null;
    },

    async markStripeEventApplied(stripeEventId) {
      const res = await rest(
        `stripe_events?stripe_event_id=eq.${encodeURIComponent(stripeEventId)}&applied_at=is.null`,
        {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: { applied_at: new Date().toISOString() },
        },
      );
      if (res.status >= 400) throw new Error("stripe_events applied_at update failed");
    },

    async casUpdateWorkspaceBilling(workspaceId, eventCreated, patch) {
      const res = await rest(
        `workspaces?id=eq.${encodeURIComponent(workspaceId)}` +
          `&last_stripe_event_created=or.(is.null,lt.${eventCreated})`,
        {
          method: "PATCH",
          headers: { Prefer: "return=representation" },
          body: { ...patch, last_stripe_event_created: eventCreated },
        },
      );
      if (res.status >= 400) throw new Error("workspaces CAS update failed");
      return Array.isArray(res.data) && res.data.length > 0;
    },

    async setClaimSyncPending(workspaceId, pending) {
      const res = await rest(`workspaces?id=eq.${encodeURIComponent(workspaceId)}`, {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: { claim_sync_pending: pending },
      });
      if (res.status >= 400) throw new Error("workspaces claim_sync_pending update failed");
    },
  };
}

/**
 * Resolves the caller's identity from the bearer token, exactly as the edge
 * version's user-client `auth.getUser()` did, but with one `fetch` instead of a
 * client. `null` means "not authenticated" — the routes turn that into the same
 * 401 the edge version returned.
 */
export async function resolveUserFromToken(
  env: BillingEnv,
  authorization: string,
): Promise<{ id: string; email?: string } | null> {
  const { url, anonKey } = supabaseBase(env);
  try {
    const res = await fetch(`${url}/auth/v1/user`, {
      headers: { apikey: anonKey, Authorization: authorization },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { id?: unknown; email?: unknown };
    if (typeof data?.id !== "string" || data.id.length === 0) return null;
    return typeof data.email === "string" ? { id: data.id, email: data.email } : { id: data.id };
  } catch {
    return null;
  }
}