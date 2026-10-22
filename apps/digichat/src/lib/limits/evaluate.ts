/**
 * AND combination. The first gate that is already exceeded wins.
 * Order: sessions, turns, model tier, cost, tokens. Tool calls are enforced
 * inside the turn, not here.
 *
 * A token-per-minute gate whose action is `pause` is left to the turn guard
 * (the rolling window and the "Pausing for the token limit" waiter). This
 * check does not also block that turn.
 */

import type { LimitRule, LimitScope } from "./schema";
import {
  bucketFor,
  usdForTokens,
  windowDurationMs,
  windowStart,
  type LimitsMemory,
  type Price,
  type Usage,
} from "./store";

export type LimitIdentities = {
  slug: string;
  userId?: string | null;
  sessionId?: string | null;
  ip?: string | null;
  conversationId?: string | null;
};

export type ModelPick = {
  id?: string;
  explicit: boolean;
  autoModel?: string;
  prices: Readonly<Record<string, Price>>;
  outputCapUsdPerMillion?: number;
};

export type LimitDecision =
  | { action: "proceed" }
  | { action: "block"; path: string; message: string }
  | { action: "fallback-auto"; path: string; message: string; model?: string }
  | { action: "pause"; path: string; message: string };

const PROCEED: LimitDecision = { action: "proceed" };

const DEFAULT_IDLE_MINUTES = 30;

const DEFAULT_MESSAGE: Record<string, string> = {
  sessions: "This deployment allows a limited number of chats from one network.",
  turns: "This chat has reached its question limit.",
  cost: "This chat has reached its cost limit.",
  tokens: "This chat has reached its token limit.",
  models: "That model is outside this deployment's standard tier.",
};

function messageFor(rule: LimitRule): string {
  return rule.message ?? DEFAULT_MESSAGE[rule.kind] ?? "This chat has reached a limit.";
}

function scopeId(scope: LimitScope, ids: LimitIdentities): string | null {
  if (scope === "deployment" || scope === "subscription") return `dep:${ids.slug}`;
  if (scope === "user") {
    const user = ids.userId?.trim();
    if (user && user !== "embed:anonymous") return `user:${user}`;
    const session = ids.sessionId?.trim();
    if (session) return `session:${session}`;
    const ip = ids.ip?.trim();
    if (ip && ip !== "unknown") return `ip:${ip}`;
    return "anonymous";
  }
  if (scope === "ip") {
    const ip = ids.ip?.trim();
    if (!ip || ip === "unknown") return null;
    return `ip:${ip}`;
  }
  const session = ids.conversationId?.trim() || ids.sessionId?.trim();
  return session ? `session:${session}` : null;
}

function counterKey(rule: LimitRule, ids: LimitIdentities): string | null {
  const who = scopeId(rule.scope, ids);
  if (!who) return null;
  if (rule.window !== "session") return `${ids.slug}|${rule.path}|${who}`;
  const sessionKey = ids.conversationId?.trim() || ids.sessionId?.trim() || "none";
  return `${ids.slug}|${rule.path}|${who}|${bucketFor(rule.window, sessionKey)}`;
}

function ruleWindowMs(rule: LimitRule): number | null {
  return rule.windowMs ?? windowDurationMs(rule.window);
}

function decide(rule: LimitRule, model?: string): LimitDecision {
  const message = messageFor(rule);
  if (rule.onExceed === "fallback-auto") {
    return { action: "fallback-auto", path: rule.path, message, ...(model ? { model } : {}) };
  }
  if (rule.onExceed === "pause") return { action: "pause", path: rule.path, message };
  return { action: "block", path: rule.path, message };
}

function deferredToTurnGuard(rule: LimitRule): boolean {
  return rule.kind === "tokens" && rule.window === "minute" && rule.onExceed === "pause";
}

export function modelIsPremium(
  modelId: string,
  opts: {
    prices: Readonly<Record<string, Price>>;
    premiumIds?: readonly string[];
    outputCapUsdPerMillion?: number;
  },
): boolean {
  if (opts.premiumIds?.includes(modelId)) return true;
  const price = opts.prices[modelId];
  if (!price || opts.outputCapUsdPerMillion == null) return false;
  return price.outputPerM > opts.outputCapUsdPerMillion;
}

function isPremium(modelId: string, rule: LimitRule, pick: ModelPick): boolean {
  return modelIsPremium(modelId, {
    prices: pick.prices,
    premiumIds: rule.premiumIds,
    outputCapUsdPerMillion: rule.maxOutputUsdPerMillion ?? pick.outputCapUsdPerMillion,
  });
}

