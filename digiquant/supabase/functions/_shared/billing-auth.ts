/**
 * Shared auth / workspace gates for Checkout + Customer Portal (T2).
 * Extracted so Deno tests can cover 401/403 without Deno.serve.
 */

import {
  ensureCallerWorkspace,
  jsonError,
  type AdminClient,
  type WorkspaceRow,
} from "./supabase-admin.ts";

export type AuthUser = {
  id: string;
  email?: string | null;
  /**
   * plan_tier from auth.users.app_metadata (T2 claim sync).
   * Presentation / JWT-side only — settings entitlement gates read
   * `workspaces.plan_tier` (authoritative after Stripe CAS), not this claim.
   */
  plan_tier?: string | null;
};

export type AuthedOwner =
  | { ok: true; user: AuthUser; workspace: WorkspaceRow; role: string }
  | { ok: false; response: Response };

/** 401 when Authorization bearer is missing. */
export function requireBearerHeader(authHeader: string | null): Response | null {
  if (!authHeader?.startsWith("Bearer ")) {
    return jsonError(401, "UNAUTHENTICATED", "Missing bearer token");
  }
  return null;
}

/**
 * Resolve caller workspace (ensuring Observer personal workspace if missing)
 * and enforce membership + optional workspace_id match.
 * Returns 403 WORKSPACE_FORBIDDEN on membership / id mismatch / bootstrap failure.
 */
export async function requireWorkspaceMember(
  admin: AdminClient,
  user: AuthUser,
  requestedWorkspaceId: string | null,
): Promise<AuthedOwner> {
  const resolved = await ensureCallerWorkspace(admin, user.id);
  if (!resolved) {
    return {
      ok: false,
      response: jsonError(403, "WORKSPACE_FORBIDDEN", "No workspace membership"),
    };
  }
  if (requestedWorkspaceId && requestedWorkspaceId !== resolved.workspace.id) {
    return {
      ok: false,
      response: jsonError(403, "WORKSPACE_FORBIDDEN", "Wrong workspace"),
    };
  }
  return {
    ok: true,
    user,
    workspace: resolved.workspace,
    role: resolved.role,
  };
}

/**
 * Resolve caller workspace and enforce owner + optional workspace_id match.
 * Returns 403 WORKSPACE_FORBIDDEN on membership / role / id mismatch.
 */
export async function requireWorkspaceOwner(
  admin: AdminClient,
  user: AuthUser,
  requestedWorkspaceId: string | null,
): Promise<AuthedOwner> {
  const member = await requireWorkspaceMember(admin, user, requestedWorkspaceId);
  if (!member.ok) return member;
  if (member.role !== "owner") {
    return {
      ok: false,
      response: jsonError(403, "WORKSPACE_FORBIDDEN", "Owner role required"),
    };
  }
  return member;
}
