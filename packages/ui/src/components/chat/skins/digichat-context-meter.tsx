"use client";

import { useAuiState } from "@assistant-ui/react";

/**
 * Context used, as the segmented digichat cube bar. The bar is the same
 * one that used to sit inside the breakdown card: its lit span is the
 * fraction of the model's window the last turn sent, coloured by
 * system/tools/user. Hovering (or focusing) the bar opens the legend.
 *
 * The provider reports only the prompt total (inputTokens). The system /
 * tools / user split is therefore an estimate: user text is counted from the
 * thread, tool schemas get a flat per-tool allowance, and the remainder is
 * the system prompt. Values carry a `~` so the card never implies precision
 * the backend does not send.
 */
const BAR_CELLS = 25;

const CONTEXT_WINDOWS: Record<string, number> = {
  "deepseek/deepseek-v4.1-flash": 1_048_576,
  "z-ai/glm-5.3-flash": 1_048_576,
  "qwen/qwen3.8-flash": 1_000_000,
  "google/gemma-4-31b-it": 262_144,
  "xiaomi/mimo-v2.6-flash": 1_050_000,
  "z-ai/glm-4.7-flash": 200_000,
  // The OpenAI models an Azure AI Foundry agent is usually deployed on. The
  // window is the published one; a deployment whose id is not listed here
  // gets no bar at all (see the unknown-window rule below).
  "gpt-4o": 128_000,
  "gpt-4o-mini": 128_000,
  "gpt-4.1": 1_047_576,
  "gpt-4.1-mini": 1_047_576,
  "gpt-4.1-nano": 1_047_576,
  "o3": 200_000,
  "o3-mini": 200_000,
  "o4-mini": 200_000,
};
/** Rough tokens per tool schema (name, description, JSON schema). */
const TOKENS_PER_TOOL = 220;

const format = (n: number): string =>
  n >= 1_000_000
    ? `${(n / 1_000_000).toFixed(1)}m`
    : n >= 1000
      ? `${(n / 1000).toFixed(1)}k`
      : String(n);

const textOf = (message: unknown): string => {
  const parts = (message as { content?: unknown; parts?: unknown })?.parts;
  if (Array.isArray(parts)) {
    return parts
      .filter(
        (part): part is { type: string; text: string } =>
          typeof part === "object" &&
          part !== null &&
          (part as { type?: unknown }).type === "text" &&
          typeof (part as { text?: unknown }).text === "string",
      )
      .map((part) => part.text)
      .join("");
  }
  const content = (message as { content?: unknown })?.content;
  return typeof content === "string" ? content : "";
};

export function DigichatContextMeter({
  model,
  toolCount = 0,
}: {
  model: string;
  /** Connected MCP + catalog tool count, used for the schema estimate. */
  toolCount?: number;
}) {
  // Select primitives, never a fresh object: useAuiState compares with
  // Object.is, and a new `{input, userChars}` every render loops forever.
  const reportedInput = useAuiState((s) => {
    const messages = s.thread.messages;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const custom = (
        messages[index]?.metadata as {
          custom?: { usage?: { inputTokens?: unknown } };
        }
      )?.custom;
      if (typeof custom?.usage?.inputTokens === "number") {
        return custom.usage.inputTokens;
      }
    }
    return undefined;
  });
  // The model the backend says it served the turn with. A tenant whose
  // session model is empty (a Foundry agent) is named here instead.
  const reportedModel = useAuiState((s) => {
    const messages = s.thread.messages;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const custom = (
        messages[index]?.metadata as {
          custom?: { usage?: { inputTokens?: unknown }; model?: unknown };
        }
      )?.custom;
      if (
        typeof custom?.usage?.inputTokens === "number" &&
        typeof custom.model === "string"
      ) {
        return custom.model;
      }
    }
    return undefined;
  });
  const userChars = useAuiState((s) => {
    let total = 0;
    for (const message of s.thread.messages) {
      if ((message as { role?: string }).role === "user") {
        total += textOf(message).length;
      }
    }
    return total;
  });

  // The window must be known: a bar drawn against a guessed window is a lie
  // about how full the context is, so an unknown model gets no bar at all.
  const window =
    CONTEXT_WINDOWS[model] ??
    (reportedModel ? CONTEXT_WINDOWS[reportedModel] : undefined);
  // No bar without a known window: the fill is a fraction of it.
  if (window === undefined) return null;

  // No fabricated fill: until a turn reports usage the grid stays empty.
  const input = reportedInput ?? 0;
  const ratio = Math.min(1, input / window);
  const userTokens = input > 0 ? Math.round(userChars / 4) : 0;
  const toolTokens = input > 0 ? toolCount * TOKENS_PER_TOOL : 0;
  const systemTokens = Math.max(0, input - userTokens - toolTokens);
  const label = `${format(input)} / ${format(window)} tokens`;

  // The used span grows with the window ratio; inside it the three types
  // take their share of the prompt.
  const usedCells = input > 0 ? Math.max(1, Math.round(ratio * BAR_CELLS)) : 0;
  const sysPct = input > 0 ? Math.round((systemTokens / input) * 100) : 0;
  const toolPct = input > 0 ? Math.round((toolTokens / input) * 100) : 0;
  const userPct = input > 0 ? Math.max(0, 100 - sysPct - toolPct) : 0;
  const sysCells = Math.min(
    usedCells,
    input > 0 ? Math.round((usedCells * systemTokens) / input) : 0,
  );
  const toolCells = Math.min(
    usedCells - sysCells,
    input > 0 ? Math.round((usedCells * toolTokens) / input) : 0,
  );
  const userCells = Math.max(0, usedCells - sysCells - toolCells);

  return (
    <span className="aui-context-meter-wrap">
      <span
        className="aui-context-meter"
        role="img"
        tabIndex={0}
        aria-label={`Context ${label}`}
      >
        {Array.from({ length: BAR_CELLS }, (_, index) => {
          const tone =
            index < sysCells
              ? "is-system"
              : index < sysCells + toolCells
                ? "is-tools"
                : index < sysCells + toolCells + userCells
                  ? "is-user"
                  : "";
          return (
            <span
              key={index}
              className={tone ? `aui-context-bar-cell ${tone}` : "aui-context-bar-cell"}
            />
          );
        })}
      </span>
      <span className="aui-context-card" role="tooltip">
        <span className="aui-context-card-row aui-context-card-total">
          <span>Context</span>
          <span>
            {format(input)} / {format(window)}
          </span>
        </span>
        <span className="aui-context-card-row">
          <span className="aui-context-legend">
            <span className="aui-context-swatch is-system" aria-hidden />
            System
          </span>
          <span>
            ~{format(systemTokens)} · {sysPct}%
          </span>
        </span>
        <span className="aui-context-card-row">
          <span className="aui-context-legend">
            <span className="aui-context-swatch is-tools" aria-hidden />
            Tools
          </span>
          <span>
            ~{format(toolTokens)} · {toolPct}%
          </span>
        </span>
        <span className="aui-context-card-row">
          <span className="aui-context-legend">
            <span className="aui-context-swatch is-user" aria-hidden />
            User
          </span>
          <span>
            ~{format(userTokens)} · {userPct}%
          </span>
        </span>
      </span>
    </span>
  );
}
