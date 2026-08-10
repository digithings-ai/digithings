import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

const cookieStore = new Map<string, string>();

vi.mock("@/auth", () => ({
  auth: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) => {
      const value = cookieStore.get(name);
      return value ? { name, value } : undefined;
    },
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  })),
}));

vi.mock("@/lib/ecosystem", () => ({
  ENDPOINTS_COOKIE: "digichat_endpoints",
  getEcosystemDefaults: vi.fn(() => ({
    digigraphUrl: "http://127.0.0.1:8000",
    digiquantUrl: "http://127.0.0.1:8001",
    digismithUrl: "http://127.0.0.1:8003",
    digisearchUrl: "",
  })),
  getEcosystemEndpoints: vi.fn(async () => ({
    digigraphUrl: "http://127.0.0.1:8000",
    digiquantUrl: "http://127.0.0.1:8001",
    digismithUrl: "http://127.0.0.1:8003",
    digisearchUrl: "",
  })),
  parseEndpointsPayload: vi.fn(),
  withDigisearchCapability: vi.fn((v: unknown) => v),
}));

import { auth } from "@/auth";
import { parseEndpointsPayload } from "@/lib/ecosystem";

describe("/api/ecosystem/config", () => {
  beforeEach(() => {
    cookieStore.clear();
    vi.mocked(auth).mockResolvedValue({ user: { id: "user-1" } } as never);
  });

  it("GET returns 401 without session", async () => {
    vi.mocked(auth).mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("GET returns effective endpoints for signed-in user", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.effective.digigraphUrl).toContain("8000");
    expect(body.persistence.serverDatabaseConfigured).toBe(false);
  });

  it("POST returns 400 for invalid endpoints payload", async () => {
    vi.mocked(parseEndpointsPayload).mockReturnValue(null);
    const res = await POST(
      new Request("http://localhost/api/ecosystem/config", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ digigraphUrl: "bad" }),
      })
    );
    expect(res.status).toBe(400);
  });
});
