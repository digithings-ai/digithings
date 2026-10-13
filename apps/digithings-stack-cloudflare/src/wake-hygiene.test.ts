import { describe, expect, it } from "vitest";
import {
  containerIsAwake,
  isHealthProbe,
  isScannerPath,
  sleepingHealthResponse,
} from "./wake-hygiene";

describe("wake hygiene", () => {
  it("flags scanner paths and leaves real routes alone", () => {
    for (const p of ["/.env", "/.git/config", "/server-info.php", "/wp-login.php", "/x/y.aspx"]) {
      expect(isScannerPath(p)).toBe(true);
    }
    for (const p of ["/", "/health", "/v1/chat/completions", "/mcp", "/v1/oauth/token", "/.well-known/jwks.json", "/query"]) {
      expect(isScannerPath(p)).toBe(false);
    }
  });

  it("treats only GET/HEAD /health and /healthz as probes", () => {
    expect(isHealthProbe(new Request("https://graph.digithings.ai/health"), "/health")).toBe(true);
    expect(isHealthProbe(new Request("https://key.digithings.ai/healthz", { method: "HEAD" }), "/healthz")).toBe(true);
    expect(isHealthProbe(new Request("https://graph.digithings.ai/health", { method: "POST" }), "/health")).toBe(false);
    expect(isHealthProbe(new Request("https://graph.digithings.ai/healthcheck"), "/healthcheck")).toBe(false);
  });

  it("proxies deep health only when the container is already up", () => {
    expect(containerIsAwake("running")).toBe(true);
    expect(containerIsAwake("healthy")).toBe(true);
    for (const s of ["stopped", "stopping", "stopped_with_code", undefined]) {
      expect(containerIsAwake(s)).toBe(false);
    }
  });

  it("answers a sleeping probe with 200 ok", async () => {
    const res = sleepingHealthResponse(new Request("https://graph.digithings.ai/health"));
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ status: "ok", container: "sleeping" });
  });
});
