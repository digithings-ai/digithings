/**
 * What each digichat backend can actually enforce.
 *
 * A rule the backend cannot enforce is `unsupported`. Config validation
 * rejects it, or warns and drops it when `limits.onUnsupported` is `warn`.
 * `best-effort` is allowed: the BFF applies the gate it can see, and the doc
 * says where the upstream agent can still run past it.
 */

export const LIMIT_KINDS = [
  "tokens",
  "cost",
  "turns",
  "sessions",
  "toolCalls",
  "models",
] as const;

export type LimitKind = (typeof LIMIT_KINDS)[number];

export type Support = "enforce" | "best-effort" | "unsupported";

export type BackendClass = "house" | "ai-sdk" | "foundry" | "ag-ui" | "a2a";

const HOUSE = new Set(["digigraph", "langgraph"]);
const AI_SDK = new Set([
  "openai-completions",
  "openai-responses",
  "anthropic",
  "google-vertex",
]);

export function backendClass(backendType: string): BackendClass | "unknown" {
  if (HOUSE.has(backendType)) return "house";
  if (AI_SDK.has(backendType)) return "ai-sdk";
  if (backendType === "foundry") return "foundry";
  if (backendType === "ag-ui") return "ag-ui";
  if (backendType === "a2a") return "a2a";
  return "unknown";
}

export type LimitShape = {
  kind: LimitKind;
  metric?: "input" | "output" | "total";
  scope?: "deployment" | "subscription" | "user" | "ip" | "session";
  window?: "minute" | "hour" | "day" | "session" | "turn" | "concurrent";
};

/**
 * Kind-level summary for the doc table. `partial` means only some shapes of
 * that kind are enforceable; `limitSupport` is the check the schema runs.
 */
export type MatrixCell = Support | "partial";

export const SUPPORT_MATRIX: Record<string, Record<LimitKind, MatrixCell>> = {
  digigraph: {
    tokens: "enforce",
    cost: "enforce",
    turns: "enforce",
    sessions: "enforce",
    // Enforced, not best-effort: digichat forwards the cap as
    // X-Digi-Max-Tool-Calls and digigraph → digillm counts executed calls and
    // wraps up tool-free at the cap. Silently — no notice in the UI.
    toolCalls: "enforce",
    models: "enforce",
  },
  langgraph: {
    tokens: "best-effort",
    cost: "best-effort",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "best-effort",
    models: "enforce",
  },
  "openai-completions": {
    tokens: "enforce",
    cost: "enforce",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "enforce",
    models: "enforce",
  },
  "openai-responses": {
    tokens: "enforce",
    cost: "enforce",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "enforce",
    models: "enforce",
  },
  anthropic: {
    tokens: "enforce",
    cost: "enforce",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "enforce",
    models: "enforce",
  },
  "google-vertex": {
    tokens: "enforce",
    cost: "enforce",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "enforce",
    models: "enforce",
  },
  foundry: {
    tokens: "partial",
    cost: "unsupported",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "enforce",
    models: "unsupported",
  },
  "ag-ui": {
    tokens: "unsupported",
    cost: "unsupported",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "best-effort",
    models: "unsupported",
  },
  a2a: {
    tokens: "unsupported",
    cost: "unsupported",
    turns: "enforce",
    sessions: "enforce",
    toolCalls: "unsupported",
    models: "unsupported",
  },
};

function foundryTokens(rule: LimitShape): Support {
  const deploymentScope = rule.scope === "deployment" || rule.scope === "subscription";
  if (rule.metric === "total" && rule.window === "minute" && deploymentScope) return "enforce";
  return "unsupported";
}

/** Per-rule support. This is what schema validation consults. */
export function limitSupport(backendType: string, rule: LimitShape): Support {
  const kind = rule.kind;
  if (backendType === "foundry" && kind === "tokens") return foundryTokens(rule);
  if (backendType === "foundry" && kind === "toolCalls") {
    return rule.window === "turn" ? "enforce" : "unsupported";
  }
  const row = SUPPORT_MATRIX[backendType];
  if (!row) return "unsupported";
  const cell = row[kind];
  if (cell === "partial") return "unsupported";
  return cell;
}
