import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";

describe("POST /api/byok/test", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
  });

  it("returns 401 without auth", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "sk-test" },
      })
    );
    expect(res.status).toBe(401);
  });

  it("returns 400 when BYOK key header missing", async () => {
    const res = await POST(new Request("http://localhost/api/byok/test", { method: "POST" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });

  it("returns 400 for invalid OpenAI key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "not-a-key", "x-byok-provider": "openai" },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("sk-");
  });
});
