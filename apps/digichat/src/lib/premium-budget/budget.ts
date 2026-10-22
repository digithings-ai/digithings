/**
 * Per-user premium spend. Auto and the other presets are not metered.
 *
 * This sits beside `guardrails.tokensPerMinute` as `models.costPerWindow`.
 * The in-memory window is per Node instance. `installPremiumSpendStore` is
 * the seam for a shared store. This module does not call a provider.
 */

import { autoPresetModelId } from "@/lib/model-picker-catalog";

export const TYPICAL_PREMIUM_INPUT_TOKENS = 3550;
export const TYPICAL_PREMIUM_OUTPUT_TOKENS = 600;
export const PREMIUM_BUDGET_TURNS = 3;
export const DEFAULT_PREMIUM_WINDOW_SECONDS = 86_400;

/**
 * One digithings.ai turn, sized from what the model actually receives:
 *
 * - 300 input tokens for the digithings research prompt (1,092 characters).
 * - 600 input tokens for the digisearch and digivault tool definitions.
 * - 50 input tokens for one short question. The public embed does not
 *   persist a thread, so this is not the 8,000-token history cap.
 * - 700 input tokens for one search: 5 rows, each clipped to 300 characters
 *   (`_LLM_SEARCH_PREVIEW_ROWS` / `_LLM_SEARCH_PREVIEW_CHARS` in digigraph).
 * - 1,900 input tokens for one follow-up note. The median markdown file
 *   under `docs/` is about 7,700 characters, under the 12,000-character
 *   tool-message cap.
 * - 600 output tokens for the tool-call arguments, a short answer, and a
 *   modest reasoning trace. These models bill reasoning as output.
 *
 * 3,550 in + 600 out. GLM 5.3 is the pricier premium model at this mix
 * ($0.77 / $2.42 per million) versus Gemini 3.8 Flash ($0.4875 / $2.4375).
 * Three of those turns is $0.0125565 per rolling day.
 */
export const PREMIUM_BUDGET_MESSAGE =
  "You've used today's premium budget. Answering with Auto instead.";

export type PremiumRate = { inputPerM: number; outputPerM: number };

export type CostPerWindow = { usd: number; windowSeconds?: number };

export type PremiumUsage = { inputTokens: number; outputTokens: number };

export function premiumTurnUsd(
  rate: PremiumRate,
  inputTokens = TYPICAL_PREMIUM_INPUT_TOKENS,
  outputTokens = TYPICAL_PREMIUM_OUTPUT_TOKENS,
): number {
  return (inputTokens * rate.inputPerM + outputTokens * rate.outputPerM) / 1_000_000;
}

type SpendEvent = { atMs: number; usd: number };

export type PremiumSpendStore = {
  spent(key: string, nowMs: number, windowMs: number): number;
  add(key: string, usd: number, nowMs: number): void;
};

const memory = new Map<string, SpendEvent[]>();

const memoryStore: PremiumSpendStore = {
  spent(key, nowMs, windowMs) {
    const kept = (memory.get(key) ?? []).filter((event) => nowMs - event.atMs < windowMs);
    memory.set(key, kept);
    return kept.reduce((sum, event) => sum + event.usd, 0);
  },
  add(key, usd, nowMs) {
    const events = memory.get(key) ?? [];
    events.push({ atMs: nowMs, usd });
    memory.set(key, events);
  },
};

let store: PremiumSpendStore = memoryStore;

/** Test and future Durable Object seam. Pass nothing to restore the in-memory store. */
export function installPremiumSpendStore(next?: PremiumSpendStore): void {
  store = next ?? memoryStore;
  if (!next) memory.clear();
}

export function resetPremiumSpendForTests(): void {
  memory.clear();
}

/**
 * Same order as `guardrailIdentity`. A client session header is not a
 * budget key. `embed:anonymous` is not a person, and `unknown` is not an
 * address. The address is `clientIpForRateLimit`: a stamped socket, or a
 * forwarded header from a stamped peer on `DIGICHAT_TRUSTED_PROXIES`. An
 * unstamped peer header is `unknown` even when that allowlist is set.
 * Callers with neither share `anonymous`.
 */
export function premiumSpendIdentity(opts: {
  userId?: string | null;
  ip?: string | null;
}): string {
  const user = opts.userId && opts.userId !== "embed:anonymous" ? opts.userId.trim() : "";
  if (user) return user;
  const ip = opts.ip && opts.ip !== "unknown" ? opts.ip.trim() : "";
  return ip || "anonymous";
}

export function premiumUserKey(slug: string, identity: string): string {
  return `${slug}:${identity}`;
}

export function chargePremiumUsage(
  key: string,
  rate: PremiumRate,
  usage: PremiumUsage | undefined,
  nowMs: number,
): number {
  const inputTokens = usage ? usage.inputTokens : TYPICAL_PREMIUM_INPUT_TOKENS;
  const outputTokens = usage ? usage.outputTokens : TYPICAL_PREMIUM_OUTPUT_TOKENS;
  if (usage && inputTokens <= 0 && outputTokens <= 0) return 0;
  const usd = premiumTurnUsd(rate, inputTokens, outputTokens);
  if (usd <= 0) return 0;
  store.add(key, usd, nowMs);
  return usd;
}

export function applyPremiumBudget(input: {
  modelId: string;
  /** Recorded by the caller. A spent window still answers with Auto. */
  defaultModel: string | undefined;
  premium: boolean;
  /** Premium group ids. A spent window still answers with Auto. */
  premiumIds?: readonly string[];
  rate: PremiumRate | undefined;
  budget: CostPerWindow | undefined;
  userKey: string;
  nowMs?: number;
}): {
  modelId: string;
  notice?: string;
  charge?: (usage?: PremiumUsage) => void;
} {
  if (!input.premium || !input.budget || !input.rate) {
    return { modelId: input.modelId };
  }
  const nowMs = input.nowMs ?? Date.now();
  const windowMs = (input.budget.windowSeconds ?? DEFAULT_PREMIUM_WINDOW_SECONDS) * 1000;
  const spent = store.spent(input.userKey, nowMs, windowMs);
  if (spent >= input.budget.usd) {
    // The notice names Auto. A configured default is not served, whether or
    // not that default is in `premiumIds`.
    return {
      modelId: autoPresetModelId(),
      notice: PREMIUM_BUDGET_MESSAGE,
    };
  }
  const rate = input.rate;
  const key = input.userKey;
  return {
    modelId: input.modelId,
    charge: (usage) => {
      chargePremiumUsage(key, rate, usage, Date.now());
    },
  };
}
