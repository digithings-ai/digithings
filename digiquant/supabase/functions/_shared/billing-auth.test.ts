/**
 * Deno unit tests for checkout/portal auth gates + Observer workspace bootstrap.
 *
 * stripe-webhook.test.ts covers bearer/owner/wrong-workspace, but its admin mock
 * refuses ensure_personal_workspace. Settings covers bootstrap on GET brokers;
 * billing must share the same fail-closed bootstrap so a brand-new Auth user
 * either gets an owner workspace or 403 WORKSPACE_FORBIDDEN — never a half
 * membership invented client-side.
 *
 *   deno test --allow-env --allow-read _shared/billing-auth.test.ts
 */

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  requireBearerHeader,
  requireWorkspaceMember,
  requireWorkspaceOwner,
  type AuthUser,
} from "./billing-auth.ts";
import {
  ensureCallerWorkspace,
  type AdminClient,
  type WorkspaceRow,
} from "./supabase-admin.ts";

const WS_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const USER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

function workspaceRow(id: string, planTier = "free"): WorkspaceRow {
  return {
    id,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    plan_tier: planTier,
    claim_sync_pending: false,
    last_stripe_event_created: null,
  };
}

type Member = { user_id: string; workspace_id: string; role: string };

function createBootstrapAdmin(opts: {
  members?: Member[];
  workspaces?: Map<string, WorkspaceRow>;
  bootstrap?: "ok" | "fail" | "noop";
  bootstrappedWorkspaceId?: string;
}): {
  admin: AdminClient;
  rpcCalls: Array<{ fn: string; args?: Record<string, unknown> }>;
  members: Member[];
  workspaces: Map<string, WorkspaceRow>;
} {
  const members = [...(opts.members ?? [])];
  const workspaces = new Map(opts.workspaces ?? []);
  const rpcCalls: Array<{ fn: string; args?: Record<string, unknown> }> = [];
  const bootstrap = opts.bootstrap ?? "ok";
  const bootstrappedWorkspaceId = opts.bootstrappedWorkspaceId ?? WS_ID;

  const admin = {
    from(table: string) {
      return {
        select(_cols: string) {
          return {
            eq(col: string, val: string) {
              if (table !== "workspace_members" || col !== "user_id") {
                return {
                  async maybeSingle() {
                    return { data: null, error: null };
                  },
                  then: undefined,
                };
              }
              const rows = members
                .filter((m) => m.user_id === val)
                .map((m) => ({
                  role: m.role,
                  workspace_id: m.workspace_id,
                  workspaces: workspaces.get(m.workspace_id)!,
                }));
              // resolveCallerWorkspace awaits the builder directly (thenable).
              return {
                then(
                  resolve: (value: { data: unknown; error: null }) => unknown,
                ) {
                  return Promise.resolve({ data: rows, error: null }).then(
                    resolve,
                  );
                },
              };
            },
          };
        },
      };
    },
    async rpc(fn: string, args?: Record<string, unknown>) {
      rpcCalls.push({ fn, args });
      if (fn !== "ensure_personal_workspace") {
        return { data: null, error: { message: `unknown rpc ${fn}` } };
      }
      if (bootstrap === "fail") {
        return { data: null, error: { message: "bootstrap disabled", code: "P0001" } };
      }
      if (bootstrap === "noop") {
        return { data: bootstrappedWorkspaceId, error: null };
      }
      const userId = String(args?.p_user_id ?? "");
      if (!members.some((m) => m.user_id === userId)) {
        workspaces.set(bootstrappedWorkspaceId, workspaceRow(bootstrappedWorkspaceId));
        members.push({
          user_id: userId,
          workspace_id: bootstrappedWorkspaceId,
          role: "owner",
        });
      }
      return { data: bootstrappedWorkspaceId, error: null };
    },
  };

  return {
    admin: admin as unknown as AdminClient,
    rpcCalls,
    members,
    workspaces,
  };
}

Deno.test("requireBearerHeader: missing or non-bearer → 401 UNAUTHENTICATED", async () => {
  // Prefix must be exactly "Bearer " — bare "Bearer" is rejected.
  for (const header of [null, "", "Token abc", "Bearer"]) {
    const res = requireBearerHeader(header);
    assertEquals(res?.status, 401);
    const body = await res!.json();
    assertEquals(body.code, "UNAUTHENTICATED");
  }
  assertEquals(requireBearerHeader("Bearer tok"), null);
});

