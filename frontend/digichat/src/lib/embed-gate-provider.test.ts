import { describe, it, expect, vi, afterEach } from "vitest";
import { consumeChatAccess } from "./embed-gate-provider";

afterEach(() => vi.restoreAllMocks());

describe("consumeChatAccess", () => {
  it("allows on 200", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("allow");
  });

  it("denies on 402", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("spent", { status: 402 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("deny");
  });

  it("denies on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("bad token", { status: 401 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("deny");
  });

  // Availability over strictness: an outage in the quota service must not break chat on every
  // embedding site. The documented consequence is that the cap is soft by construction.
  it("allows on a 500", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("allow");
  });

  it("allows when the request throws", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("network down");
    }));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("allow");
  });
});
