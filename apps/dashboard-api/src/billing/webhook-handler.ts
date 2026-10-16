/**
 * Stripe webhook event application — a port of
 * `digiquant/supabase/functions/_shared/webhook-handler.ts`.
 *
 * No Deno-isms, so the algorithm is unchanged. Two properties are worth naming
 * because they are the ones a rewrite is most likely to break:
 *
 *  1. The event row is inserted BEFORE any workspace write, so a duplicate
 *     delivery is a 200 no-op and a crash mid-apply leaves `applied_at` NULL,
 *     which Stripe's retry re-enters through the `duplicate_pending` branch.
 *  2. `markStripeEventApplied` runs even for ignored and out-of-order events, so
 *     Stripe stops retrying an event we deliberately declined to apply. Only a
 *     thrown error leaves the row unapplied.
 */

import {
  extractSubscriptionPriceId,
  loadPriceTierEnv,
  mapStripeStatus,
  planTierForSubscriptionStatus,
} from "./tiers";
import type { AdminDb, WorkspaceRow } from "./admin";
import type { StripeEvent } from "./stripe";
import type { BillingEnv } from "./env";

export interface WebhookResult {
  ok: true;
  status: "applied" | "duplicate" | "out_of_order" | "ignored";
  claim_sync_pending?: boolean;
}

interface MappingOutcome {
  planTier?: string;
  claimSyncPending?: boolean;
  stale?: boolean;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function extractWorkspaceId(obj: Record<string, unknown>): string | null {
  const metadata = asRecord(obj.metadata);
  if (typeof metadata.workspace_id === "string" && metadata.workspace_id) {
    return metadata.workspace_id;
  }
  return typeof obj.client_reference_id === "string" && obj.client_reference_id
    ? obj.client_reference_id
    : null;
}

function extractSubscriptionId(eventType: string, obj: Record<string, unknown>): string | null {
  if (eventType.startsWith("customer.subscription.")) {
    return typeof obj.id === "string" && obj.id ? obj.id : null;
  }
  return typeof obj.subscription === "string" && obj.subscription ? obj.subscription : null;
}

async function resolveWorkspace(
  admin: AdminDb,
  hints: { workspaceId: string | null; subscriptionId: string | null; customerId: string | null },
): Promise<WorkspaceRow | null> {
  if (hints.workspaceId) {
    const byId = await admin.getWorkspaceBy("id", hints.workspaceId);
    if (byId) return byId;
  }
  if (hints.subscriptionId) {
    const bySub = await admin.getWorkspaceBy("stripe_subscription_id", hints.subscriptionId);
    if (bySub) return bySub;
  }
  if (hints.customerId) {
    const byCustomer = await admin.getWorkspaceBy("stripe_customer_id", hints.customerId);
    if (byCustomer) return byCustomer;
  }
  return null;
}

async function runClaimSync(admin: AdminDb, workspaceId: string, planTier: string): Promise<boolean> {
  const members = await admin.listWorkspaceMembers(workspaceId);
  if (members.length === 0) return true;
  return admin.syncPlanTierClaims(
    members.map((m) => m.user_id),
    planTier,
  );
}

async function finishWithClaimSync(
  admin: AdminDb,
  workspaceId: string,
  planTier: string,
): Promise<MappingOutcome> {
  const ok = await runClaimSync(admin, workspaceId, planTier);
  const claimSyncPending = !ok;
  await admin.setClaimSyncPending(workspaceId, claimSyncPending);
  return { claimSyncPending, stale: false };
}

async function writeBillingAndSyncClaims(
  admin: AdminDb,
  workspace: WorkspaceRow,
  eventCreated: number,
  patch: Partial<WorkspaceRow>,
): Promise<MappingOutcome> {
  const won = await admin.casUpdateWorkspaceBilling(workspace.id, eventCreated, patch);
  if (!won) return { claimSyncPending: false, stale: true };
  return finishWithClaimSync(admin, workspace.id, patch.plan_tier ?? workspace.plan_tier);
}

async function applyEventMapping(
  admin: AdminDb,
  env: BillingEnv,
  event: StripeEvent,
  workspace: WorkspaceRow | null,
): Promise<MappingOutcome | null> {
  if (!workspace) return null;
  const obj = asRecord(event.data?.object);
  switch (event.type) {
    case "checkout.session.completed": {
      const patch: Partial<WorkspaceRow> = {};
      if (typeof obj.customer === "string" && obj.customer) {
        patch.stripe_customer_id = obj.customer;
      }
      if (typeof obj.subscription === "string" && obj.subscription) {
        patch.stripe_subscription_id = obj.subscription;
      }
      if (Object.keys(patch).length === 0) {
        return finishWithClaimSync(admin, workspace.id, workspace.plan_tier);
      }
      return writeBillingAndSyncClaims(admin, workspace, event.created, patch);
    }
    case "customer.subscription.created":
    case "customer.subscription.updated": {
      const status = mapStripeStatus(typeof obj.status === "string" ? obj.status : "");
      const priceId = extractSubscriptionPriceId(obj);
      const planTier = planTierForSubscriptionStatus(status, priceId, loadPriceTierEnv(env));
      return writeBillingAndSyncClaims(admin, workspace, event.created, {
        stripe_subscription_id:
          typeof obj.id === "string" && obj.id ? obj.id : workspace.stripe_subscription_id,
        stripe_customer_id:
          typeof obj.customer === "string" && obj.customer
            ? obj.customer
            : workspace.stripe_customer_id,
        subscription_status: status,
        plan_tier: planTier,
      });
    }
    case "customer.subscription.deleted":
      return writeBillingAndSyncClaims(admin, workspace, event.created, {
        subscription_status: "canceled",
        plan_tier: "free",
      });
    case "invoice.payment_failed":
      // Grace period: keep the tier, mark past_due so the UI can warn.
      return writeBillingAndSyncClaims(admin, workspace, event.created, {
        subscription_status: "past_due",
        plan_tier: workspace.plan_tier,
      });
    default:
      return null;
  }
}

export async function handleStripeEvent(
  admin: AdminDb,
  env: BillingEnv,
  event: StripeEvent,
): Promise<WebhookResult> {
  const obj = asRecord(event.data?.object);
  const workspaceIdHint = extractWorkspaceId(obj);
  const subscriptionId = extractSubscriptionId(event.type, obj);
  const customerId = typeof obj.customer === "string" && obj.customer ? obj.customer : null;

  const workspace = await resolveWorkspace(admin, {
    workspaceId: workspaceIdHint,
    subscriptionId,
    customerId,
  });

  const inserted = await admin.insertStripeEvent({
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

  if (inserted.status === "duplicate_applied") return { ok: true, status: "duplicate" };
  if (inserted.status === "error") throw new Error("stripe_events insert failed");
  // inserted and duplicate_pending both fall through and re-apply.

  const outcome = await applyEventMapping(admin, env, event, workspace);

  // Always mark applied — including ignored and out-of-order — so Stripe stops
  // retrying. A throw above leaves applied_at NULL and Stripe's retry re-enters.
  await admin.markStripeEventApplied(event.id);

  if (outcome === null) return { ok: true, status: "ignored" };
  if (outcome.stale) return { ok: true, status: "out_of_order" };
  return { ok: true, status: "applied", claim_sync_pending: outcome.claimSyncPending ?? false };
}