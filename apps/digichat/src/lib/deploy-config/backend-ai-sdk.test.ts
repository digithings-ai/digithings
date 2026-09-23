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

const ANTHROPIC = {
  type: "anthropic",
  model: "claude-sonnet-4-5",
  apiKeyEnv: "DIGICHAT_BACKEND_ANTHROPIC_KEY",
} as const;

const VERTEX = {
  type: "google-vertex",
  project: "my-project",
  location: "us-central1",
  model: "gemini-2.5-pro",
} as const;

describe("Anthropic + Vertex backend schema (#4539)", () => {
  it("accepts an anthropic backend", () => {
    expect(parse(ANTHROPIC).deployment?.backend).toEqual(ANTHROPIC);
  });

  it("accepts a google-vertex backend", () => {
    expect(parse(VERTEX).deployment?.backend).toEqual(VERTEX);
  });

  it("rejects an anthropic apiKeyEnv that is not DIGICHAT_BACKEND_*", () => {
    expect(() => parse({ ...ANTHROPIC, apiKeyEnv: "AUTH_SECRET" })).toThrow(
      /apiKeyEnv/,
    );
  });

  it("rejects an empty anthropic model", () => {
    expect(() => parse({ ...ANTHROPIC, model: "" })).toThrow();
  });

  it("rejects a vertex backend missing project, location, or model", () => {
    expect(() => parse({ ...VERTEX, project: "" })).toThrow();
    expect(() => parse({ ...VERTEX, location: "" })).toThrow();
    expect(() => parse({ ...VERTEX, model: "" })).toThrow();
  });
});

describe("Anthropic + Vertex backend in the tenant registry (#4539)", () => {
  const entry = (backend: unknown) =>
    JSON.stringify({
      "example.com": { slug: "example", backend, gateMode: "ungated", token: "t" },
    });

  it("accepts an anthropic tenant", () => {
    const tenant = parseEmbedTenants(entry(ANTHROPIC)).get("example.com");
    expect(tenant?.backend).toEqual(ANTHROPIC);
  });

  it("accepts a google-vertex tenant", () => {
    const tenant = parseEmbedTenants(entry(VERTEX)).get("example.com");
    expect(tenant?.backend).toEqual(VERTEX);
  });

  it("rejects an anthropic apiKeyEnv outside the DIGICHAT_BACKEND_ prefix", () => {
    expect(() =>
      parseEmbedTenants(entry({ ...ANTHROPIC, apiKeyEnv: "DIGIKEY_BFF_TOKEN" })),
    ).toThrow(/apiKeyEnv/);
  });

  it("rejects a google-vertex tenant missing location", () => {
    const { location: _omit, ...rest } = VERTEX;
    void _omit;
    expect(() => parseEmbedTenants(entry(rest))).toThrow(/location/);
  });
});
