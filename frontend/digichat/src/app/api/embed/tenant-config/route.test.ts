import { describe, it, expect, afterEach, vi } from "vitest";
import { GET } from "./route";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

const REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: { type: "external-relay", url: "https://relay.example.com/api/digichat" },
    gateMode: "ungated",
    theme: "light",
    accent: { color: "#b5562b", foreground: "#fff7f2" },
    title: "Chat for Help",
    attribution: true,
    token: "datatapstream-secret",
  },
});

describe("GET /api/embed/tenant-config", () => {
  it("returns the client-safe config for a registered host with a valid token — never the backend", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const res = await GET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: {
          "x-embed-host": "https://datatapstream.com",
          "x-embed-token": "datatapstream-secret",
        },
      })
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = await res.json();
    expect(body).toEqual({
      slug: "datatapstream",
      gateMode: "ungated",
      theme: "light",
      accent: { color: "#b5562b", foreground: "#fff7f2" },
      title: "Chat for Help",
      attribution: true,
    });
    expect(JSON.stringify(body)).not.toContain("relay.example.com");
  });

  it("returns legacy defaults for a registered host when the token is missing (#1339)", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const res = await GET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": "https://datatapstream.com" },
      })
    );
    const body = await res.json();
    expect(body).toEqual({
      slug: "embed",
      gateMode: "turn_limited",
      theme: "dark",
      accent: null,
      title: null,
      attribution: false,
    });
  });

  it("returns legacy defaults for unknown hosts", async () => {
    const res = await GET(new Request("http://127.0.0.1/api/embed/tenant-config"));
    expect(await res.json()).toEqual({
      slug: "embed",
      gateMode: "turn_limited",
      theme: "dark",
      accent: null,
      title: null,
      attribution: false,
    });
  });
});
