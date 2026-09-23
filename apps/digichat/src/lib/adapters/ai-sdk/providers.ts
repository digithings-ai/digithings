/**
 * AI-SDK provider factory (Phase 5b, #4535, #4539).
 *
 * One place that turns a `backend` config into a `LanguageModel` for the AI-SDK
 * family, so the route never names a provider package. Adding a provider is one
 * more branch here plus its `@ai-sdk/*` dependency.
 *
 * The credential is read from the env var the config NAMES (`apiKeyEnv`), never
 * from the config body — that is what keeps it off the client and out of the
 * repository. The `DIGICHAT_BACKEND_` prefix on that name is enforced by the
 * schema, so a config can never point at `AUTH_SECRET` and have the BFF ship it
 * to an attacker-controlled `baseUrl`. Vertex is the exception: it carries no
 * credential field at all and uses Application Default Credentials.
 */

import { createAnthropic } from "@ai-sdk/anthropic";
import { createVertex } from "@ai-sdk/google-vertex";
import { createOpenAI } from "@ai-sdk/openai";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import type { LanguageModel, ToolSet } from "ai";
import type { AiSdkBackendConfig } from "@/lib/backend-adapters";

/** Raised when the configured `apiKeyEnv` is missing or empty. */
export class BackendCredentialError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BackendCredentialError";
  }
}

/** Read the upstream key from the env var the config names. Never logs it. */
export function readBackendApiKey(apiKeyEnv: string): string {
  const key = process.env[apiKeyEnv]?.trim();
  if (!key) {
    throw new BackendCredentialError(`${apiKeyEnv} is not set`);
  }
  return key;
}

/** Resolve the model for an AI-SDK backend config. Server-only. */
export function resolveAiSdkModel(backend: AiSdkBackendConfig): LanguageModel {
  switch (backend.type) {
    case "openai-completions": {
      // The *compatible* provider, not `@ai-sdk/openai` (#4544). The OpenAI
      // product client parses only OpenAI-native reasoning fields, so a vendor
      // that emits the widely-used `reasoning_content` (xAI, DeepSeek, Groq,
      // Mistral, OpenRouter, GLM, a LiteLLM proxy) would stream text and tool
      // calls while silently dropping its thinking — even though this adapter
      // declares `reasoning: true`. `@ai-sdk/openai-compatible` reads
      // `reasoning_content` / `reasoning` and emits them as reasoning parts.
      const apiKey = readBackendApiKey(backend.apiKeyEnv);
      const provider = createOpenAICompatible({
        name: backend.type,
        baseURL: backend.baseUrl,
        apiKey,
        // `@ai-sdk/openai-compatible` only asks for the trailing usage chunk
        // when this is set, whereas `@ai-sdk/openai`'s chat path always did.
        // Without it the request shape changes for every compatible vendor.
        includeUsage: true,
      });
      return provider.chatModel(backend.model);
    }
    case "openai-responses": {
      // The Responses wire format is OpenAI-native (reasoning summaries,
      // encrypted reasoning, `*_call` output items), so this arm keeps the
      // OpenAI provider — it is the only one that exposes `.responses()`.
      const apiKey = readBackendApiKey(backend.apiKeyEnv);
      const provider = createOpenAI({
        baseURL: backend.baseUrl,
        apiKey,
        name: backend.type,
      });
      return provider.responses(backend.model);
    }
    case "anthropic": {
      const apiKey = readBackendApiKey(backend.apiKeyEnv);
      return createAnthropic({ apiKey, name: backend.type })(backend.model);
    }
    case "google-vertex":
      // Vertex reads Application Default Credentials from the ambient
      // environment; nothing secret comes from the config.
      return createVertex({
        project: backend.project,
        location: backend.location,
      })(backend.model);
  }
}

/**
 * The provider's own built-in web-search / grounding tool, when it has one
 * (#4552).
 *
 * These are provider-executed services — the provider runs the search upstream
 * inside the same request and returns citations — so they carry the provider's
 * separate search pricing, not a local tool call. The citations come back as
 * `source-url` / `source-document` parts, which the shared mapper forwards once
 * `sendSources` is on.
 *
 * Returning `undefined` means the backend has no built-in search:
 * `openai-completions` is that case, because Chat Completions has no
 * server-side search — vendors on that wire format bring their own (Perplexity's
 * native web search, OpenRouter's `:online`).
 */
export function resolveAiSdkSearchTools(
  backend: AiSdkBackendConfig,
): ToolSet | undefined {
  switch (backend.type) {
    case "openai-completions":
      return undefined;
    case "openai-responses": {
      const apiKey = readBackendApiKey(backend.apiKeyEnv);
      const provider = createOpenAI({
        baseURL: backend.baseUrl,
        apiKey,
        name: backend.type,
      });
      return { web_search: provider.tools.webSearch() };
    }
    case "anthropic": {
      const apiKey = readBackendApiKey(backend.apiKeyEnv);
      const provider = createAnthropic({ apiKey, name: backend.type });
      // Newer dated versions exist (`webSearch_20260209`, `webSearch_20260318`);
      // the provider adds the required beta header itself either way.
      return { web_search: provider.tools.webSearch_20250305() };
    }
    case "google-vertex": {
      const provider = createVertex({
        project: backend.project,
        location: backend.location,
      });
      // Google Search grounding for Gemini on Vertex.
      return { google_search: provider.tools.googleSearch({}) };
    }
  }
}