function sessionOver(rule: LimitRule, ids: LimitIdentities, store: LimitsMemory, at: number): boolean {
  const who = scopeId("ip", ids);
  if (!who) return false;
  const conversation = ids.conversationId?.trim() || ids.sessionId?.trim();
  if (!conversation) return false;
  const key = `${ids.slug}|${rule.path}|${who}`;
  const idleMs =
    rule.window === "concurrent" ? (rule.idleMinutes ?? DEFAULT_IDLE_MINUTES) * 60_000 : null;
  const start = rule.window === "concurrent" ? null : windowStart(rule.window, at);
  if (store.hasSession(key, conversation, at, idleMs, start)) return false;
  return store.sessionCount(key, at, idleMs, start) >= (rule.max ?? 1);
}

export function evaluateLimits(opts: {
  rules: readonly LimitRule[];
  ids: LimitIdentities;
  store: LimitsMemory;
  at: number;
  model: ModelPick;
}): LimitDecision {
  const { rules, ids, store, at } = opts;
  let modelId = opts.model.id;
  let fallback: LimitDecision | null = null;

  for (const rule of rules) {
    if (rule.kind === "toolCalls") continue;
    if (deferredToTurnGuard(rule)) continue;

    if (rule.kind === "sessions") {
      if (sessionOver(rule, ids, store, at)) return decide(rule);
      continue;
    }

    if (rule.kind === "models") {
      if (!rule.manualOnly || !modelId) continue;
      if (!isPremium(modelId, rule, opts.model)) continue;
      if (opts.model.explicit) continue;
      const next = decide(rule, opts.model.autoModel);
      if (next.action === "block") return next;
      if (next.action === "fallback-auto") {
        fallback = next;
        modelId = opts.model.autoModel;
      }
      continue;
    }

    if (rule.kind === "cost" && rule.premiumOnly) {
      if (!modelId || !isPremium(modelId, rule, opts.model)) continue;
    }

    const key = counterKey(rule, ids);
    if (!key || rule.max == null) continue;
    const used = store.read(key, at, ruleWindowMs(rule));
    if (used >= rule.max) {
      const next = decide(rule, opts.model.autoModel);
      if (next.action === "block" || next.action === "pause") return next;
      if (!fallback) fallback = next;
    }
  }

  return fallback ?? PROCEED;
}

export function recordAdmission(opts: {
  rules: readonly LimitRule[];
  ids: LimitIdentities;
  store: LimitsMemory;
  at: number;
}): void {
  const { rules, ids, store, at } = opts;
  for (const rule of rules) {
    if (rule.kind === "turns") {
      const key = counterKey(rule, ids);
      if (key) store.add(key, 1, at);
    }
    if (rule.kind === "sessions") {
      const who = scopeId("ip", ids);
      const conversation = ids.conversationId?.trim() || ids.sessionId?.trim();
      if (!who || !conversation) continue;
      store.noteSession(`${ids.slug}|${rule.path}|${who}`, conversation, at);
    }
  }
}

export function recordUsage(opts: {
  rules: readonly LimitRule[];
  ids: LimitIdentities;
  store: LimitsMemory;
  at: number;
  usage: Usage;
  modelId?: string;
  prices: Readonly<Record<string, Price>>;
  outputCapUsdPerMillion?: number;
  premiumIds?: readonly string[];
}): void {
  const { rules, ids, store, at, usage } = opts;
  const input = finite(usage.inputTokens) ?? 0;
  const output = finite(usage.outputTokens) ?? 0;
  const total =
    finite(usage.totalTokens) ?? (input + output > 0 ? input + output : 0);
  const price = opts.modelId ? opts.prices[opts.modelId] : undefined;
  const usd = price ? usdForTokens(usage, price) : 0;
  for (const rule of rules) {
    if (deferredToTurnGuard(rule)) continue;
    const key = counterKey(rule, ids);
    if (!key) continue;
    if (rule.kind === "tokens") {
      const amount =
        rule.metric === "input" ? input : rule.metric === "output" ? output : total;
      store.add(key, amount, at);
    } else if (rule.kind === "cost" && usd > 0) {
      if (
        rule.premiumOnly &&
        (!opts.modelId ||
          !modelIsPremium(opts.modelId, {
            prices: opts.prices,
            premiumIds: rule.premiumIds ?? opts.premiumIds,
            outputCapUsdPerMillion: rule.maxOutputUsdPerMillion ?? opts.outputCapUsdPerMillion,
          }))
      ) {
        continue;
      }
      store.add(key, usd, at);
    }
  }
}

function finite(value: number | undefined): number | undefined {
  return value != null && Number.isFinite(value) && value > 0 ? value : undefined;
}
