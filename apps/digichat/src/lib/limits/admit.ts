/**
 * Pre-turn admission for the chat route. Block stops the request. Fallback
 * rewrites the model. Pause asks the turn guard to summarize. Token-per-minute
 * pause stays in the turn guard and is not decided here.
 */

import { LIMIT_SUMMARIZE_INSTRUCTION } from "@/lib/guardrails/turn";
import {
  evaluateLimits,
  recordAdmission,
  recordUsage,
  type LimitDecision,
  type LimitIdentities,
} from "./evaluate";
import {
  costPerWindowCovered,
  flattenLimits,
  guardrailsFromLimits,
  limitsFromGuardrails,
  ruleFromCostPerWindow,
  standardOutputCap,
  type CostPerWindow,
  type GuardrailAlias,
  type LimitRule,
  type LimitsConfig,
} from "./schema";
import { activeLimitsStore, type LimitsMemory, type Price, type Usage } from "./store";

const KIND_ORDER = ["sessions", "turns", "models", "cost", "tokens", "toolCalls"];

export function mergeLimitRules(
  limits: LimitsConfig | null | undefined,
  guardrails: GuardrailAlias | null | undefined,
  budget?: CostPerWindow | null,
  caps?: { outputCapUsdPerMillion?: number; premiumIds?: readonly string[] },
): LimitRule[] {
  const primary = flattenLimits(limits);
  const paths = new Set(primary.map((rule) => rule.path));
  const alias = flattenLimits(limitsFromGuardrails(guardrails)).filter((rule) => !paths.has(rule.path));
  const premium =
    budget && !costPerWindowCovered(limits, budget)
      ? [
          ruleFromCostPerWindow(budget, {
            outputCapUsdPerMillion: caps?.outputCapUsdPerMillion,
            premiumIds: caps?.premiumIds ?? limits?.models?.premium?.ids,
          }),
        ]
      : [];
  return [...primary, ...alias, ...premium].sort(
    (a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind),
  );
}

export type ChatAdmission = {
  decision: LimitDecision;
  /** Present when the turn should continue but the model must wrap up. */
  summarize?: { notice: string; instruction: string };
  /** Model to send when the decision is a fallback. */
  model?: string;
  record(usage: Usage, modelId?: string): void;
};

export function admitChatTurn(opts: {
  limits?: LimitsConfig | null;
  guardrails?: GuardrailAlias | null;
  slug: string;
  userId?: string | null;
  sessionId?: string | null;
  ip?: string | null;
  conversationId?: string | null;
  modelId?: string;
  explicitModel: boolean;
  autoModel?: string;
  outputCapUsdPerMillion?: number;
  /** #6193 `models.costPerWindow`. Enforced as one premium cost gate. */
  costPerWindow?: CostPerWindow | null;
  prices?: Readonly<Record<string, Price>>;
  now?: number;
  store?: LimitsMemory;
}): ChatAdmission {
  const cap = standardOutputCap(opts.limits, opts.outputCapUsdPerMillion);
  const rules = mergeLimitRules(opts.limits, opts.guardrails, opts.costPerWindow, {
    outputCapUsdPerMillion: cap,
    premiumIds: opts.limits?.models?.premium?.ids,
  });
  const store = opts.store ?? activeLimitsStore();
  const at = opts.now ?? Date.now();
  const ids: LimitIdentities = {
    slug: opts.slug,
    userId: opts.userId,
    sessionId: opts.sessionId,
    ip: opts.ip,
    conversationId: opts.conversationId,
  };
  const prices = { ...(opts.prices ?? {}), ...(opts.limits?.cost?.prices ?? {}) };
  const noop = () => {};
  if (rules.length === 0) {
    return { decision: { action: "proceed" }, record: noop };
  }
  const decision = evaluateLimits({
    rules,
    ids,
    store,
    at,
    model: {
      id: opts.modelId,
      explicit: opts.explicitModel,
      autoModel: opts.autoModel,
      prices,
      outputCapUsdPerMillion: cap,
    },
  });
  if (decision.action === "block") return { decision, record: noop };
  recordAdmission({ rules, ids, store, at });
  const model = decision.action === "fallback-auto" ? decision.model : undefined;
  return {
    decision,
    ...(model ? { model } : {}),
    ...(decision.action === "pause"
      ? { summarize: { notice: decision.message, instruction: LIMIT_SUMMARIZE_INSTRUCTION } }
      : {}),
    record(usage, modelId) {
      recordUsage({
        rules,
        ids,
        store,
        at,
        usage,
        modelId: modelId ?? model ?? opts.modelId,
        prices,
        outputCapUsdPerMillion: cap,
        premiumIds: opts.limits?.models?.premium?.ids,
      });
    },
  };
}

export function projectedGuardrails(
  limits: LimitsConfig | null | undefined,
  guardrails: GuardrailAlias | null | undefined,
): GuardrailAlias | undefined {
  return guardrails ?? guardrailsFromLimits(limits) ?? undefined;
}
