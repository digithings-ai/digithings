/**
 * Dispatcher for the non-AI-SDK protocol adapters (#4543).
 *
 * The route hands over the already-built core messages and the resolved
 * adapter; this module picks the mapper and resolves the optional credential
 * once, so the three mappers stay free of env access and the
 * `backend_unavailable` 502 policy lives in a single place (mirroring
 * `createAiSdkStreamResponse`).
 */
import type { UIMessage } from "ai";
import type { ActivityDetail } from "@/lib/chat-activity";
import type { NonAiSdkBackendConfig } from "@/lib/backend-adapters";
import { readBackendApiKey } from "@/lib/adapters/ai-sdk/providers";
import { createLangGraphStreamResponse } from "@/lib/adapters/langgraph/stream";
import { createAgUiStreamResponse } from "@/lib/adapters/ag-ui/stream";
import { createA2aStreamResponse } from "@/lib/adapters/a2a/stream";

export async function createNonAiSdkStreamResponse(opts: {
  backend: NonAiSdkBackendConfig;
  messages: UIMessage[];
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  signal?: AbortSignal;
}): Promise<Response> {
  let apiKey: string | null = null;
  if (opts.backend.apiKeyEnv) {
    try {
      apiKey = readBackendApiKey(opts.backend.apiKeyEnv);
    } catch (err) {
      // Operator misconfiguration, not a client error: answer 502 with the env
      // var NAME (never its value) and make no upstream call.
      const message = err instanceof Error ? err.message : "backend_credential_error";
      return new Response(JSON.stringify({ error: "backend_unavailable", message }), {
        status: 502,
        headers: { "content-type": "application/json", ...opts.responseHeaders },
      });
    }
  }

  switch (opts.backend.type) {
    case "langgraph":
      return createLangGraphStreamResponse({ ...opts, backend: opts.backend, apiKey });
    case "ag-ui":
      return createAgUiStreamResponse({ ...opts, backend: opts.backend, apiKey });
    case "a2a":
      return createA2aStreamResponse({ ...opts, backend: opts.backend, apiKey });
  }
}
