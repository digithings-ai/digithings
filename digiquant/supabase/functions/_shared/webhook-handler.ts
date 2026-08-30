/**
 * Pure Stripe webhook apply path (T2) — imported by stripe-webhook/index.ts and tests.
 *
 * Does not call Deno.serve. Admin + Stripe clients are injected.
 */

import type { StripeEvent } from "./stripe.ts";
import {
  insertStripeEvent,
  listWorkspaceMembers,
  maxAppliedEventCreated,
  syncPlanTierClaims,
  type AdminClient,
  type WorkspaceRow,
} from "./supabase-admin.ts";
import {
  extractSubscriptionPriceId,
  mapStripeStatus,
  planTierFromPriceId,
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

  if (insertStatus === "duplicate") {
    return { ok: true, status: "duplicate" };
  }
  if (insertStatus === "error") {
    throw new Error("stripe_events insert failed");
  }

  // Out-of-order guard: ignore older events for the same subscription.
  if (subscriptionId || workspace) {
    const priorMax = await maxAppliedEventCreated(admin, {
      workspaceId: workspace?.id ?? null,
      subscriptionId,
      excludeEventId: event.id,
    });
    if (priorMax > 0 && event.created < priorMax) {
      return { ok: true, status: "out_of_order" };
    }
  }

  const applied = await applyEventMapping(admin, event, workspace);
  if (!applied) {
    return { ok: true, status: "ignored" };
  }

  return {
    ok: true,
    status: "applied",
    claim_sync_pending: applied.claimSyncPending,
  };
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
      .select(
        "id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending",
      )
      .eq("id", args.workspaceId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  if (args.subscriptionId) {
    const { data } = await admin
      .from("workspaces")
      .select(
        "id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending",
      )
      .eq("stripe_subscription_id", args.subscriptionId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  if (args.customerId) {
    const { data } = await admin
      .from("workspaces")
      .select(
        "id, stripe_customer_id, stripe_subscription_id, subscription_status, plan_tier, claim_sync_pending",
      )
      .eq("stripe_customer_id", args.customerId)
      .maybeSingle();
    if (data) return data as WorkspaceRow;
  }
  return null;
}

interface ApplyResult {
  claimSyncPending: boolean;
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
      if (Object.keys(patch).length === 0) return null;
      await admin.from("workspaces").update(patch).eq("id", workspace.id);
      if (workspace.claim_sync_pending) {
        const pending = !(await runClaimSync(admin, workspace.id, workspace.plan_tier as PlanTier));
        await admin
          .from("workspaces")
          .update({ claim_sync_pending: pending })
          .eq("id", workspace.id);
        return { claimSyncPending: pending };
      }
      return { claimSyncPending: false };
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
      let planTier: PlanTier = planTierFromPriceId(priceId);
      if (status === "canceled") {
        planTier = "free";
      }
      return await writeBillingAndSyncClaims(admin, workspace.id, {
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
      return await writeBillingAndSyncClaims(admin, workspace.id, {
        subscription_status: "canceled" satisfies SubscriptionStatus,
        plan_tier: "free",
      });
    }

    case "invoice.payment_failed": {
      if (!workspace) return null;
      await admin
        .from("workspaces")
        .update({ subscription_status: "past_due" satisfies SubscriptionStatus })
        .eq("id", workspace.id);
      return { claimSyncPending: workspace.claim_sync_pending };
    }

    default:
      return null;
  }
}

async function writeBillingAndSyncClaims(
  admin: AdminClient,
  workspaceId: string,
  patch: {
    stripe_subscription_id?: string | null;
    stripe_customer_id?: string | null;
    subscription_status: SubscriptionStatus;
    plan_tier: PlanTier;
  },
): Promise<ApplyResult> {
  const { error } = await admin.from("workspaces").update(patch).eq("id", workspaceId);
  if (error) {
    throw new Error("workspaces update failed");
  }
  const claimOk = await runClaimSync(admin, workspaceId, patch.plan_tier);
  const claimSyncPending = !claimOk;
  await admin
    .from("workspaces")
    .update({ claim_sync_pending: claimSyncPending })
    .eq("id", workspaceId);
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
