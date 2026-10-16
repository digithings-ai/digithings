import { describe, expect, it } from "vitest";
import app from "./index";
import { corsHeaders, resolveAllowlist } from "./cors";

const ORIGIN = "https://digiquant.io";

describe("resolveAllowlist", () => {
  it("defaults include the production dashboard and loopbacks", () => {
    const list = resolveAllowlist({});
    expect(list).toContain("https://digiquant.io");
    expect(list).toContain("http://127.0.0.1:3101");
  });

  it("env override replaces the default with a comma list", () => {
    const list = resolveAllowlist({ DASHBOARD_API_ALLOWED_ORIGINS: "https://a.example, https://b.example" });
    expect(list).toEqual(["https://a.example", "https://b.example"]);
  });
});

describe("corsHeaders", () => {
  it("echoes an allowlisted origin with Vary", () => {
    const headers = corsHeaders(ORIGIN, [ORIGIN]);
    expect(headers["Access-Control-Allow-Origin"]).toBe(ORIGIN);
    expect(headers["Vary"]).toBe("Origin");
    expect(headers["Access-Control-Allow-Methods"]).toContain("OPTIONS");
  });

  it("emits no allow-origin for a foreign origin", () => {
    const headers = corsHeaders("https://evil.example", [ORIGIN]);
    expect(headers["Access-Control-Allow-Origin"]).toBeUndefined();
    expect(headers["Vary"]).toBe("Origin");
  });
});

describe("worker CORS integration", () => {
  it("GET /portfolio carries the allow-origin header", async () => {
    const res = await app.fetch(
      new Request("https://api.test/portfolio?retrieval_pin=p", { headers: { origin: ORIGIN } }),
      {},
    );
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(ORIGIN);
    expect(res.headers.get("Vary")).toBe("Origin");
  });

  it("OPTIONS preflights to 204 with allow headers", async () => {
    const res = await app.fetch(
      new Request("https://api.test/portfolio", { method: "OPTIONS", headers: { origin: ORIGIN } }),
      {},
    );
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(ORIGIN);
    expect((res.headers.get("Access-Control-Allow-Methods") ?? "").split(",").map((m) => m.trim())).toContain(
      "OPTIONS",
    );
  });

  it("foreign origin gets no allow-origin header", async () => {
    const res = await app.fetch(
      new Request("https://api.test/portfolio", { headers: { origin: "https://evil.example" } }),
      {},
    );
    expect(res.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });

  it("error responses (unknown route) still carry CORS", async () => {
    const res = await app.fetch(
      new Request("https://api.test/nope", { headers: { origin: ORIGIN } }),
      {},
    );
    expect(res.status).toBe(400);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(ORIGIN);
  });
});
