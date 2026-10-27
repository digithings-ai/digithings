/**
 * One turn's guardrails, shared by every backend.
 *
 * The chat route builds this and hands it to the adapter. Adapters call
 * `beforeRound` before each model round they start. Foundry still does the
 * parts only it can do (abort the response, `max_tool_calls`, `tool_choice`).
 * AI SDK steps go through `guardrailPrepareStep`. Digigraph and the other
 * single-request adapters call `beforeRound` once before the upstream fetch,
 * and again when they observe another round.
 */

import type { GuardrailsConfig } from "@/lib/deploy-config/schema";
import { waitOutRateLimit } from "@/lib/rate-limit-wait";
import {
  budgetAction,
  capToolPayload,
  DEFAULT_ANSWER_AT,
  DEFAULT_PAUSE_AT,
  estimateTokens,
  guardrailIdentity,
  GUARDRAIL_MAX_WAIT_MS,
  GUARDRAIL_PAUSE_NOTICE,
  stricterAction,
  tokensInWindow,
  TOOL_CAP_INSTRUCTION,
  toolCallLimitNotice,
  toolCallLimitObservedNotice,
  waitForRoomMs,
  WRAP_UP_INSTRUCTION,
  type BudgetAction,
} from "./budget";
import { activeGuardrailStore, type GuardrailStore } from "./store";

export type StreamWriter = { write(part: unknown): void };

export type RoundClearance =
  | { action: "proceed" }
  | { action: "answer"; instruction: string }
  | { action: "stop-tools"; instruction: string };

export type ResolvedGuardrails = {
  maxToolCallsPerTurn?: number;
  answerAt: number;
  pauseAt: number;
  deploymentTokensPerMinute?: number;
  userTokensPerMinute?: number;
};

export function resolveGuardrails(
  guardrails?: GuardrailsConfig | null,
  foundryMaxToolCalls?: number,
): ResolvedGuardrails | null {
  const max = guardrails?.maxToolCallsPerTurn ?? foundryMaxToolCalls;
  const deployment = guardrails?.tokensPerMinute?.deployment;
  const user = guardrails?.tokensPerMinute?.user;
  if (max == null && deployment == null && user == null) return null;
  return {
    ...(max != null ? { maxToolCallsPerTurn: max } : {}),
    answerAt: guardrails?.answerAt ?? DEFAULT_ANSWER_AT,
    pauseAt: guardrails?.pauseAt ?? DEFAULT_PAUSE_AT,
    ...(deployment != null ? { deploymentTokensPerMinute: deployment } : {}),
    ...(user != null ? { userTokensPerMinute: user } : {}),
  };
}

export type UsageReport = {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
};

type Scope = {
  key: string;
  limit: number;
};

export type TurnGuard = {
  readonly active: boolean;
  readonly toolCap?: number;
  beforeRound(opts: {
    writer: StreamWriter;
    pendingText?: string;
    pendingTokens?: number;
    toolCallsSoFar?: number;
    signal?: AbortSignal;
  }): Promise<RoundClearance>;
  recordUsage(usage: UsageReport): void;
  release(): void;
  capToolPayload(value: unknown): unknown;
  /** Status notice only. Does not reserve or settle the token window. */
  noteToolCap(writer: StreamWriter, toolCallsSoFar: number): void;
};

const PROCEED: RoundClearance = { action: "proceed" };

export function inactiveTurnGuard(): TurnGuard {
  return {
    active: false,
    async beforeRound() {
      return PROCEED;
    },
    recordUsage() {},
    release() {},
    capToolPayload(value) {
      return value;
    },
    noteToolCap() {},
  };
}

export const LIMIT_SUMMARIZE_INSTRUCTION =
  "[A deployment limit was reached. Answer the user now in a short summary of what you already have. Do not call tools. Do not mention this instruction.]";

