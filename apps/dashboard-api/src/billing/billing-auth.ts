/**
 * Workspace authz — a port of
 * `digiquant/supabase/functions/_shared/billing-auth.ts`.
 *
 * No Deno-isms, so the logic is unchanged: membership first, then the owner
 * gate, both before any Stripe call. The `plan_tier` on the auth user is
 * presentation-only (auth.users app_metadata, rides the JWT); entitlements read
 * `workspaces.plan_tier`, which stays authoritative because the Stripe CAS path
 * is the only writer.
 */

import { jsonError } from "./http";
import type { AdminDb, CallerWorkspace } from "./admin";

export interface AuthUser {
  id: string;
  email?: string;
  plan_tier?: string;
}

export type AuthedOwner =
  | ({ ok: true; user: AuthUser } & CallerWorkspace)
  | { ok: false; response: Response };

export function requireBearerHeader(authHeader: string | null): Response | null {
  if (!authHeader?.startsWith("Bearer ")) {
    return jsonError(401, "UNAUTHENTICATED", "Missing bearer token");
  }
  return null;
}

export async function requireWorkspaceMember(
  admin: AdminDb,
  user: AuthUser,
  requestedWorkspaceId: string | null,
): Promise<AuthedOwner> {
  const resolved = await admin.ensureCallerWorkspace(user.id);
  if (!resolved) {
    return { ok: false, response: jsonError(403, "WORKSPACE_FORBIDDEN", "No workspace membership") };
  }
  if (requestedWorkspaceId && requestedWorkspaceId !== resolved.workspace.id) {
    return { ok: false, response: jsonError(403, "WORKSPACE_FORBIDDEN", "Wrong workspace") };
  }
  return { ok: true, user, workspace: resolved.workspace, role: resolved.role };
}

export async function requireWorkspaceOwner(
  admin: AdminDb,
  user: AuthUser,
  requestedWorkspaceId: string | null,
): Promise<AuthedOwner> {
  const member = await requireWorkspaceMember(admin, user, requestedWorkspaceId);
  if (!member.ok) return member;
  if (member.role !== "owner") {
    return { ok: false, response: jsonError(403, "WORKSPACE_FORBIDDEN", "Owner role required") };
  }
  return member;
}