/**
 * Backend adapter registry (Phase 5a, #4522).
 *
 * Every chat backend the BFF can stream from is described here once: which
 * wire protocol it speaks, where its credentials come from, and what it can
 * surface in the chat. The route handler reads this descriptor instead of
 * branching on `backend.type` directly, so adding a backend type is a registry
 * entry plus its mapper rather than a new `if` in the handler.
 *
 * Phase 5a is a faithful extraction of the two existing backends — `digigraph`
 * and `foundry` behave exactly as before, and no new dependency is introduced.
 * Phase 5b adds the AI SDK backends (`openai-completions`, `openai-responses`,
 * `anthropic`, `google-vertex`); 5c adds the non-AI-SDK protocols (each a new
 * dependency and therefore human-gated).
 *
 * The UI never changes per backend: both adapters normalize onto the same
 * `ActivitySpan` vocabulary in `lib/chat-activity.ts` and emit the same AI SDK
 * UI-message stream, so reasoning, tool calls, sources and activity render the
 * same way regardless of which backend produced them.
 *
 * In 5a only `protocol` and `capabilities.corpus` are load-bearing in the
 * handler; the remaining capabilities are declared here for 5b/5c and asserted
 * by the parity test, not yet read at runtime.
 */

import type { DigichatDeployment } from "@/lib/deploy-config/schema";

export type BackendConfig = DigichatDeployment["backend"];
export type BackendType = BackendConfig["type"];
export type DigigraphBackendConfig = Extract<BackendConfig, { type: "digigraph" }>;
export type FoundryBackendConfig = Extract<BackendConfig, { type: "foundry" }>;
export type OpenAiCompletionsBackendConfig = Extract<
  BackendConfig,
  { type: "openai-completions" }
>;
export type OpenAiResponsesBackendConfig = Extract<
  BackendConfig,
  { type: "openai-responses" }
>;
export type AnthropicBackendConfig = Extract<BackendConfig, { type: "anthropic" }>;
export type GoogleVertexBackendConfig = Extract<
  BackendConfig,
  { type: "google-vertex" }
>;
/** The AI-SDK family: one `streamText` mapper serves all of them (#4535, #4539). */
export type AiSdkBackendConfig =
  | OpenAiCompletionsBackendConfig
  | OpenAiResponsesBackendConfig
  | AnthropicBackendConfig
  | GoogleVertexBackendConfig;

/**
 * The upstream wire protocol an adapter speaks. This is the adapter selector:
 * the route decides which streaming path to take from `adapter.protocol`, never
 * from the backend type itself.
 */
export type BackendProtocol =
  | "digigraph-trace"
  | "foundry-responses"
  | "openai-completions"
  | "openai-responses"
  | "anthropic-messages"
  | "gemini"
  | "langgraph"
  | "ag-ui"
  | "a2a";

/** Where the adapter's upstream credential comes from — always server-side. */
export type BackendAuth =
  | "managed-identity"
  | "env"
  | "upstream-bearer"
  | "byok";

/**
 * What the adapter can surface in the chat. Drives the UI and the parity
 * contract: a backend that cannot produce reasoning must not pretend it can.
 * The per-backend canned-stream normalization fixture lands in 5d; for now the
 * parity test asserts the boolean flags themselves.
 */
export type BackendCapabilities = {
  /** Chain-of-thought / reasoning content. */
  reasoning: boolean;
  /** Reasoning is only present when a summary is enabled upstream. */
  reasoningSummary?: boolean;
  /** Tool calls (args + results). */
  toolCalls: boolean;
  /** Upstream web search. */
  webSearch: boolean;
  /** Citation / source documents. */
  sources: boolean;
  /** Send / regenerate / edit-last-user turn mutation. */
  turnMutation: boolean;
  /** Multi-turn continuity via an external conversation id. */
  conversationContinuity: boolean;
  /** File and image attachments. */
  attachments: boolean;
  /** Operator MCP servers forwarded upstream. */
  mcp: boolean;
  /** Corpus scope headers (`digisearchIndex` / `vaultPathPrefix`). */
  corpus: boolean;
};

export type BackendAdapter = {
  type: BackendType;
  protocol: BackendProtocol;
  auth: BackendAuth;
  capabilities: BackendCapabilities;
};

/**
 * One entry per supported `backend.type`. Adding a type here without a matching
 * stream implementation is a compile error at the lookup site only if the union
 * grows — keep this object exhaustive over `BackendType`.
 */