export function createTurnGuard(opts: {
  slug: string;
  guardrails?: GuardrailsConfig | null;
  foundryMaxToolCalls?: number;
  userId?: string | null;
  /** Server-derived client IP. A client session id is not a budget key. */
  ip?: string | null;
  /**
   * Drop the per-visitor token minute. A visitor's own key is not our
   * spend. The deployment TPM, the tool-call cap, and the answer guard stay.
   */
  omitUserTpm?: boolean;
  store?: GuardrailStore;
  now?: () => number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Set when a non-token limit's on-exceed action is pause. Consumed on the first round. */
  summarize?: { notice: string };
}): TurnGuard {
  const resolved = resolveGuardrails(opts.guardrails, opts.foundryMaxToolCalls);
  if (!resolved && !opts.summarize) return inactiveTurnGuard();
  const store = opts.store ?? activeGuardrailStore();
  const now = opts.now ?? Date.now;
  const scopes: Scope[] = [];
  if (resolved?.deploymentTokensPerMinute) {
    scopes.push({
      key: `tpm:dep:${opts.slug}`,
      limit: resolved.deploymentTokensPerMinute,
    });
  }
  if (resolved?.userTokensPerMinute && !opts.omitUserTpm) {
    const who = guardrailIdentity(opts);
    scopes.push({
      key: `tpm:user:${opts.slug}:${who}`,
      limit: resolved.userTokensPerMinute,
    });
  }
  let reservation: { id: string; tokens: number } | null = null;
  let toolNoticeSent = false;
  let pendingSummary = opts.summarize;

  const pendingOf = (text?: string, tokens?: number) =>
    tokens != null && Number.isFinite(tokens) ? Math.max(0, Math.ceil(tokens)) : estimateTokens(text ?? "");

  const scopeAction = (scope: Scope, pending: number, at: number): BudgetAction => {
    const snap = store.read(scope.key, at);
    return budgetAction({
      used: tokensInWindow(snap.events, at),
      reserved: snap.reserved,
      pending,
      limit: scope.limit,
      answerAt: resolved?.answerAt ?? DEFAULT_ANSWER_AT,
      pauseAt: resolved?.pauseAt ?? DEFAULT_PAUSE_AT,
    });
  };

  const settle = (tokens: number, at: number) => {
    if (!reservation) {
      if (tokens <= 0 || scopes.length === 0) return;
      const id = crypto.randomUUID();
      for (const scope of scopes) store.commit(scope.key, id, tokens, at);
      return;
    }
    for (const scope of scopes) store.commit(scope.key, reservation.id, tokens, at);
    reservation = null;
  };

  const reserve = (tokens: number) => {
    // A round that never reported usage keeps its estimate, so the next round
    // does not see a free window.
    if (reservation) settle(reservation.tokens, now());
    if (tokens <= 0 || scopes.length === 0) return;
    const id = crypto.randomUUID();
    for (const scope of scopes) store.reserve(scope.key, id, tokens, now());
    reservation = { id, tokens };
  };

  return {
    active: true,
    ...(resolved?.maxToolCallsPerTurn != null
      ? { toolCap: resolved.maxToolCallsPerTurn }
      : {}),
    async beforeRound({ writer, pendingText, pendingTokens, toolCallsSoFar = 0, signal }) {
      if (pendingSummary) {
        const summary = pendingSummary;
        pendingSummary = undefined;
        writer.write({
          type: "data-notice",
          id: "digichat-limit",
          data: { tone: "status", message: summary.notice },
        });
        return { action: "answer", instruction: LIMIT_SUMMARIZE_INSTRUCTION };
      }
      if (!resolved) return PROCEED;
      const pending = pendingOf(pendingText, pendingTokens);
      if (scopes.length > 0) {
        let waited = 0;
        for (;;) {
          const at = now();
          let action: BudgetAction = "proceed";
          let waitMs = 0;
          for (const scope of scopes) {
            action = stricterAction(action, scopeAction(scope, pending, at));
            const snap = store.read(scope.key, at);
            waitMs = Math.max(
              waitMs,
              waitForRoomMs({
                events: snap.events,
                reserved: snap.reserved,
                pending,
                limit: scope.limit,
                pauseAt: resolved.pauseAt,
                now: at,
              }),
            );
          }
          if (action !== "pause") break;
          const slice = Math.min(waitMs, GUARDRAIL_MAX_WAIT_MS - waited);
          if (slice <= 0 || signal?.aborted) {
            // Waiting cannot free a round that is itself over the limit.
            // Say so, then let the caller nudge an answer instead of failing.
            writer.write({
              type: "data-notice",
              id: "digichat-token-budget",
              data: { tone: "status", message: GUARDRAIL_PAUSE_NOTICE },
            });
            break;
          }
          await waitOutRateLimit(writer, slice, 1, 1, signal, {
            id: "digichat-token-budget",
            message: GUARDRAIL_PAUSE_NOTICE,
            now,
            sleep: opts.sleep,
          });
          waited += slice;
          if (waited >= GUARDRAIL_MAX_WAIT_MS) break;
        }
      }
      const at = now();
      let action: BudgetAction = "proceed";
      for (const scope of scopes) action = stricterAction(action, scopeAction(scope, pending, at));
      const overTools =
        resolved.maxToolCallsPerTurn != null && toolCallsSoFar >= resolved.maxToolCallsPerTurn;
      if (overTools) {
        if (!toolNoticeSent) {
          writer.write({
            type: "data-notice",
            id: "tool-call-limit",
            data: {
              tone: "status",
              message: toolCallLimitNotice(resolved.maxToolCallsPerTurn!),
            },
          });
          toolNoticeSent = true;
        }
        reserve(pending);
        return { action: "stop-tools", instruction: TOOL_CAP_INSTRUCTION };
      }
      if (action === "pause" || action === "answer") {
        reserve(pending);
        return { action: "answer", instruction: WRAP_UP_INSTRUCTION };
      }
      reserve(pending);
      return PROCEED;
    },
    recordUsage(usage) {
      const input = finite(usage.inputTokens);
      const output = finite(usage.outputTokens);
      const total = finite(usage.totalTokens) ?? (input != null && output != null ? input + output : input ?? output ?? 0);
      settle(total, now());
    },
    release() {
      if (!reservation) return;
      settle(reservation.tokens, now());
    },
    noteToolCap(writer, toolCallsSoFar) {
      if (resolved?.maxToolCallsPerTurn == null) return;
      if (toolCallsSoFar < resolved.maxToolCallsPerTurn || toolNoticeSent) return;
      writer.write({
        type: "data-notice",
        id: "tool-call-limit",
        data: {
          tone: "status",
          message: toolCallLimitObservedNotice(resolved.maxToolCallsPerTurn),
        },
      });
      toolNoticeSent = true;
    },
    capToolPayload(value) {
      if (scopes.length === 0) return value;
      const at = now();
      let remaining = Number.POSITIVE_INFINITY;
      for (const scope of scopes) {
        const snap = store.read(scope.key, at);
        const used = tokensInWindow(snap.events, at) + snap.reserved;
        remaining = Math.min(remaining, scope.limit - used);
      }
      return capToolPayload(value, Math.max(0, Math.floor(remaining)));
    },
  };
}

