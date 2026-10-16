/**
 * LangGraph / AG-UI / A2A backend config (#4543).
 *
 * The YAML schema (`.strict()`) and the `DIGICHAT_EMBED_TENANTS` validator are
 * two independent parsers for the same contract, so both are pinned here —
 * including the https-only URL rule and the optional `DIGICHAT_BACKEND_*`
 * credential name.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseDigichatConfig } from "./schema";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

const parse = (backend: unknown) =>
  parseDigichatConfig({ version: 1, deployment: { slug: "acme", backend } });

const entry = (backend: unknown) =>
  JSON.stringify({
    "example.com": { slug: "example", backend, gateMode: "ungated", token: "t" },
  });

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("non-AI-SDK backend schema (#4543)", () => {
  it("accepts langgraph, ag-ui and a2a", () => {
    const langgraph = { type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" };
    const agui = { type: "ag-ui", url: "https://agui.example.com/run" };
    const a2a = { type: "a2a", baseUrl: "https://a2a.example.com" };
    expect(parse(langgraph).deployment?.backend).toEqual(langgraph);
    expect(parse(agui).deployment?.backend).toEqual(agui);
    expect(parse(a2a).deployment?.backend).toEqual(a2a);
  });

  it("accepts an optional DIGICHAT_BACKEND_* apiKeyEnv", () => {
    expect(
      parse({
        type: "a2a",
        baseUrl: "https://a2a.example.com",
        apiKeyEnv: "DIGICHAT_BACKEND_A2A_KEY",
      }).deployment?.backend,
    ).toEqual({
      type: "a2a",
      baseUrl: "https://a2a.example.com",
      apiKeyEnv: "DIGICHAT_BACKEND_A2A_KEY",
    });
  });

  it("rejects a plain-http URL", () => {
    expect(() => parse({ type: "ag-ui", url: "http://agui.example.com" })).toThrow(/https/);
  });

  it("rejects an apiKeyEnv outside the DIGICHAT_BACKEND_ prefix", () => {
    expect(() =>
      parse({ type: "a2a", baseUrl: "https://a2a.example.com", apiKeyEnv: "AUTH_SECRET" }),
    ).toThrow(/apiKeyEnv/);
  });

  it("requires assistantId on langgraph", () => {
    expect(() => parse({ type: "langgraph", apiUrl: "https://lg.example.com" })).toThrow();
  });

  it("rejects unknown keys on the strict schema", () => {
    expect(() =>
      parse({ type: "a2a", baseUrl: "https://a2a.example.com", model: "nope" }),
    ).toThrow();
  });
});

describe("non-AI-SDK backend in the tenant registry (#4543)", () => {
  it("accepts the three shapes", () => {
    expect(
      parseEmbedTenants(
        entry({ type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" }),
      ).get("example.com")?.backend,
    ).toEqual({ type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" });
    expect(
      parseEmbedTenants(entry({ type: "ag-ui", url: "https://agui.example.com/run" })).get(
        "example.com",
      )?.backend,
    ).toEqual({ type: "ag-ui", url: "https://agui.example.com/run" });
    expect(
      parseEmbedTenants(entry({ type: "a2a", baseUrl: "https://a2a.example.com" })).get(
        "example.com",
      )?.backend,
    ).toEqual({ type: "a2a", baseUrl: "https://a2a.example.com" });
  });

  it("carries a valid apiKeyEnv and rejects a non-prefixed one", () => {
    expect(
      parseEmbedTenants(
        entry({
          type: "ag-ui",
          url: "https://agui.example.com/run",
          apiKeyEnv: "DIGICHAT_BACKEND_AGUI_KEY",
        }),
      ).get("example.com")?.backend,
    ).toEqual({
      type: "ag-ui",
      url: "https://agui.example.com/run",
      apiKeyEnv: "DIGICHAT_BACKEND_AGUI_KEY",
    });
    expect(() =>
      parseEmbedTenants(
        entry({ type: "ag-ui", url: "https://agui.example.com/run", apiKeyEnv: "DIGIKEY_BFF_TOKEN" }),
      ),
    ).toThrow(/apiKeyEnv/);
  });

  it("rejects a non-https URL and a missing assistantId", () => {
    expect(() => parseEmbedTenants(entry({ type: "a2a", baseUrl: "http://a2a.example.com" }))).toThrow(
      /https/,
    );
    expect(() =>
      parseEmbedTenants(entry({ type: "langgraph", apiUrl: "https://lg.example.com" })),
    ).toThrow(/assistantId/);
  });

  it("names every type in the rejection message", () => {
    expect(() => parseEmbedTenants(entry({ type: "nope" }))).toThrow(/langgraph/);
  });
});
