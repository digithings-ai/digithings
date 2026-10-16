/**
 * Pure Stripe webhook apply path (T2) — imported by stripe-webhook/index.ts and tests.
 *
 * Invariants (review):
 * - An inserted-but-not-applied event remains retryable (applied_at NULL).
 * - Every applied event retries claim sync.
 * - Ordering is atomic via workspaces.last_stripe_event_created CAS.
 */

import type { StripeEvent } from "./stripe.ts";
import {
  casUpdateWorkspaceBilling,
  insertStripeEvent,
  listWorkspaceMembers,
  markStripeEventApplied,
  syncPlanTierClaims,
  type AdminClient,
  type WorkspaceRow,
} from "./supabase-admin.ts";
import {
  extractSubscriptionPriceId,
  mapStripeStatus,
  planTierForSubscriptionStatus,
  type PlanTier,
  type SubscriptionStatus,
} from "./tiers.ts";

export interface WebhookResult {
  ok: true;
  status: "applied" | "duplicate" | "out_of_order" | "ignored";
  claim_sync_pending?: boolean;
}

export async function handleStripeEvent(
  admin: AdminClient,
  event: StripeEvent,
): Promise<WebhookResult> {
  const obj = event.data?.object ?? {};
  const workspaceIdHint = extractWorkspaceId(obj);
  const subscriptionId = extractSubscriptionId(event.type, obj);
  const customerId = typeof obj.customer === "string" ? obj.customer : null;

  const workspace = await resolveWorkspace(admin, {
    workspaceId: workspaceIdHint,
    customerId,
    subscriptionId,
  });

  const insertStatus = await insertStripeEvent(admin, {
    stripeEventId: event.id,
    eventType: event.type,
    workspaceId: workspace?.id ?? null,
    payload: {
      created: event.created,
      type: event.type,
      subscription_id: subscriptionId,
      customer_id: customerId,
      workspace_id: workspace?.id ?? workspaceIdHint,
    },
  });

  if (insertStatus.status === "duplicate_applied") {
    return { ok: true, status: "duplicate" };
  }
  if (insertStatus.status === "error") {
    throw new Error("stripe_events insert failed");
  }
  // "inserted" | "duplicate_pending" → continue to (re-)apply.

  try {
    const applied = await applyEventMapping(admin, event, workspace);
    // Mark applied only after the apply path finishes without throw.
    // Stale / ignored paths also mark applied so Stripe stops retrying.
    await markStripeEventApplied(admin, event.id);

    if (!applied) {
      return { ok: true, status: "ignored" };
    }
    if (applied.stale) {
      return { ok: true, status: "out_of_order" };
    }
    return {
      ok: true,
      status: "applied",
      claim_sync_pending: applied.claimSyncPending,
    };
  } catch (err) {
    // Leave applied_at NULL so Stripe's retry re-enters via duplicate_pending.
    throw err;
  }
}

function extractWorkspaceId(obj: Record<string, unknown>): string | null {
  const meta = obj.metadata;
  if (meta && typeof meta === "object" && meta !== null) {
    const wid = (meta as Record<string, unknown>).workspace_id;
    if (typeof wid === "string" && wid.length > 0) return wid;
  }
  if (typeof obj.client_reference_id === "string" && obj.client_reference_id.length > 0) {
    return obj.client_reference_id;
  }
  return null;
}

function extractSubscriptionId(
  type: string,
  obj: Record<string, unknown>,
): string | null {
  if (type.startsWith("customer.subscription.")) {
    return typeof obj.id === "string" ? obj.id : null;
  }
  if (typeof obj.subscription === "string") return obj.subscription;
  return null;
}

const WORKSPACE_SELECT =
  "id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending, last_stripe_event_created";

