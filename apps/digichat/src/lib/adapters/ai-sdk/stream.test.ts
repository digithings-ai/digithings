/**
 * AI-SDK mapper wiring (#4552).
 *
 * `createAiSdkStreamResponse` is the one place every AI-SDK backend streams
 * through, so the two things that make provider citations visible live here:
 * `sendSources: true` on `toUIMessageStream` (off by default in AI SDK v7, so a
 * grounded answer would otherwise arrive with its citations stripped) and the
 * provider's built-in search tool passed to `streamText` when the web-search
 * gate is on.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ai = vi.hoisted(() => ({
  streamText: vi.fn(() => ({ stream: "MODEL_STREAM" })),
  toUIMessageStream: vi.fn(() => ({ stream: "UI_STREAM" })),
  createUIMessageStreamResponse: vi.fn(
    () => new Response("ok", { status: 200 }),
  ),
  smoothStream: vi.fn(() => (input: unknown) => input),
}));

const providers = vi.hoisted(() => ({
  resolveAiSdkModel: vi.fn(() => "MODEL"),
  resolveAiSdkSearchTools: vi.fn(() => ({ web_search: { marker: "tool" } })),
  BackendCredentialError: class BackendCredentialError extends Error {},
}));

vi.mock("ai", () => ai);
vi.mock("./providers", () => providers);

import { createAiSdkStreamResponse } from "./stream";
import type { AiSdkBackendConfig } from "@/lib/backend-adapters";

const BACKEND = {
  type: "openai-responses",
  baseUrl: "https://api.example.com/v1",
  model: "gpt-5",
  apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
} as unknown as AiSdkBackendConfig;

const opts = {
  backend: BACKEND,
  messages: [],
  responseHeaders: { "X-Test": "1" },
  signal: new AbortController().signal,
};

describe("createAiSdkStreamResponse", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("sends sources and reasoning to the client", async () => {
    await createAiSdkStreamResponse(opts);
    expect(ai.toUIMessageStream).toHaveBeenCalledWith(
      expect.objectContaining({ sendSources: true, sendReasoning: true }),
    );
  });

  it("passes the provider search tool when web search is enabled", async () => {
    await createAiSdkStreamResponse({ ...opts, webSearch: true });
    expect(providers.resolveAiSdkSearchTools).toHaveBeenCalledWith(BACKEND);
    expect(ai.streamText).toHaveBeenCalledWith(
      expect.objectContaining({ tools: { web_search: { marker: "tool" } } }),
    );
  });

  it("passes no tools when web search is off", async () => {
    await createAiSdkStreamResponse(opts);
    expect(providers.resolveAiSdkSearchTools).not.toHaveBeenCalled();
    const call = ai.streamText.mock.calls.at(-1)?.[0] as unknown as Record<
      string,
      unknown
    >;
    expect(call).not.toHaveProperty("tools");
  });

  it("answers 502 without calling the model when the credential is missing", async () => {
    providers.resolveAiSdkModel.mockImplementationOnce(() => {
      throw new providers.BackendCredentialError(
        "DIGICHAT_BACKEND_EXAMPLE_KEY is not set",
      );
    });
    const res = await createAiSdkStreamResponse(opts);
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe("backend_unavailable");
    expect(body.message).toContain("DIGICHAT_BACKEND_EXAMPLE_KEY");
    expect(ai.streamText).not.toHaveBeenCalled();
  });
});