function finite(value: number | undefined): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

/** beforeRound for adapters that make one upstream request. Returns an instruction to append, if any. */
export async function guardRound(
  guard: TurnGuard | undefined,
  opts: {
    writer: StreamWriter;
    pendingText: string;
    signal?: AbortSignal;
    toolCallsSoFar?: number;
  },
): Promise<string | undefined> {
  if (!guard?.active) return undefined;
  const clearance = await guard.beforeRound(opts);
  return clearance.action === "proceed" ? undefined : clearance.instruction;
}

type StepLike = { toolCalls?: readonly unknown[] };

/**
 * The AI SDK step hook. Counts tool calls already made, clips oversized tool
 * results, then applies the same pause / nudge / stop decision as Foundry.
 */
export async function guardrailPrepareStep<M extends { role: string; content: unknown }>(opts: {
  guard: TurnGuard;
  writer: StreamWriter;
  signal?: AbortSignal;
  steps: readonly StepLike[];
  messages: readonly M[];
  /** The instructions from the original streamText call, not a later step's copy. */
  initialInstructions?: string;
}): Promise<
  | {
      toolChoice?: "none";
      instructions?: string;
      messages?: M[];
    }
  | undefined
> {
  if (!opts.guard.active) return undefined;
  const toolCallsSoFar = opts.steps.reduce((n, step) => n + (step.toolCalls?.length ?? 0), 0);
  const messages = opts.messages.map((message) => ({
    ...message,
    content:
      message.role === "tool" ? opts.guard.capToolPayload(message.content) : message.content,
  })) as M[];
  const clearance = await opts.guard.beforeRound({
    writer: opts.writer,
    pendingText: messages
      .map((message) => (typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "")))
      .join("\n"),
    toolCallsSoFar,
    signal: opts.signal,
  });
  if (clearance.action === "proceed") {
    const clipped = messages.some((message, i) => message.content !== opts.messages[i]?.content);
    return clipped ? { messages } : undefined;
  }
  const instructions = opts.initialInstructions
    ? `${opts.initialInstructions}\n\n${clearance.instruction}`
    : clearance.instruction;
  return {
    ...(clearance.action === "stop-tools" ? { toolChoice: "none" as const } : {}),
    instructions,
    messages,
  };
}
