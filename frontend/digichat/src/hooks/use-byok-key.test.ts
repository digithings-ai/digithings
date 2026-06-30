import { describe, expect, it } from "vitest";
import {
  isOpenRouterKey,
  normalizeOpenRouterModel,
} from "@/lib/byok-openrouter";
import { validateBYOKKey, validateBYOKModel } from "@/hooks/use-byok-key";

describe("validateBYOKKey", () => {
  it("returns null for a valid OpenAI key", () => {
    expect(validateBYOKKey("sk-proj-abc123", "openai")).toBeNull();
  });

  it("returns null for a valid Anthropic key", () => {
    expect(validateBYOKKey("sk-ant-api03-xyz", "anthropic")).toBeNull();
  });

  it("returns null for a valid OpenRouter key", () => {
    expect(validateBYOKKey("sk-or-v1-abc123", "openrouter")).toBeNull();
  });

  it("errors on empty key", () => {
    expect(validateBYOKKey("", "openai")).not.toBeNull();
  });

  it("errors when OpenAI key does not start with sk-", () => {
    expect(validateBYOKKey("not-a-key", "openai")).toMatch(/sk-/);
  });

  it("errors when Anthropic key does not start with sk-ant-", () => {
    expect(validateBYOKKey("sk-wrong", "anthropic")).toMatch(/sk-ant-/);
  });

  it("errors when OpenRouter key does not start with sk-or-", () => {
    expect(validateBYOKKey("sk-proj-abc", "openrouter")).toMatch(/sk-or-/);
  });

  it("accepts OpenAI key starting with sk- that contains ant (not a prefix match confusion)", () => {
    expect(validateBYOKKey("sk-ant-bad", "openai")).toBeNull();
  });

  it("rejects Anthropic key that only starts with sk-", () => {
    expect(validateBYOKKey("sk-only", "anthropic")).not.toBeNull();
  });
});

describe("validateBYOKModel", () => {
  it("requires model for OpenRouter", () => {
    expect(validateBYOKModel("", "openrouter")).not.toBeNull();
    expect(validateBYOKModel("openai/gpt-4o-mini", "openrouter")).toBeNull();
  });

  it("does not require model for other providers", () => {
    expect(validateBYOKModel("", "openai")).toBeNull();
  });
});

describe("normalizeOpenRouterModel", () => {
  it("strips openrouter/ prefix", () => {
    expect(normalizeOpenRouterModel("openrouter/openai/gpt-4o")).toBe("openai/gpt-4o");
  });

  it("passes through bare slugs", () => {
    expect(normalizeOpenRouterModel("anthropic/claude-sonnet-4")).toBe(
      "anthropic/claude-sonnet-4"
    );
  });
});

describe("isOpenRouterKey", () => {
  it("matches sk-or- prefix", () => {
    expect(isOpenRouterKey("sk-or-v1-test")).toBe(true);
    expect(isOpenRouterKey("sk-proj-test")).toBe(false);
  });
});
