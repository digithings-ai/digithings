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
 * Phase 5b/5c add the AI SDK and non-AI-SDK backends (each a new dependency and
 * therefore human-gated).
 *
 * The UI never changes per backend: both adapters normalize onto the same
 * `ActivitySpan` vocabulary in `lib/chat-activity.ts` and emit the same AI SDK
 * UI-message stream, so reasoning, tool calls, sources and activity render the
 * same way regardless of which backend produced them.
 */

import type { DigichatDeployment } from "@/lib/deploy-config/schema";

export type BackendConfig = DigichatDeployment["backend"];
export type BackendType = BackendConfig["type"];
export type DigigraphBackendConfig = Extract<BackendConfig, { type: "digigraph" }>;
export type FoundryBackendConfig = Extract<BackendConfig, { type: "foundry" }>;

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
 * What the adapter can surface in the chat. Drives the UI and the parity test:
 * a backend that cannot produce reasoning must not pretend it can, and a test
 * asserts each adapter's canned stream normalizes to the declared parts.
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
};

/** The default backend when a deployment declares none. */
export const DEFAULT_BACKEND_TYPE: BackendType = "digigraph";

/** Resolve the adapter for a backend type, defaulting to digigraph. */
export function backendAdapterFor(type: BackendType | undefined): BackendAdapter {
  return BACKEND_ADAPTERS[type ?? DEFAULT_BACKEND_TYPE];
}

/** Narrow a config to the digigraph shape (for reading its own fields). */
export function isDigigraphConfig(
  config: BackendConfig | undefined,
): config is DigigraphBackendConfig {
  return config?.type === "digigraph";
}

/** Narrow a config to the foundry shape (for reading its own fields). */
export function isFoundryConfig(
  config: BackendConfig | undefined,
): config is FoundryBackendConfig {
  return config?.type === "foundry";
}
