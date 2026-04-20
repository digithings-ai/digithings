import { describe, expect, it } from "vitest";
import { validateBYOKKey } from "@/hooks/use-byok-key";

describe("validateBYOKKey", () => {
  it("returns null for a valid OpenAI key", () => {
    expect(validateBYOKKey("sk-proj-abc123", "openai")).toBeNull();
  });

  it("returns null for a valid Anthropic key", () => {
    expect(validateBYOKKey("sk-ant-api03-xyz", "anthropic")).toBeNull();
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

  it("accepts OpenAI key starting with sk- that contains ant (not a prefix match confusion)", () => {
    // sk-ant- is the Anthropic pattern; sk- alone is OpenAI
    expect(validateBYOKKey("sk-ant-bad", "openai")).toBeNull();
  });

  it("rejects Anthropic key that only starts with sk-", () => {
    expect(validateBYOKKey("sk-only", "anthropic")).not.toBeNull();
  });
});
