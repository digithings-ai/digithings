import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import * as assets from "@digithings/ui/replay/assets";

describe("GET /api/replay-assets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
  });

  it("returns 401 without a session", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(new Request("http://localhost/api/replay-assets"));
    expect(res.status).toBe(401);
  });

  it("returns the inlined chat stylesheet", async () => {
    const res = await GET(new Request("http://localhost/api/replay-assets"));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/css");
    const css = await res.text();
    expect(css).toContain("@font-face");
    expect(css).toContain(".aui-user-message-content");
    expect(css).not.toMatch(/https?:\/\/[^"'\s]+woff2/);
  });

  it("answers 503 when the stylesheets are not on disk", async () => {
    const spy = vi.spyOn(assets, "loadReplayStyles").mockImplementation(() => {
      throw new Error("replay stylesheets not found");
    });
    const res = await GET(new Request("http://localhost/api/replay-assets"));
    expect(res.status).toBe(503);
    spy.mockRestore();
  });
});
