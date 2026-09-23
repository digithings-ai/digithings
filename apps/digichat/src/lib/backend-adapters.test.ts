import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  AI_SDK_PROTOCOLS,
  BACKEND_ADAPTERS,
  backendAdapterFor,
  DEFAULT_BACKEND_TYPE,
  isAiSdkConfig,
  isDigigraphConfig,
  isFoundryConfig,
  type BackendType,
} from "./backend-adapters";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

const TYPES: BackendType[] = [
  "digigraph",
  "foundry",
  "openai-completions",
  "openai-responses",
];

describe("backend adapter registry", () => {
  // Exhaustiveness itself is pinned by the `Record<BackendType, BackendAdapter>`
  // type on BACKEND_ADAPTERS; this test pins the key set at runtime.
  it("describes every backend type", () => {
    for (const type of TYPES) {
      expect(BACKEND_ADAPTERS[type]?.type).toBe(type);
    }
    expect(Object.keys(BACKEND_ADAPTERS).sort()).toEqual([...TYPES].sort());
  });

  it("resolves digigraph to the trace protocol with corpus + MCP", () => {
    const adapter = BACKEND_ADAPTERS.digigraph;
    expect(adapter.protocol).toBe("digigraph-trace");
    expect(adapter.auth).toBe("upstream-bearer");
    expect(adapter.capabilities.corpus).toBe(true);
    expect(adapter.capabilities.mcp).toBe(true);
    expect(adapter.capabilities.webSearch).toBe(true);
  });

  it("resolves foundry to the responses protocol with conversation continuity", () => {
    const adapter = BACKEND_ADAPTERS.foundry;
    expect(adapter.protocol).toBe("foundry-responses");
    expect(adapter.auth).toBe("managed-identity");
    expect(adapter.capabilities.conversationContinuity).toBe(true);
    // The foundry path does not forward corpus scope or operator MCP servers.
    expect(adapter.capabilities.corpus).toBe(false);
    expect(adapter.capabilities.mcp).toBe(false);
  });

  it("resolves the OpenAI AI-SDK backends to their own protocol with env auth", () => {
    for (const type of ["openai-completions", "openai-responses"] as const) {
      const adapter = BACKEND_ADAPTERS[type];
      expect(adapter.protocol).toBe(type);
      expect(adapter.auth).toBe("env");
      expect(AI_SDK_PROTOCOLS.has(adapter.protocol)).toBe(true);
      // No external conversation id / corpus scope / operator MCP on this path.
      expect(adapter.capabilities.conversationContinuity).toBe(false);
      expect(adapter.capabilities.corpus).toBe(false);
      expect(adapter.capabilities.mcp).toBe(false);
      // Turn mutation is not wired for the AI-SDK mapper yet (#4535).
      expect(adapter.capabilities.turnMutation).toBe(false);
    }
  });

  it("every adapter surfaces reasoning and tool calls (the parity invariant)", () => {
    for (const type of TYPES) {
      const { capabilities } = BACKEND_ADAPTERS[type];
      expect(capabilities.reasoning).toBe(true);
      expect(capabilities.toolCalls).toBe(true);
      expect(capabilities.sources).toBe(true);
    }
  });

  it("defaults to digigraph when the deployment declares no backend", () => {
    expect(backendAdapterFor(undefined).type).toBe(DEFAULT_BACKEND_TYPE);
    expect(backendAdapterFor(undefined).protocol).toBe("digigraph-trace");
    expect(backendAdapterFor("foundry").type).toBe("foundry");
  });

  it("narrows the config to the adapter's own shape", () => {
    const digigraph = { type: "digigraph", digisearchIndex: "idx" } as const;
    const foundry = {
      type: "foundry",
      projectEndpoint: "https://example.openai.azure.com",
      agentName: "agent",
    } as const;
    expect(isDigigraphConfig(digigraph)).toBe(true);
    expect(isFoundryConfig(digigraph)).toBe(false);
    expect(isFoundryConfig(foundry)).toBe(true);
    expect(isDigigraphConfig(undefined)).toBe(false);
    expect(isFoundryConfig(undefined)).toBe(false);
  });

  it("narrows the AI-SDK family and excludes the others", () => {
    const completions = {
      type: "openai-completions",
      baseUrl: "https://api.example.com/v1",
      model: "gpt-4o-mini",
      apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
    } as const;
    const responses = { ...completions, type: "openai-responses" } as const;
    expect(isAiSdkConfig(completions)).toBe(true);
    expect(isAiSdkConfig(responses)).toBe(true);
    expect(isAiSdkConfig({ type: "digigraph" } as const)).toBe(false);
    expect(isAiSdkConfig(undefined)).toBe(false);
    expect(isDigigraphConfig(completions)).toBe(false);
  });
});

describe("chat route backend selection", () => {
  // The registry is the single source of truth: the handler must choose its
  // streaming path from the adapter, not from a raw `backend.type` comparison.
  // Comments are stripped first so a future comment quoting the pattern does
  // not fail the guard spuriously.
  const route = read("../app/api/chat/route.ts").replace(/\/\/.*$/gm, "");

  it("never compares backend.type in the handler", () => {
    expect(route).not.toMatch(
      /backend\??\.type\s*(===|!==|==|!=)|switch\s*\(\s*backend\??\.type/,
    );
  });

  it("selects the streaming path from the adapter protocol and capabilities", () => {
    expect(route).toMatch(/const adapter = backendAdapterFor\(backend\?\.type\)/);
    expect(route).toMatch(/adapter\.protocol === "foundry-responses"/);
    expect(route).toMatch(/adapter\.capabilities\.corpus/);
  });

  it("routes the AI-SDK protocols through the shared mapper", () => {
    expect(route).toMatch(/AI_SDK_PROTOCOLS\.has\(adapter\.protocol\)/);
    expect(route).toMatch(/isAiSdkConfig\(backend\)/);
    expect(route).toMatch(/createAiSdkStreamResponse\(/);
  });
});
