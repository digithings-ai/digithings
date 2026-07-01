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

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import {
  deleteConversation,
  getConversationMessages,
  replaceConversationMessages,
  tenantIdBySlug,
} from "@/lib/conversations-repo";

const routeCtx = { params: Promise.resolve({ id: "conv-1" }) };
const db = {};

describe("/api/conversations/[id]", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
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
    vi.mocked(replaceConversationMessages).mockResolvedValue(true);
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
