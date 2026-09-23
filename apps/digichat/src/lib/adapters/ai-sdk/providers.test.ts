import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { chat, responses, createOpenAI } = vi.hoisted(() => {
  const chat = vi.fn((model: string) => ({ model, kind: "chat" }));
  const responses = vi.fn((model: string) => ({ model, kind: "responses" }));
  const createOpenAI = vi.fn(() => ({ chat, responses }));
  return { chat, responses, createOpenAI };
});

vi.mock("@ai-sdk/openai", () => ({ createOpenAI }));

import {
  BackendCredentialError,
  readBackendApiKey,
  resolveAiSdkModel,
} from "./providers";

const BASE = {
  baseUrl: "https://api.example.com/v1",
  model: "gpt-4o-mini",
  apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
} as const;

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("DIGICHAT_BACKEND_EXAMPLE_KEY", "sk-test");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("resolveAiSdkModel (#4535)", () => {
  it("uses the Responses API for openai-responses", () => {
    const model = resolveAiSdkModel({ ...BASE, type: "openai-responses" });
    expect(createOpenAI).toHaveBeenCalledWith({
      baseURL: BASE.baseUrl,
      apiKey: "sk-test",
      name: "openai-responses",
    });
    expect(responses).toHaveBeenCalledWith("gpt-4o-mini");
    expect(chat).not.toHaveBeenCalled();
    expect(model).toEqual({ model: "gpt-4o-mini", kind: "responses" });
  });

  it("uses Chat Completions for openai-completions", () => {
    const model = resolveAiSdkModel({ ...BASE, type: "openai-completions" });
    expect(chat).toHaveBeenCalledWith("gpt-4o-mini");
    expect(responses).not.toHaveBeenCalled();
    expect(model).toEqual({ model: "gpt-4o-mini", kind: "chat" });
  });

  it("throws a credential error naming the env var when the key is unset", () => {
    vi.stubEnv("DIGICHAT_BACKEND_EXAMPLE_KEY", "");
    expect(() => readBackendApiKey("DIGICHAT_BACKEND_EXAMPLE_KEY")).toThrow(
      BackendCredentialError,
    );
    expect(() => resolveAiSdkModel({ ...BASE, type: "openai-completions" })).toThrow(
      /DIGICHAT_BACKEND_EXAMPLE_KEY/,
    );
    expect(createOpenAI).not.toHaveBeenCalled();
  });
});
