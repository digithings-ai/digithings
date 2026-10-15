import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";
import { POST, DIGIGRAPH_MCP_DECISION_PATH } from "./route";

vi.mock("@/lib/request-auth", () => ({ requireDigiChatAuth: vi.fn() }));
vi.mock("@/lib/chat-route-context", () => ({ resolveChatTenantContext: vi.fn() }));
vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 30 })),
}));
vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: vi.fn(async () => ({ digigraphUrl: "http://127.0.0.1:8000" })),
}));
vi.mock("@/lib/license/state", () => ({
  licenseRefusal: vi.fn(() => null),
  getHeartbeatContext: vi.fn(() => null),
}));
vi.mock("@/lib/digigraph-upstream", () => ({
  resolveDigigraphUpstreamAuth: vi.fn(async () => ({ bearer: "upstream-token" })),
  DigigraphUpstreamAuthError: class extends Error {},
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveDigigraphUpstreamAuth } from "@/lib/digigraph-upstream";
import { resolveChatTenantContext } from "@/lib/chat-route-context";

const PENDING_ID = "a1b2c3d4e5f60718";
const SESSION = "sess-123";

function request(body: unknown, sessionId: string | null = SESSION): Request {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (sessionId) headers["x-digichat-session"] = sessionId;
  return new Request("http://localhost/api/chat/approve", {
    method: "POST",
    headers,
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx as never);
  vi.mocked(resolveChatTenantContext).mockResolvedValue({
    tenantSlug: "acme",
    ownerUserSub: "user-1",
  } as never);
  vi.mocked(resolveDigigraphUpstreamAuth).mockResolvedValue({ bearer: "upstream-token" } as never);
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: "approved" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});

describe("POST /api/chat/approve", () => {
  it("test 4: accepts only the opaque id plus a verdict, and rejects the rest by name", async () => {
    // Positive: the allowed pair is accepted and forwarded.
    const ok = await POST(request({ pendingId: PENDING_ID, decision: "approve" }));
    expect(ok.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({
      pending_id: PENDING_ID,
      approve: true,
    });

    // Negative: a body carrying a tool name or arguments is an EXPLICIT refusal,
    // not a silent ignore — an ignored `arguments` would make the gate look
    // enforced while the caller's intent was actually discarded.
    const withTool = await POST(
      request({ pendingId: PENDING_ID, decision: "approve", tool: "createJiraIssue" })
    );
    expect(withTool.status).toBe(400);
    const toolBody = await withTool.json();
    expect(toolBody).toMatchObject({ error: "unsupported_field", fields: ["tool"] });

    const withArgs = await POST(
      request({ pendingId: PENDING_ID, decision: "approve", arguments: { issueIdOrKey: "ABC-1" } })
    );
    expect(withArgs.status).toBe(400);
    expect(await withArgs.json()).toMatchObject({
      error: "unsupported_field",
      fields: ["arguments"],
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("test 6: the operator-only invariant holds — config keys are refused by name", async () => {
    for (const field of ["url", "authHeader", "allowedTools", "mutatingTools"]) {
      const res = await POST(
        request({ pendingId: PENDING_ID, decision: "approve", [field]: "https://evil.example" })
      );
      expect(res.status).toBe(403);
      expect(await res.json()).toMatchObject({
        error: "operator_only_field",
        fields: [field],
      });
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("test 5: the decision is forwarded for the session that raised it", async () => {
    await POST(request({ pendingId: PENDING_ID, decision: "deny" }));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      `http://127.0.0.1:8000${DIGIGRAPH_MCP_DECISION_PATH}`
    );
    const headers = init.headers as Record<string, string>;
    // The session travels in the header, never the body: digigraph keys the
    // pending store on (session_id, pending_id), so this is what makes an id
    // belonging to another session fail closed upstream instead of here.
    expect(headers["X-Session-Id"]).toBe(SESSION);
    expect(headers.Authorization).toBe("Bearer upstream-token");
    expect(headers["X-Digi-Caller"]).toBe("digichat");
    expect(JSON.parse(String(init.body))).toEqual({
      pending_id: PENDING_ID,
      approve: false,
    });
    // The body carries an id and a verdict. Nothing else can reach digigraph.
    expect(Object.keys(JSON.parse(String(init.body))).sort()).toEqual(["approve", "pending_id"]);
  });

  it("test 5: a decision without the session header is refused, and no session is invented", async () => {
    const res = await POST(request({ pendingId: PENDING_ID, decision: "approve" }, null));
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "session_required" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a malformed id and an unknown verdict", async () => {
    const badId = await POST(request({ pendingId: "../../etc/passwd", decision: "approve" }));
    expect(badId.status).toBe(400);
    expect(await badId.json()).toMatchObject({ error: "invalid_pending_id" });

    const badDecision = await POST(request({ pendingId: PENDING_ID, decision: "maybe" }));
    expect(badDecision.status).toBe(400);
    expect(await badDecision.json()).toMatchObject({ error: "invalid_decision" });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requires authentication", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse as never);
    const res = await POST(request({ pendingId: PENDING_ID, decision: "approve" }));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces a missing upstream decision endpoint instead of claiming a decision", async () => {
    // 284.6 has not landed yet. Reporting 200 here would be a lie: nothing was
    // recorded, so the human would believe their answer was acted on.
    fetchMock.mockResolvedValueOnce(new Response("not found", { status: 404 }));
    const res = await POST(request({ pendingId: PENDING_ID, decision: "approve" }));
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ error: "decision_upstream_unavailable" });
  });

  it("rejects an unexpected upstream decision shape", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "whatever" }), { status: 200 })
    );
    const res = await POST(request({ pendingId: PENDING_ID, decision: "approve" }));
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ error: "decision_upstream_failed" });
  });

  it("rejects a body that is not an object", async () => {
    const res = await POST(request("[1,2,3]"));
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "invalid_body" });
  });
});
