import { describe, expect, it } from "vitest";
import { dataPlaneEnv, type Env } from "./env";

function env(over: Partial<Env> = {}): Env {
  return {
    TWELVEX_CONTAINER: {} as DurableObjectNamespace,
    ...over,
  };
}

describe("dataPlaneEnv", () => {
  it("omits an optional variable that is not set instead of forwarding an empty string", () => {
    const forwarded = dataPlaneEnv(env());
    expect("TWELVEX_SUPABASE_URL" in forwarded).toBe(false);
    expect("PRIMEMARKET_SESSION_TOKEN" in forwarded).toBe(false);
    expect("TWELVEX_SUPABASE_SERVICE_KEY" in forwarded).toBe(false);
    expect("OPENAI_API_KEY" in forwarded).toBe(false);
    expect("CORE_SUPABASE_SERVICE_KEY" in forwarded).toBe(false);
    expect("OPENAI_API_BASE" in forwarded).toBe(false);
  });

  it("forwards an optional variable that is set", () => {
    const forwarded = dataPlaneEnv(
      env({
        TWELVEX_SUPABASE_URL: "https://example.supabase.co",
        TWELVEX_SUPABASE_SERVICE_KEY: "service-key-value",
      }),
    );
    expect(forwarded.TWELVEX_SUPABASE_URL).toBe("https://example.supabase.co");
    expect(forwarded.TWELVEX_SUPABASE_SERVICE_KEY).toBe("service-key-value");
  });

  it("forwards the FX research keys under the names the workflow uses", () => {
    const forwarded = dataPlaneEnv(
      env({
        CHEAPERINFERENCE_API_KEY: "cheaper-key-value",
        CORE_SUPABASE_SERVICE_KEY: "core-key-value",
        OPENAI_API_BASE: "https://api.cheaperinference.com/v1",
      }),
    );
    expect(forwarded.OPENAI_API_KEY).toBe("cheaper-key-value");
    expect(forwarded.CORE_SUPABASE_SERVICE_KEY).toBe("core-key-value");
    expect(forwarded.OPENAI_API_BASE).toBe("https://api.cheaperinference.com/v1");
    expect("CHEAPERINFERENCE_API_KEY" in forwarded).toBe(false);
  });

  it("always sets DRY_RUN and never forwards the auth tokens", () => {
    const forwarded = dataPlaneEnv(
      env({ RUNNER_AUTH_TOKEN: "runner-token", GH_ISSUES_TOKEN: "issues-token" }),
    );
    expect(forwarded.DRY_RUN).toBe("0");
    expect("RUNNER_AUTH_TOKEN" in forwarded).toBe(false);
    expect("GH_ISSUES_TOKEN" in forwarded).toBe(false);
    expect(dataPlaneEnv(env({ DRY_RUN: "1" })).DRY_RUN).toBe("1");
  });
});
