import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/db", () => ({
  getDb: vi.fn(),
}));

vi.mock("@/lib/conversations-repo", () => ({
  tenantIdBySlug: vi.fn(),
  listConversationSummaries: vi.fn(),
  createConversation: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import {
  createConversation,
  listConversationSummaries,
  tenantIdBySlug,
} from "@/lib/conversations-repo";

const db = { execute: vi.fn() };

describe("/api/conversations", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
  });

  it("GET returns 401 without auth", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(new Request("http://localhost/api/conversations"));
    expect(res.status).toBe(401);
  });

  it("GET returns conversation summaries", async () => {
    vi.mocked(listConversationSummaries).mockResolvedValue([
      { id: "c1", title: "Chat", updatedAt: new Date("2026-01-01T00:00:00Z") },
    ]);
    const res = await GET(new Request("http://localhost/api/conversations"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.conversations).toHaveLength(1);
    expect(body.conversations[0].id).toBe("c1");
  });

  it("POST creates a conversation", async () => {
    vi.mocked(createConversation).mockResolvedValue("new-id");
    const res = await POST(
      new Request("http://localhost/api/conversations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: "Hello" }),
      })
    );
    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.id).toBe("new-id");
  });

  it("POST returns 400 for invalid JSON", async () => {
    const res = await POST(
      new Request("http://localhost/api/conversations", {
        method: "POST",
        body: "not-json",
      })
    );
    expect(res.status).toBe(400);
  });
});
