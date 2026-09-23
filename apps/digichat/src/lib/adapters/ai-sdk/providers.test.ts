import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  chat,
  responses,
  createOpenAI,
  anthropicMessages,
  createAnthropic,
  vertexModel,
  createVertex,
} = vi.hoisted(() => {
  const chat = vi.fn((model: string) => ({ model, kind: "chat" }));
  const responses = vi.fn((model: string) => ({ model, kind: "responses" }));
  const createOpenAI = vi.fn(() => ({ chat, responses }));
  const anthropicMessages = vi.fn((model: string) => ({ model, kind: "anthropic" }));
  const createAnthropic = vi.fn(() => anthropicMessages);
  const vertexModel = vi.fn((model: string) => ({ model, kind: "vertex" }));
  const createVertex = vi.fn(() => vertexModel);
  return {
    chat,
    responses,
    createOpenAI,
    anthropicMessages,
    createAnthropic,
    vertexModel,
    createVertex,
  };
});

vi.mock("@ai-sdk/openai", () => ({ createOpenAI }));
vi.mock("@ai-sdk/anthropic", () => ({ createAnthropic }));
vi.mock("@ai-sdk/google-vertex", () => ({ createVertex }));

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

  it("uses the Anthropic provider with the key from the named env var (#4539)", () => {
    vi.stubEnv("DIGICHAT_BACKEND_ANTHROPIC_KEY", "sk-ant-test");
    const model = resolveAiSdkModel({
      type: "anthropic",
      model: "claude-sonnet-4-5",
      apiKeyEnv: "DIGICHAT_BACKEND_ANTHROPIC_KEY",
    });
    expect(createAnthropic).toHaveBeenCalledWith({
      apiKey: "sk-ant-test",
      name: "anthropic",
    });
    expect(anthropicMessages).toHaveBeenCalledWith("claude-sonnet-4-5");
    expect(model).toEqual({ model: "claude-sonnet-4-5", kind: "anthropic" });
  });

  it("uses the Vertex provider with project + location and no credential (#4539)", () => {
    const model = resolveAiSdkModel({
      type: "google-vertex",
      project: "my-project",
      location: "us-central1",
      model: "gemini-2.5-pro",
    });
    expect(createVertex).toHaveBeenCalledWith({
      project: "my-project",
      location: "us-central1",
    });
    expect(vertexModel).toHaveBeenCalledWith("gemini-2.5-pro");
    expect(model).toEqual({ model: "gemini-2.5-pro", kind: "vertex" });
  });

  it("throws for anthropic when its key env var is unset", () => {
    vi.stubEnv("DIGICHAT_BACKEND_ANTHROPIC_KEY", "");
    expect(() =>
      resolveAiSdkModel({
        type: "anthropic",
        model: "claude-sonnet-4-5",
        apiKeyEnv: "DIGICHAT_BACKEND_ANTHROPIC_KEY",
      }),
    ).toThrow(/DIGICHAT_BACKEND_ANTHROPIC_KEY/);
    expect(createAnthropic).not.toHaveBeenCalled();
  });
});
