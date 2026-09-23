import { afterEach, describe, expect, it, vi } from "vitest";
import { parseDigichatConfig } from "./schema";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

const AI_SDK = {
  type: "openai-completions",
  baseUrl: "https://api.example.com/v1",
  model: "gpt-4o-mini",
  apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
} as const;

const parse = (backend: unknown) =>
  parseDigichatConfig({ version: 1, deployment: { slug: "acme", backend } });

describe("AI-SDK backend schema (#4535)", () => {
  it("accepts both OpenAI wire formats", () => {
    for (const type of ["openai-completions", "openai-responses"] as const) {
      const cfg = parse({ ...AI_SDK, type });
      expect(cfg.deployment?.backend.type).toBe(type);
    }
  });

  it("rejects a non-https baseUrl", () => {
    expect(() => parse({ ...AI_SDK, baseUrl: "http://api.example.com/v1" })).toThrow(
      /https/,
    );
  });

  it("rejects an apiKeyEnv that is not DIGICHAT_BACKEND_*", () => {
    // A tenant must never be able to name AUTH_SECRET and have the BFF ship it
    // as a Bearer token to an attacker-controlled baseUrl.
    expect(() => parse({ ...AI_SDK, apiKeyEnv: "AUTH_SECRET" })).toThrow(/apiKeyEnv/);
  });

  it("rejects an empty model", () => {
    expect(() => parse({ ...AI_SDK, model: "" })).toThrow();
  });
});

describe("AI-SDK backend in the tenant registry (#4535)", () => {
  const entry = (backend: unknown) =>
    JSON.stringify({
      "example.com": { slug: "example", backend, gateMode: "ungated", token: "t" },
    });

  it("accepts an openai-responses tenant", () => {
    const tenant = parseEmbedTenants(
      entry({ ...AI_SDK, type: "openai-responses" }),
    ).get("example.com");
    expect(tenant?.backend).toEqual({ ...AI_SDK, type: "openai-responses" });
  });

  it("rejects an apiKeyEnv outside the DIGICHAT_BACKEND_ prefix", () => {
    expect(() =>
      parseEmbedTenants(entry({ ...AI_SDK, apiKeyEnv: "DIGIKEY_BFF_TOKEN" })),
    ).toThrow(/apiKeyEnv/);
  });

  it("rejects a non-https baseUrl", () => {
    expect(() =>
      parseEmbedTenants(entry({ ...AI_SDK, baseUrl: "http://api.example.com" })),
    ).toThrow(/https/);
  });
});
