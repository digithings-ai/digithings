import { describe, it, expect, vi, afterEach } from "vitest";
import { consumeChatAccess } from "./embed-gate-provider";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

  it.each([400, 403])("denies invalid-token client errors (%s)", async (status) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("invalid token", { status })));
    expect(await consumeChatAccess("https://api.test/consume", "garbage")).toBe("deny");
  });

  // Availability over strictness: an outage in the quota service must not break chat
  // on every embedding site. The outage is REPORTED as a third verdict rather than
  // allowed, so the caller can admit the visitor and bound the entitlement
  // server-side instead of granting it outright. The provider only reports the
  // verdict; the caller is the one that logs the degraded path.
  it("reports unavailable on a 500", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("unavailable");
  });

  it("reports unavailable on a 503", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("unavailable", { status: 503 })));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("unavailable");
  });

  it("reports unavailable when the request throws", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("network down");
    }));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("unavailable");
  });

  it("reports unavailable when the request times out", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      const err = new Error("The operation was aborted due to timeout");
      err.name = "TimeoutError";
      throw err;
    }));
    expect(await consumeChatAccess("https://api.test/consume", "id.secret")).toBe("unavailable");
  });
});
