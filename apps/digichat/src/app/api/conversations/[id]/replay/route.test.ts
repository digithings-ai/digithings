import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
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
}));

vi.mock("@/lib/deploy-config/loader", () => ({
  getPrimaryDeployment: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import { getConversationMessages, tenantIdBySlug } from "@/lib/conversations-repo";
import { getPrimaryDeployment } from "@/lib/deploy-config/loader";

const JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";

const routeCtx = { params: Promise.resolve({ id: "conv-1" }) };
const db = {};

const deployment = {
  slug: "acme",
  chrome: {
    title: "Acme desk",
    theme: "dark",
    welcome: { title: "Hello Acme", body: ["Saved for the demo."] },
    suggestions: ["What can you show me?"],
    placeholder: "Message Acme",
    accent: { color: "#112233", foreground: "#ffffff" },
  },
  features: { view: "balanced" },
};

describe("GET /api/conversations/[id]/replay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
    vi.mocked(getPrimaryDeployment).mockReturnValue(deployment as never);
  });

  it("returns 401 before reading the conversation", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(new Request("http://localhost/api/conversations/conv-1/replay"), routeCtx);
    expect(res.status).toBe(401);
    expect(getConversationMessages).not.toHaveBeenCalled();
  });

  it("returns 404 when the conversation is missing", async () => {
    vi.mocked(getConversationMessages).mockResolvedValue(null);
    const res = await GET(new Request("http://localhost/api/conversations/conv-1/replay"), routeCtx);
    expect(res.status).toBe(404);
  });

  it("downloads a self-contained file and leaves every secret out", async () => {
    vi.mocked(getConversationMessages).mockResolvedValue({
      title: "Demo",
      messages: [
        {
          id: "u1",
          role: "user",
          parts: [{ type: "text", text: "token dgk_live_TESTSECRET99" }],
        },
        {
          id: "a1",
          role: "assistant",
          parts: [
            {
              type: "tool-digisearch",
              state: "output-available",
              input: { authorization: `Bearer ${JWT}` },
              output: {
                api_key: "sk-ant-TESTSECRET99",
                inviteKey: "invite-plain-9f3c2a",
                note: "X-Embed-Token: embed-plain-9f3c2a",
              },
            },
            { type: "text", text: "digi_live_TESTSECRET99" },
          ],
        },
      ],
    });
    const res = await GET(
      new Request(
        "http://localhost/api/conversations/conv-1/replay?theme=light&view=verbose&at=2026-10-21T03:00:00.000Z",
      ),
      routeCtx,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="acme-2026-10-21.html"');
    const html = await res.text();
    expect(html).toContain('data-theme="light"');
    expect(html).toContain('data-view="verbose"');
    expect(html).toContain("Hello Acme");
    expect(html).toContain("What can you show me?");
    expect(html).toContain("@font-face");
    expect(html).not.toMatch(/<link[^>]+stylesheet/i);
    for (const secret of [
      "dgk_live_TESTSECRET99",
      "digi_live_TESTSECRET99",
      "sk-ant-TESTSECRET99",
      "invite-plain-9f3c2a",
      "embed-plain-9f3c2a",
      JWT,
    ]) {
      expect(html).not.toContain(secret);
    }
    expect(html).toContain("[redacted]");
  });
});
