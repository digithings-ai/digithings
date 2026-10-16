import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, PUT } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/db", () => ({
  getDb: vi.fn(),
}));

vi.mock("@/lib/conversations-repo", () => ({
  tenantIdBySlug: vi.fn(),
  getConversationMessages: vi.fn(),
  replaceConversationMessages: vi.fn(),
  deleteConversation: vi.fn(),
}));

// Art. 9 screening hop (DIG-1178 leaf 12d): mocked to allow by default so the
// pre-existing PUT tests keep passing; refusal paths are pinned below. This is
// expected, not a regression.
vi.mock("@/lib/art9-screen", () => ({
  CODE_REFUSED: "art9_refused",
  screenConversationWrite: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import {
  deleteConversation,
  getConversationMessages,
  replaceConversationMessages,
  tenantIdBySlug,
} from "@/lib/conversations-repo";
import { screenConversationWrite } from "@/lib/art9-screen";

const routeCtx = { params: Promise.resolve({ id: "conv-1" }) };
const db = {};

describe("/api/conversations/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
    vi.mocked(screenConversationWrite).mockResolvedValue({ allowed: true });
  });

  it("GET returns 404 when conversation missing", async () => {
    vi.mocked(getConversationMessages).mockResolvedValue(null);
    const res = await GET(new Request("http://localhost/api/conversations/conv-1"), routeCtx);
    expect(res.status).toBe(404);
  });

  it("GET returns messages for owned conversation", async () => {
    vi.mocked(getConversationMessages).mockResolvedValue({
      title: "T",
      messages: [{ id: "m1", role: "user", parts: [] }],
    });
    const res = await GET(new Request("http://localhost/api/conversations/conv-1"), routeCtx);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.messages).toHaveLength(1);
  });

  it("PUT returns 204 on success", async () => {
    vi.mocked(replaceConversationMessages).mockResolvedValue("ok");
    const res = await PUT(
      new Request("http://localhost/api/conversations/conv-1", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "m1", role: "user", parts: [] }] }),
      }),
      routeCtx
    );
    expect(res.status).toBe(204);
  });

  it("PUT returns 409 when replace would truncate history", async () => {
    vi.mocked(replaceConversationMessages).mockResolvedValue("would_truncate");
    const res = await PUT(
      new Request("http://localhost/api/conversations/conv-1", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [] }),
      }),
      routeCtx
    );
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.error).toBe("would_truncate");
  });

  it("PUT screens before any db handle and writes on allow", async () => {
    vi.mocked(replaceConversationMessages).mockResolvedValue("ok");
    const res = await PUT(
      new Request("http://localhost/api/conversations/conv-1", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "m1", role: "user", parts: [] }] }),
      }),
      routeCtx
    );
    expect(res.status).toBe(204);
    expect(vi.mocked(screenConversationWrite)).toHaveBeenCalledOnce();
    // The screen hop runs before any database handle exists.
    expect(
      vi.mocked(screenConversationWrite).mock.invocationCallOrder[0]
    ).toBeLessThan(vi.mocked(getDb).mock.invocationCallOrder[0]);
    expect(vi.mocked(replaceConversationMessages)).toHaveBeenCalled();
  });

  it("PUT refuses the write when screening refuses (no db write)", async () => {
    vi.mocked(screenConversationWrite).mockResolvedValue({
      allowed: false,
      code: "art9_refused",
      categories: ["art9:health"],
      reason: "art9:health:field-name",
    });
    const res = await PUT(
      new Request("http://localhost/api/conversations/conv-1", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "m1", role: "user", parts: [] }] }),
      }),
      routeCtx
    );
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.error).toBe("art9_refused");
    expect(vi.mocked(replaceConversationMessages)).not.toHaveBeenCalled();
  });

  it("PUT fails closed when the screening hop is unavailable", async () => {
    vi.mocked(screenConversationWrite).mockResolvedValue({
      allowed: false,
      code: "art9_screen_unavailable",
      categories: [],
      reason: "art9_screen_unavailable",
    });
    const res = await PUT(
      new Request("http://localhost/api/conversations/conv-1", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ id: "m1", role: "user", parts: [] }] }),
      }),
      routeCtx
    );
    expect(res.status).toBe(503);
    expect(vi.mocked(replaceConversationMessages)).not.toHaveBeenCalled();
  });

  it("DELETE returns 401 without auth", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await DELETE(
      new Request("http://localhost/api/conversations/conv-1", { method: "DELETE" }),
      routeCtx
    );
    expect(res.status).toBe(401);
  });

  it("DELETE returns 204 when conversation deleted", async () => {
    vi.mocked(deleteConversation).mockResolvedValue(true);
    const res = await DELETE(
      new Request("http://localhost/api/conversations/conv-1", { method: "DELETE" }),
      routeCtx
    );
    expect(res.status).toBe(204);
  });
});
