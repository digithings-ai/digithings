import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  BACKEND_ADAPTERS,
  backendAdapterFor,
  DEFAULT_BACKEND_TYPE,
  isDigigraphConfig,
  isFoundryConfig,
  type BackendType,
} from "./backend-adapters";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

const TYPES: BackendType[] = ["digigraph", "foundry"];

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
});
