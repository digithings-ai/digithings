import { afterEach, describe, expect, it } from "vitest";

import { isAllowedServiceUrl, parseEndpointsPayload } from "./ecosystem";

describe("isAllowedServiceUrl", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_ALLOW_PRIVATE_ENDPOINTS;
    delete process.env.DIGICHAT_ENDPOINT_HOST_ALLOWLIST;
  });

  it("allows localhost and docker service names", () => {
    expect(isAllowedServiceUrl("http://127.0.0.1:8000")).toBe(true);
    expect(isAllowedServiceUrl("http://localhost:8000")).toBe(true);
    expect(isAllowedServiceUrl("http://digigraph:8000")).toBe(true);
  });

  it("blocks private RFC1918 unless explicitly allowed", () => {
    expect(isAllowedServiceUrl("http://10.0.0.5:8000")).toBe(false);
    process.env.DIGICHAT_ALLOW_PRIVATE_ENDPOINTS = "1";
    expect(isAllowedServiceUrl("http://10.0.0.5:8000")).toBe(true);
  });

  it("rejects non-http schemes and userinfo", () => {
    expect(isAllowedServiceUrl("ftp://digigraph:8000")).toBe(false);
    expect(isAllowedServiceUrl("http://user:pass@digigraph:8000")).toBe(false);
  });

  it("honors host allowlist when set", () => {
    process.env.DIGICHAT_ENDPOINT_HOST_ALLOWLIST = "digithings.internal";
    expect(isAllowedServiceUrl("http://api.digithings.internal:8000")).toBe(true);
    expect(isAllowedServiceUrl("http://evil.example:8000")).toBe(false);
  });
});

describe("parseEndpointsPayload", () => {
  it("rejects disallowed URLs", () => {
    expect(
      parseEndpointsPayload({
        digigraphUrl: "http://127.0.0.1:8000",
        digiquantUrl: "http://10.0.0.1:8001",
        digismithUrl: "http://127.0.0.1:8003",
      })
    ).toBeNull();
  });

  it("accepts valid ecosystem payload", () => {
    const parsed = parseEndpointsPayload({
      digigraphUrl: "http://127.0.0.1:8000",
      digiquantUrl: "http://127.0.0.1:8001",
      digismithUrl: "http://127.0.0.1:8003",
      digisearchUrl: "http://127.0.0.1:8002",
    });
    expect(parsed?.digigraphUrl).toBe("http://127.0.0.1:8000");
    expect(parsed?.digisearchUrl).toBe("http://127.0.0.1:8002");
  });
});