export const BACKEND_ADAPTERS: Record<BackendType, BackendAdapter> = {
  digigraph: {
    type: "digigraph",
    protocol: "digigraph-trace",
    auth: "upstream-bearer",
    capabilities: {
      reasoning: true,
      toolCalls: true,
      webSearch: true,
      sources: true,
      turnMutation: true,
      // digigraph keys continuity off `X-Session-Id`; there is no external
      // conversation id to round-trip.
      conversationContinuity: false,
      attachments: true,
      mcp: true,
      corpus: true,
    },
  },
  foundry: {
    type: "foundry",
    protocol: "foundry-responses",
    auth: "managed-identity",
    capabilities: {
      reasoning: true,
      // Responses items carry reasoning only when a summary is enabled on the
      // agent; the adapter drops the empty case rather than rendering a bare
      // "Thinking" row.
      reasoningSummary: false,
      toolCalls: true,
      // The DataTap agent is wired to azure_ai_search, not web search.
      webSearch: false,
      sources: true,
      turnMutation: true,
      conversationContinuity: true,
      attachments: true,
      // Operator MCP servers are not forwarded on the foundry path today.
      mcp: false,
      corpus: false,
    },
  },
  // The AI-SDK family (#4535): one `streamText` → `toUIMessageStream` mapper
  // serves both OpenAI wire formats. The credential comes from the env var the
  // config names, so `auth: "env"`.
  "openai-completions": {
    type: "openai-completions",
    protocol: "openai-completions",
    auth: "env",
    capabilities: {
      reasoning: true,
      toolCalls: true,
      // Provider-side tools (web search, file search) surface as tool calls and
      // source parts on the same UI-message stream.
      webSearch: true,
      sources: true,
      // Regenerate / edit-last-user are not wired yet: `createAiSdkStreamResponse`
      // accepts no `turnMode` and the client gate only enables the chrome for
      // digigraph/foundry. Declared false until the mapper threads it (#4535).
      turnMutation: false,
      // No external conversation id is round-tripped on these backends.
      conversationContinuity: false,
      attachments: true,
      mcp: false,
      corpus: false,
    },
  },
  "openai-responses": {
    type: "openai-responses",
    protocol: "openai-responses",
    auth: "env",
    capabilities: {
      reasoning: true,
      toolCalls: true,
      webSearch: true,
      sources: true,
      // See the openai-completions entry: turn mutation is not wired yet.
      turnMutation: false,
      conversationContinuity: false,
      attachments: true,
      mcp: false,
      corpus: false,
    },
  },
  // The AI-SDK family, continued (#4539). Same shared mapper; the credential
  // source differs: Anthropic names an env var, Vertex uses ambient ADC.
  anthropic: {
    type: "anthropic",
    protocol: "anthropic-messages",
    auth: "env",
    capabilities: {
      reasoning: true,
      toolCalls: true,
      webSearch: true,
      sources: true,
      turnMutation: false,
      conversationContinuity: false,
      attachments: true,
      mcp: false,
      corpus: false,
    },
  },
  "google-vertex": {
    type: "google-vertex",
    protocol: "gemini",
    auth: "managed-identity",
    capabilities: {
      reasoning: true,
      toolCalls: true,
      webSearch: true,
      sources: true,
      turnMutation: false,
      conversationContinuity: false,
      attachments: true,
      mcp: false,
      corpus: false,
    },
  },
};

/** The default backend when a deployment declares none. */
export const DEFAULT_BACKEND_TYPE: BackendType = "digigraph";

/** Resolve the adapter for a backend type, defaulting to digigraph. */
export function backendAdapterFor(type: BackendType | undefined): BackendAdapter {
  return BACKEND_ADAPTERS[type ?? DEFAULT_BACKEND_TYPE];
}

/**
 * Narrow a config to the digigraph shape (for reading its own fields).
 *
 * Checks `type` only; the rest of the shape is guaranteed by the Zod schema
 * (`BackendSchema`) and the tenant validator, both of which run before the
 * handler ever sees a config.
 */
export function isDigigraphConfig(
  config: BackendConfig | undefined,
): config is DigigraphBackendConfig {
  return config?.type === "digigraph";
}

/**
 * Narrow a config to the foundry shape (for reading its own fields).
 *
 * Checks `type` only; `projectEndpoint` / `agentName` are guaranteed by the
 * Zod schema and the tenant validator, which reject a foundry backend missing
 * either field.
 */
export function isFoundryConfig(
  config: BackendConfig | undefined,
): config is FoundryBackendConfig {
  return config?.type === "foundry";
}

/**
 * The AI-SDK protocols. The handler tests `AI_SDK_PROTOCOLS.has(protocol)`
 * rather than naming backend types, which keeps the "no `backend.type`
 * comparison in the handler" invariant the source guard pins.
 */
export const AI_SDK_PROTOCOLS: ReadonlySet<BackendProtocol> = new Set<BackendProtocol>([
  "openai-completions",
  "openai-responses",
  "anthropic-messages",
  "gemini",
]);

/**
 * Narrow a config to the AI-SDK family (for reading `model` / `baseUrl` /
 * `apiKeyEnv` / `project`). Checks `type` only; the rest of the shape is
 * guaranteed by the Zod schema (`BackendSchema`) and the tenant validator, both
 * of which run before the handler ever sees a config.
 */
export function isAiSdkConfig(
  config: BackendConfig | undefined,
): config is AiSdkBackendConfig {
  return (
    config?.type === "openai-completions" ||
    config?.type === "openai-responses" ||
    config?.type === "anthropic" ||
    config?.type === "google-vertex"
  );
}