async function resolveWorkspace(
  admin: AdminClient,
  args: {
    workspaceId: string | null;
    customerId: string | null;
    subscriptionId: string | null;
  },
): Promise<WorkspaceRow | null> {
  if (args.workspaceId) {
    const { data } = await admin
      .from("workspaces")
      .select(WORKSPACE_SELECT)
      .eq("id", args.workspaceId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  if (args.subscriptionId) {
    const { data } = await admin
      .from("workspaces")
      .select(WORKSPACE_SELECT)
      .eq("stripe_subscription_id", args.subscriptionId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  if (args.customerId) {
    const { data } = await admin
      .from("workspaces")
      .select(WORKSPACE_SELECT)
      .eq("stripe_customer_id", args.customerId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  return null;
}

interface ApplyResult {
  claimSyncPending: boolean;
  stale?: boolean;
}

async function applyEventMapping(
  admin: AdminClient,
  event: StripeEvent,
  workspace: WorkspaceRow | null,
): Promise<ApplyResult | null> {
  const obj = event.data.object;

  switch (event.type) {
    case "checkout.session.completed": {
      if (!workspace) return null;
      const customerId = typeof obj.customer === "string" ? obj.customer : null;
      const subscriptionId = typeof obj.subscription === "string" ? obj.subscription : null;
      const patch: Record<string, unknown> = {};
      if (customerId) patch.stripe_customer_id = customerId;
      if (subscriptionId) patch.stripe_subscription_id = subscriptionId;
      if (Object.keys(patch).length === 0) {
        // Nothing to write, but still retry claim sync for any pending flag.
        return await finishWithClaimSync(
          admin,
          workspace.id,
          workspace.plan_tier as PlanTier,
        );
      }
      const won = await casUpdateWorkspaceBilling(
        admin,
        workspace.id,
        event.created,
        patch,
      );
      if (!won) return { claimSyncPending: workspace.claim_sync_pending, stale: true };
      // Re-read plan_tier after CAS (unchanged by checkout) for claim sync.
      return await finishWithClaimSync(
        admin,
        workspace.id,
        workspace.plan_tier as PlanTier,
      );
    }

    case "customer.subscription.created":
    case "customer.subscription.updated": {
      if (!workspace) return null;
      const status = mapStripeStatus(
        typeof obj.status === "string" ? obj.status : null,
      );
      const priceId = extractSubscriptionPriceId(
        obj as { items?: { data?: Array<{ price?: { id?: string } }> } },
      );
      const planTier = planTierForSubscriptionStatus(status, priceId);
      return await writeBillingAndSyncClaims(admin, workspace.id, event.created, {
        stripe_subscription_id: typeof obj.id === "string"
          ? obj.id
          : workspace.stripe_subscription_id,
        stripe_customer_id: typeof obj.customer === "string"
          ? obj.customer
          : workspace.stripe_customer_id,
        subscription_status: status,
        plan_tier: planTier,
      });
    }

    case "customer.subscription.deleted": {
      if (!workspace) return null;
      return await writeBillingAndSyncClaims(admin, workspace.id, event.created, {
        subscription_status: "canceled" satisfies SubscriptionStatus,
        plan_tier: "free",
      });
    }

    case "invoice.payment_failed": {
      if (!workspace) return null;
      return await writeBillingAndSyncClaims(admin, workspace.id, event.created, {
        subscription_status: "past_due" satisfies SubscriptionStatus,
        // Keep current plan_tier during grace; claim sync still runs.
        plan_tier: workspace.plan_tier as PlanTier,
      });
    }

    default:
      return null;
  }
}

async function writeBillingAndSyncClaims(
  admin: AdminClient,
  workspaceId: string,
  eventCreated: number,
  patch: {
    stripe_subscription_id?: string | null;
    stripe_customer_id?: string | null;
    subscription_status: SubscriptionStatus;
    plan_tier: PlanTier;
  },
): Promise<ApplyResult> {
  const won = await casUpdateWorkspaceBilling(admin, workspaceId, eventCreated, patch);
  if (!won) {
    return { claimSyncPending: false, stale: true };
  }
  return await finishWithClaimSync(admin, workspaceId, patch.plan_tier);
}

/** Claim sync on every applied event; propagate claim_sync_pending flag errors. */
async function finishWithClaimSync(
  admin: AdminClient,
  workspaceId: string,
  planTier: PlanTier,
): Promise<ApplyResult> {
  const claimOk = await runClaimSync(admin, workspaceId, planTier);
  const claimSyncPending = !claimOk;
  const { error } = await admin
    .from("workspaces")
    .update({ claim_sync_pending: claimSyncPending })
    .eq("id", workspaceId);
  if (error) {
    throw new Error("workspaces claim_sync_pending update failed");
  }
  return { claimSyncPending };
}

async function runClaimSync(
  admin: AdminClient,
  workspaceId: string,
  planTier: PlanTier,
): Promise<boolean> {
  const members = await listWorkspaceMembers(admin, workspaceId);
  if (members.length === 0) return true;
  return await syncPlanTierClaims(
    admin,
    members.map((m) => m.user_id),
    planTier,
  );
}
