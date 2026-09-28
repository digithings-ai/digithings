/**
 * Shared AI-SDK stream mapper (Phase 5b, #4535).
 *
 * Every AI-SDK backend (OpenAI Completions, OpenAI Responses, and the Anthropic
 * / Google Vertex providers that follow) runs through this one function, so
 * provider-native reasoning, tool calls, sources and data all land on the same
 * AI SDK UI-message stream the chat UI already renders. That is the parity
 * invariant the backend matrix is built on: the UI never learns which backend
 * produced a part.
 */

import {
  createUIMessageStreamResponse,
  smoothStream,
  streamText,
  toUIMessageStream,
  type LanguageModel,
  type ModelMessage,
  type ToolSet,
} from "ai";
import type { AiSdkBackendConfig } from "@/lib/backend-adapters";
import { resolveAiSdkModel, resolveAiSdkSearchTools } from "./providers";

export async function createAiSdkStreamResponse({
  backend,
  messages,
  responseHeaders,
  webSearch = false,
  signal,
}: {
  backend: AiSdkBackendConfig;
  messages: ModelMessage[];
  responseHeaders: Record<string, string>;
  /**
   * The client asked for web search AND the tenant allows it. Passes the
   * provider's built-in search/grounding tool so its citations flow.
   */
  webSearch?: boolean;
  signal: AbortSignal;
}): Promise<Response> {
  let model: LanguageModel;
  let tools: ToolSet | undefined;
  try {
    model = resolveAiSdkModel(backend);
    tools = webSearch ? resolveAiSdkSearchTools(backend) : undefined;
  } catch (err) {
    // A missing credential is an operator misconfiguration, not a client error:
    // answer 502 with the env var NAME (never its value) and no upstream call.
    const message = err instanceof Error ? err.message : "backend_credential_error";
    return new Response(JSON.stringify({ error: "backend_unavailable", message }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }

  // NOTE (#4539): only the env-key backends (openai-*, anthropic) can fail
  // here with a clean 502 — `readBackendApiKey` throws before any upstream
  // call. `google-vertex` has no env var to pre-check: it resolves Application
  // Default Credentials lazily, so an absent ADC surfaces as an upstream error
  // from `streamText` rather than through this path.
  const result = streamText({
    model,
    messages,
    ...(tools ? { tools } : {}),
    abortSignal: signal,
    experimental_transform: smoothStream({ chunking: "word" }),
  });

  return createUIMessageStreamResponse({
    stream: toUIMessageStream({
      stream: result.stream,
      // Provider citations (web search, grounding, RAG) travel as `source-url` /
      // `source-document` parts and `sendSources` is OFF by default in v7, so
      // without this a grounded answer arrives with its citations stripped
      // (#4552). `sendReasoning` already defaults true; pinned for intent.
      sendSources: true,
      sendReasoning: true,
    }),
    headers: responseHeaders,
  });
}
