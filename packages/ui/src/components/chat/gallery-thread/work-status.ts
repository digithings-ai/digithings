/**
 * The live one-line status of a work chain.
 *
 * The same chain is described in two places: the collapsed header (which
 * reads as a status line — "Working — digisearch", "Used 3 tools") and the
 * retired summary row. Both must say exactly the same thing, so the sentence
 * is computed once here, from the message parts and the chain's own indices.
 */

/**
 * The part fields the status needs. Kept structural so the function stays a
 * pure module: no React, no runtime import, and callable from a test with
 * plain objects.
 */
type WorkStatusPart = {
  readonly type: string;
  readonly toolName?: string | undefined;
  readonly status?: { readonly type?: string | undefined } | undefined;
};

import { EN_TRACE_T, type TraceT } from "../trace-i18n/core";

export type { WorkStatusPart };

export type WorkStatus = {
  /**
   * The status sentence: what is running now, or what the chain did once it
   * is done.
   */
  label: string;
  /** A tool call or the reasoning is still streaming. */
  running: boolean;
};

/**
 * Describe a chain of reasoning and tool calls.
 *
 * While something runs the line names it; once the chain is done it counts
 * the tools it ran. A chain that only reasoned says so — there is no tool to
 * count, so "Thought" is the honest answer.
 */
export function workStatusText(
  parts: readonly WorkStatusPart[],
  indices: readonly number[],
  tr: TraceT = EN_TRACE_T,
): WorkStatus {
  const chain = indices
    .map((index) => parts[index])
    .filter((part): part is WorkStatusPart => part !== undefined);

  const tools = chain.filter((part) => part.type === "tool-call");
  const running = tools.find((part) => part.status?.type === "running");
  const thinking = chain.some(
    (part) => part.type === "reasoning" && part.status?.type === "running",
  );

  const label = running
    ? tr.t("workingOn", { tool: running.toolName ?? tr.t("toolFallbackName") })
    : thinking
      ? tr.t("thinking")
      : tools.length > 0
        ? tr.plural("usedTools", tools.length)
        : tr.t("thought");

  return { label, running: running !== undefined || thinking };
}