Deno.test("ensureCallerWorkspace: existing membership skips RPC", async () => {
  const { admin, rpcCalls } = createBootstrapAdmin({
    members: [{ user_id: USER_ID, workspace_id: WS_ID, role: "owner" }],
    workspaces: new Map([[WS_ID, workspaceRow(WS_ID)]]),
  });
  const resolved = await ensureCallerWorkspace(admin, USER_ID);
  assertEquals(resolved?.workspace.id, WS_ID);
  assertEquals(resolved?.role, "owner");
  assertEquals(rpcCalls.length, 0);
});

Deno.test("ensureCallerWorkspace: missing membership bootstraps via RPC", async () => {
  const { admin, rpcCalls, members } = createBootstrapAdmin({
    members: [],
    bootstrap: "ok",
  });
  const resolved = await ensureCallerWorkspace(admin, USER_ID);
  assertEquals(rpcCalls.length, 1);
  assertEquals(rpcCalls[0]?.fn, "ensure_personal_workspace");
  assertEquals(rpcCalls[0]?.args?.p_user_id, USER_ID);
  assertEquals(resolved?.role, "owner");
  assertEquals(resolved?.workspace.plan_tier, "free");
  assertEquals(members.filter((m) => m.user_id === USER_ID).length, 1);
});

Deno.test("ensureCallerWorkspace: RPC failure returns null (fail closed)", async () => {
  const { admin, rpcCalls } = createBootstrapAdmin({
    members: [],
    bootstrap: "fail",
  });
  const resolved = await ensureCallerWorkspace(admin, USER_ID);
  assertEquals(resolved, null);
  assertEquals(rpcCalls.length, 1);
});

Deno.test("ensureCallerWorkspace: RPC ok but still no membership returns null", async () => {
  const { admin } = createBootstrapAdmin({
    members: [],
    bootstrap: "noop",
  });
  const resolved = await ensureCallerWorkspace(admin, USER_ID);
  assertEquals(resolved, null);
});

Deno.test("requireWorkspaceMember: bootstraps then returns owner", async () => {
  const { admin } = createBootstrapAdmin({ members: [], bootstrap: "ok" });
  const user: AuthUser = { id: USER_ID, email: "owner@example.com" };
  const result = await requireWorkspaceMember(admin, user, null);
  assertEquals(result.ok, true);
  if (result.ok) {
    assertEquals(result.role, "owner");
    assertEquals(result.workspace.id, WS_ID);
  }
});

Deno.test("requireWorkspaceMember: wrong workspace_id → 403", async () => {
  const { admin } = createBootstrapAdmin({
    members: [{ user_id: USER_ID, workspace_id: WS_ID, role: "owner" }],
    workspaces: new Map([[WS_ID, workspaceRow(WS_ID)]]),
  });
  const result = await requireWorkspaceMember(
    admin,
    { id: USER_ID },
    "99999999-9999-4999-8999-999999999999",
  );
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.response.status, 403);
    const body = await result.response.json();
    assertEquals(body.code, "WORKSPACE_FORBIDDEN");
    assertEquals(body.message, "Wrong workspace");
  }
});

Deno.test("requireWorkspaceOwner: member role → 403", async () => {
  const { admin } = createBootstrapAdmin({
    members: [{ user_id: USER_ID, workspace_id: WS_ID, role: "member" }],
    workspaces: new Map([[WS_ID, workspaceRow(WS_ID)]]),
  });
  const result = await requireWorkspaceOwner(admin, { id: USER_ID }, null);
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.response.status, 403);
    const body = await result.response.json();
    assertEquals(body.code, "WORKSPACE_FORBIDDEN");
    assertEquals(body.message, "Owner role required");
  }
});

Deno.test("requireWorkspaceOwner: bootstrap failure → 403", async () => {
  const { admin } = createBootstrapAdmin({ members: [], bootstrap: "fail" });
  const result = await requireWorkspaceOwner(admin, { id: USER_ID }, null);
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.response.status, 403);
    const body = await result.response.json();
    assertEquals(body.code, "WORKSPACE_FORBIDDEN");
    assertEquals(body.message, "No workspace membership");
  }
});
