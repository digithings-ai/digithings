import { describe, it, expect } from "vitest";
import {
  MODEL_POOL,
  resolveDigivaultLlmRoute,
  validateDigivaultByokKey,
} from "./digivault-byok";

describe("validateDigivaultByokKey", () => {
  it("accepts provider prefixes and rejects bad ones without echoing keys", () => {
    expect(validateDigivaultByokKey("sk-or-v1-abc", "openrouter")).toBeNull();
    expect(validateDigivaultByokKey("sk-abc", "openai")).toBeNull();
    expect(validateDigivaultByokKey("sk-ant-abc", "anthropic")).toBeNull();
    expect(validateDigivaultByokKey("AIzaSy", "gemini")).toBeNull();
    const bad = validateDigivaultByokKey("wrong-key-material", "gemini");
    expect(bad).toMatch(/Gemini keys start with AI/);
    expect(bad).not.toContain("wrong-key");
  });
});

describe("resolveDigivaultLlmRoute", () => {
  it("uses free pool when no BYOK key", () => {
    const route = resolveDigivaultLlmRoute({ openRouterKey: "sk-or-pool" });
    expect(route).toMatchObject({
      kind: "openai_compat",
      isFreePool: true,
      models: [...MODEL_POOL],
      url: "https://openrouter.ai/api/v1/chat/completions",
    });
  });

  it("returns 400 on bad key prefix", () => {
    const route = resolveDigivaultLlmRoute({
      openRouterKey: "sk-or-pool",
      byokKey: "not-a-key",
      byokProvider: "openrouter",
    });
    expect(route).toEqual({
      error: "OpenRouter keys start with sk-or-.",
      status: 400,
    });
  });

  it("resolves gemini OpenAI-compat URL", () => {
    const route = resolveDigivaultLlmRoute({
      openRouterKey: "sk-or-pool",
      byokKey: "AIzaSyTest",
      byokProvider: "gemini",
    });
    expect(route).toMatchObject({
      kind: "openai_compat",
      url: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
      model: "gemini-2.5-flash",
      isFreePool: false,
    });
  });

  it("resolves anthropic kind", () => {
    const route = resolveDigivaultLlmRoute({
      openRouterKey: "sk-or-pool",
      byokKey: "sk-ant-test",
      byokProvider: "anthropic",
    });
    expect(route).toMatchObject({
      kind: "anthropic",
      model: "claude-3-5-haiku-20241022",
    });
  });

  it("returns 503 when free pool key missing", () => {
    expect(resolveDigivaultLlmRoute({ openRouterKey: "" })).toEqual({
      error: "chat not configured",
      status: 503,
    });
  });
});
