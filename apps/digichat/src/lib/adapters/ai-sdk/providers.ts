/**
 * AI-SDK provider factory (Phase 5b, #4535).
 *
 * One place that turns a `backend` config into a `LanguageModel` for the AI-SDK
 * family, so the route never names a provider package. Adding `anthropic` or
 * `google-vertex` is one more branch here plus its `@ai-sdk/*` dependency.
 *
 * The credential is read from the env var the config NAMES (`apiKeyEnv`), never
 * from the config body — that is what keeps it off the client and out of the
 * repository. The `DIGICHAT_BACKEND_` prefix on that name is enforced by the
 * schema, so a config can never point at `AUTH_SECRET` and have the BFF ship it
 * to an attacker-controlled `baseUrl`.
 */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
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
  const apiKey = readBackendApiKey(backend.apiKeyEnv);
  const provider = createOpenAI({
    baseURL: backend.baseUrl,
    apiKey,
    name: backend.type,
  });
  // `openai-responses` speaks the Responses wire format; `openai-completions`
  // the Chat Completions one. Both are the installed `@ai-sdk/openai` provider.
  return backend.type === "openai-responses"
    ? provider.responses(backend.model)
    : provider.chat(backend.model);
}
